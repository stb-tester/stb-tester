"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/drothlis/stb-tester/blob/master/LICENSE for details).
"""

from collections import namedtuple, deque
import argparse
from contextlib import contextmanager
import ConfigParser
import Queue
import errno
import inspect
import os
import re
import socket
import sys
import time

import irnetbox


class ArgvHider:
    """ For use with 'with' statement:  Unsets argv and resets it.

    This is used because otherwise gst-python will exit if '-h', '--help', '-v'
    or '--version' command line arguments are given.
    """
    def __enter__(self):
        self.argv = sys.argv[:]
        del sys.argv[1:]

    def __exit__(self, type, value, traceback):
        sys.argv = self.argv


class StdErrHider:
    """For use with 'with' statement: Hide stderr output.

    This is used because otherwise gst-python will print
    'pygobject_register_sinkfunc is deprecated'.
    """
    def __enter__(self):
        fd = sys.__stderr__.fileno()
        self.saved_fd = os.dup(fd)
        sys.__stderr__.flush()
        self.null_stream = open(os.devnull, 'w', 0)
        os.dup2(self.null_stream.fileno(), fd)

    def __exit__(self, type, value, traceback):
        sys.__stderr__.flush()
        os.dup2(self.saved_fd, sys.__stderr__.fileno())
        self.null_stream.close()


import pygst  # gstreamer
pygst.require("0.10")
with ArgvHider(), StdErrHider():
    import gst
import gobject
import glib


# Functions available to stbt scripts
#===========================================================================

def press(key):
    """Send the specified key-press to the system under test.

    The mechanism used to send the key-press depends on what you've configured
    with `--control`.

    `key` is a string. The allowed values depend on the control you're using:
    If that's lirc, then `key` is a key name from your lirc config file.
    """
    return control.press(key)

@contextmanager
def process_all_frames():
    """Force the pipeline to process all the frames for the duration of the
    call.

    This will introduce a delay with the live stream but will not block the
    pipeline. The delay will depend on which features are actually used in the
    context of this call.

    Use as a context manager in a 'with' statement.
    """
    with display.process_all_frames():
        yield


class Position(namedtuple('Position', 'x y')):
    """
    * `x` and `y`: Integer coordinates from the top left corner of the video
      frame.
    """
    pass


class MatchResult(namedtuple(
        'MatchResult', 'timestamp match position first_pass_result')):
    """
    * `timestamp`: Video stream timestamp.
    * `match`: Boolean result.
    * `position`: `Position` of the match.
    * `first_pass_result`: Value between 0 (poor) and 1.0 (excellent match)
      from the first pass of the two-pass templatematch algorithm.
    """
    pass


def detect_match(image, timeout_secs=10, noise_threshold=0.16):
    """Generator that yields a sequence of one `MatchResult` for each frame
    processed from the source video stream.

    Returns after `timeout_secs` seconds. (Note that the caller can also choose
    to stop iterating over this function's results at any time.)

    `noise_threshold` is a parameter used by the templatematch algorithm.
    Increase `noise_threshold` to avoid false negatives, at the risk of
    increasing false positives (a value of 1.0 will report a match every time).
    """

    params = {
        "template": _find_path(image),
        "noiseThreshold": noise_threshold,
    }
    debug("Searching for " + params["template"])
    if not os.path.isfile(params["template"]):
        raise UITestError("No such template file: %s" % image)

    for message, buf in display.detect("template_match", params, timeout_secs):
        # Discard messages generated from previous call with different template
        if message["template_path"] == params["template"]:
            result = MatchResult(
                timestamp=buf.timestamp,
                match=message["match"],
                position=Position(message["x"], message["y"]),
                first_pass_result=message["first_pass_result"])
            debug("%s found: %s" % (
                  "Match" if result.match else "Weak match", str(result)))
            yield result


class MotionResult(namedtuple('MotionResult', 'timestamp motion')):
    """
    * `timestamp`: Video stream timestamp.
    * `motion`: Boolean result.
    """
    pass


def detect_motion(timeout_secs=10, noise_threshold=0.84, mask=None):
    """Generator that yields a sequence of one `MotionResult` for each frame
    processed from the source video stream.

    Returns after `timeout_secs` seconds. (Note that the caller can also choose
    to stop iterating over this function's results at any time.)

    `noise_threshold` is a parameter used by the motiondetect algorithm.
    Increase `noise_threshold` to avoid false negatives, at the risk of
    increasing false positives (a value of 0.0 will never report motion).
    This is particularly useful with noisy analogue video sources.

    `mask` is a black and white image that specifies which part of the image
    to search for motion. White pixels select the area to search; black pixels
    the area to ignore.
    """

    debug("Searching for motion")
    params = {
        "enabled": True,
        "noiseThreshold": noise_threshold,
    }
    if mask:
        params["mask"] = _find_path(mask)
        debug("Using mask %s" % (params["mask"]))
        if not os.path.isfile(params["mask"]):
            debug("No such mask file: %s" % mask)
            raise UITestError("No such mask file: %s" % mask)

    for msg, buf in display.detect("motiondetect", params, timeout_secs):
        # Discard messages generated from previous calls with a different mask
        if ((mask and msg["masked"] and msg["mask_path"] == params["mask"])
                or (not mask and not msg["masked"])):
            result = MotionResult(timestamp=buf.timestamp,
                                  motion=msg["has_motion"])
            debug("%s detected. Timestamp: %d." % (
                "Motion" if result.motion else "No motion", result.timestamp))
            yield result


def wait_for_match(image, timeout_secs=10,
                   consecutive_matches=1, noise_threshold=0.16):
    """Search for `image` in the source video stream.

    Returns `MatchResult` when `image` is found.
    Raises `MatchTimeout` if no match is found after `timeout_secs` seconds.

    `consecutive_matches` forces this function to wait for several consecutive
    frames with a match found at the same x,y position.

    Increase `noise_threshold` to avoid false negatives, at the risk of
    increasing false positives (a value of 1.0 will report a match every time);
    increase `consecutive_matches` to avoid false positives due to noise. But
    please let us know if you are having trouble with image matches, so that we
    can improve the matching algorithm.
    """

    match_count = 0
    last_pos = Position(0, 0)
    for res in detect_match(image, timeout_secs, noise_threshold):
        if res.match and (match_count == 0 or res.position == last_pos):
            match_count += 1
        else:
            match_count = 0
        last_pos = res.position
        if match_count == consecutive_matches:
            debug("Matched " + image)
            return res

    screenshot = display.capture_down_stream_screenshot()
    raise MatchTimeout(screenshot, image, timeout_secs)


def press_until_match(key, image,
                      interval_secs=3, noise_threshold=0.16, max_presses=10):
    """Calls `press` as many times as necessary to find the specified `image`.

    Returns `MatchResult` when `image` is found.
    Raises `MatchTimeout` if no match is found after `max_presses` times.

    `interval_secs` is the number of seconds to wait for a match before
    pressing again.
    """
    i = 0
    while True:
        try:
            return wait_for_match(image, timeout_secs=interval_secs,
                                  noise_threshold=noise_threshold)
        except MatchTimeout:
            if i < max_presses:
                press(key)
                i += 1
            else:
                raise


def wait_for_motion(
        timeout_secs=10, consecutive_frames=10,
        noise_threshold=0.84, mask=None):
    """Search for motion in the source video stream.

    Returns `MotionResult` when motion is detected.
    Raises `MotionTimeout` if no motion is detected after `timeout_secs`
    seconds.

    Considers the video stream to have motion if there were diferences between
    10 consecutive frames, or the number specified by `consecutive_frames`,
    which can be:

    * a positive integer value, or
    * a string in the form "x/y", where `x` is the number of frames with motion
      detected out of a sliding window of `y` frames.

    Increase `noise_threshold` to avoid false negatives, at the risk of
    increasing false positives (a value of 0.0 will never report motion).
    This is particularly useful with noisy analogue video sources.

    `mask` is a black and white image that specifies which part of the image
    to search for motion. White pixels select the area to search; black pixels
    the area to ignore.
    """

    consecutive_frames = str(consecutive_frames)
    if '/' in consecutive_frames:
        motion_frames = int(consecutive_frames.split('/')[0])
        considered_frames = int(consecutive_frames.split('/')[1])
    else:
        motion_frames = int(consecutive_frames)
        considered_frames = int(consecutive_frames)

    if motion_frames > considered_frames:
        raise ConfigurationError(
            "`motion_frames` exceeds `considered_frames`")

    debug("Waiting for %d out of %d frames with motion" % (
        motion_frames, considered_frames))

    matches = deque(maxlen=considered_frames)
    for res in detect_motion(timeout_secs, noise_threshold, mask):
        matches.append(res.motion)
        if matches.count(True) >= motion_frames:
            debug("Motion detected.")
            return res

    screenshot = display.capture_down_stream_screenshot()
    raise MotionTimeout(screenshot, mask, timeout_secs)

def get_live_stream_timestamp():
    return display.get_live_stream_timestamp()


def save_frame(buf, filename):
    """Save a GStreamer buffer to the specified file in png format.

    Takes a buffer `buf` obtained from `get_frame` or from the `screenshot`
    property of `MatchTimeout` or `MotionTimeout`.
    """
    pipeline = gst.parse_launch(" ! ".join([
        'appsrc name="src" caps="%s"' % buf.get_caps(),
        'ffmpegcolorspace',
        'pngenc',
        'filesink location="%s"' % filename,
    ]))
    src = pipeline.get_by_name("src")
    # This is actually a (synchronous) method call to push-buffer:
    src.emit('push-buffer', buf)
    src.emit('end-of-stream')
    pipeline.set_state(gst.STATE_PLAYING)
    msg = pipeline.get_bus().poll(
        gst.MESSAGE_ERROR | gst.MESSAGE_EOS, 25 * gst.SECOND)
    pipeline.set_state(gst.STATE_NULL)
    if msg.type == gst.MESSAGE_ERROR:
        err, dbg = msg.parse_error()
        raise RuntimeError("%s: %s\n%s\n" % (err, err.message, dbg))


def get_frame():
    """Get a GStreamer buffer containing the current video frame."""
    return display.capture_down_stream_screenshot()


def get_config(key, tool=None):
    """Read the value of `key` from the stbt config file.

    See 'CONFIGURATION' in the stbt(1) man page for the config file search
    path.

    Raises `ConfigurationError` if the specified `tool` section or `key` is not
    found.
    """
    try:
        return load_config(tool)[key]
    except KeyError:
        raise ConfigurationError("No such config key: '%s'" % key)
    except ConfigParser.NoSectionError:
        raise ConfigurationError("No such config section: '%s'" % tool)


def debug(s):
    """Print the given string to stderr if stbt run `--verbose` was given."""
    if _debug_level > 0:
        sys.stderr.write("%s: %s\n" % (os.path.basename(sys.argv[0]), str(s)))


class UITestError(Exception):
    """The test script had an unrecoverable error."""
    pass


class UITestFailure(Exception):
    """The test failed because the system under test didn't behave as expected.
    """
    pass


class MatchTimeout(UITestFailure):
    """
    * `screenshot`: A GStreamer frame from the source video when the search
      for the expected image timed out.
    * `expected`: Filename of the image that was being searched for.
    * `timeout_secs`: Number of seconds that the image was searched for.
    """
    def __init__(self, screenshot, expected, timeout_secs):
        self.screenshot = screenshot
        self.expected = expected
        self.timeout_secs = timeout_secs

    def __str__(self):
        return "Didn't find match for '%s' within %d seconds." % (
            self.expected, self.timeout_secs)


class MotionTimeout(UITestFailure):
    """
    * `screenshot`: A GStreamer frame from the source video when the search
      for motion timed out.
    * `mask`: Filename of the mask that was used (see `wait_for_motion`).
    * `timeout_secs`: Number of seconds that motion was searched for.
    """
    def __init__(self, screenshot, mask, timeout_secs):
        self.screenshot = screenshot
        self.mask = mask
        self.timeout_secs = timeout_secs

    def __str__(self):
        return "Didn't find motion%s within %d seconds." % (
            " (with mask '%s')" % self.mask if self.mask else "",
            self.timeout_secs)


class ConfigurationError(UITestError):
    pass


# stbt-run initialisation and convenience functions
# (you will need these if writing your own version of stbt-run)
#===========================================================================

def argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--control',
        help='The remote control to control the stb (default: %(default)s)')
    parser.add_argument(
        '--source-pipeline',
        help='A gstreamer pipeline to use for A/V input (default: '
             '%(default)s)')
    parser.add_argument(
        '--sink-pipeline',
        help='A gstreamer pipeline to use for video output '
             '(default: %(default)s)')

    class IncreaseDebugLevel(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            global _debug_level
            _debug_level += 1
            setattr(namespace, self.dest, _debug_level)

    global _debug_level
    _debug_level = 0
    parser.add_argument(
        '-v', '--verbose', action=IncreaseDebugLevel, nargs=0,
        help='Enable debug output (specify twice to enable GStreamer element '
             'dumps to ./stbt-debug directory)')

    return parser


def init_run(gst_source_pipeline, gst_sink_pipeline, control_uri):
    global display, control
    display = Display(gst_source_pipeline, gst_sink_pipeline)
    control = uri_to_remote(control_uri, display)


def teardown_run():
    display.teardown()


# Internal
#===========================================================================

_config = None
_debug_level = 0
_mainloop = glib.MainLoop()


def MessageIterator(bus, signal):
    queue = Queue.Queue()

    def sig(bus, message):
        queue.put(message)
        _mainloop.quit()
    bus.connect(signal, sig)
    try:
        stop = False
        while not stop:
            _mainloop.run()
            # Check what interrupted the main loop (new message, error thrown)
            try:
                item = queue.get(block=False)
                yield item
            except Queue.Empty:
                stop = True
    finally:
        bus.disconnect_by_func(sig)


class Display:
    def __init__(self, source_pipeline_description, sink_pipeline_description):
        gobject.threads_init()

        imageprocessing = " ! ".join([
            # Buffer the video stream, dropping frames if downstream
            # processors aren't fast enough:
            "queue name=q leaky=2",
            # Convert to a colorspace that templatematch can handle:
            "ffmpegcolorspace",
            # Detect motion when requested:
            "stbt-motiondetect name=motiondetect enabled=false",
            # OpenCV image-processing library:
            "stbt-templatematch name=template_match method=1",
        ])
        xvideo = " ! ".join([
            # Convert to a colorspace that xvimagesink can handle:
            "ffmpegcolorspace",
            sink_pipeline_description,
        ])
        screenshot = ("appsink name=screenshot max-buffers=1 drop=true "
                      "sync=false")
        pipe = " ".join([
            "tee name=up_t",
            "up_t. ! appsink name=upstream_screenshot "
                            "max-buffers=1 drop=true sync=false",
            "up_t. ! ",
            imageprocessing,
            "! tee name=t",
            "t. ! queue leaky=2 !", screenshot,
            "t. ! queue leaky=2 !", xvideo
        ])

        self.source_pipeline_description = source_pipeline_description
        self.source_bin = self.create_source_bin()
        self.sink_bin = gst.parse_bin_from_description(pipe, True)

        self.pipeline = gst.Pipeline("stb-tester")
        self.pipeline.add(self.source_bin, self.sink_bin)
        gst.element_link_many(self.source_bin, self.sink_bin)

        self.templatematch = self.pipeline.get_by_name("template_match")
        self.motiondetect = self.pipeline.get_by_name("motiondetect")
        self.upstream_screenshot = \
            self.pipeline.get_by_name("upstream_screenshot")
        self.screenshot = self.pipeline.get_by_name("screenshot")
        self.bus = self.pipeline.get_bus()
        self.bus.connect("message::error", self.on_error)
        self.bus.connect("message::warning", self.on_warning)
        self.bus.add_signal_watch()

        if _debug_level > 1:
            if _mkdir("stbt-debug/motiondetect") and _mkdir(
                    "stbt-debug/templatematch"):
                # Note that this will dump a *lot* of files -- several images
                # per frame processed.
                self.motiondetect.props.debugDirectory = (
                    "stbt-debug/motiondetect")
                self.templatematch.props.debugDirectory = (
                    "stbt-debug/templatematch")
            else:
                warn("Failed to create directory 'stbt-debug'. "
                     "Will not enable motiondetect/templatematch debug dump.")

        self.pipeline.set_state(gst.STATE_PLAYING)

        # Handle loss of video (but without end-of-stream event) from the
        # Hauppauge HDPVR capture device.
        self.queue = self.pipeline.get_by_name("q")
        self.test_timeout = None
        self.successive_underruns = 0
        self.underrun_timeout = None
        self.underrun_handler_id = self.queue.connect("underrun", self.on_underrun)
        self.queue.connect("running", self.on_running)
        self.last_config = {}

    def create_source_bin(self):
        source_bin = gst.parse_bin_from_description(
            "%s ! capsfilter name=padforcer caps=video/x-raw-yuv" % (
                self.source_pipeline_description),
            False)
        source_bin.add_pad(
            gst.GhostPad(
                "source",
                source_bin.get_by_name("padforcer").src_pads().next()))
        return source_bin

    def capture_live_stream_screenshot(self):
        return self.upstream_screenshot.get_property("last-buffer")

    def capture_down_stream_screenshot(self):
        return self.screenshot.get_property("last-buffer")

    def catch_up_live_stream(self):
        prev_max_size_buffers = self.queue.props.max_size_buffers
        self.queue.props.max_size_buffers = 1

        gst.element_unlink_many(self.source_bin, self.sink_bin)
        self.source_bin.set_state(gst.STATE_NULL)
        self.sink_bin.set_state(gst.STATE_READY)
        self.pipeline.remove(self.source_bin)
        self.source_bin = None
        debug("Attempting to recover from video loss: "
              "Stopping source pipeline and waiting 5s...")
        time.sleep(5)

        debug("Restarting source pipeline...")
        self.source_bin = self.create_source_bin()
        self.pipeline.add(self.source_bin)
        gst.element_link_many(self.source_bin, self.sink_bin)
        self.source_bin.set_state(gst.STATE_PLAYING)
        self.sink_bin.set_state(gst.STATE_PLAYING)
        self.pipeline.set_state(gst.STATE_PLAYING)
        self.start_timestamp = None
        debug("Restarted source pipeline")

        self.queue.props.max_size_buffers = prev_max_size_buffers

    def save_config(self):
        self.last_config['queue.leaky'] = self.queue.props.leaky
        self.last_config['queue.max_size_buffers'] = self.queue.props.max_size_buffers
        self.last_config['queue.max_size_time'] = self.queue.props.max_size_time
        self.last_config['queue.max_size_bytes'] = self.queue.props.max_size_bytes

    def restore_last_saved_config(self):
        self.queue.props.leaky = self.last_config['queue.leaky']
        self.queue.props.max_size_buffers = self.last_config['queue.max_size_buffers']
        self.queue.props.max_size_time = self.last_config['queue.max_size_time']
        self.queue.props.max_size_bytes = self.last_config['queue.max_size_bytes']

    @contextmanager
    def process_all_frames(self):
        """Temporarily set the pipeline to non leaky.
        """
        self.save_config()
        self.queue.disconnect(self.underrun_handler_id)
        self.queue.props.max_size_buffers = 0
        self.queue.props.max_size_time = 0
        self.queue.props.max_size_bytes = 0
        self.queue.props.leaky = 0
        yield
        self.restore_last_saved_config()
        self.underrun_handler_id = self.queue.connect("underrun", self.on_underrun)
        self.catch_up_live_stream()

    def detect(self, element_name, params, timeout_secs):
        """Generator that yields the messages emitted by the named gstreamer
        element configured with the parameters `params`.

        "element_name" is the name of the gstreamer element as specified in the
        pipeline. The name must be the same in the pipeline and in the messages
        returned by gstreamer.

        "params" is a dictionary of parameters to setup the element. The
        original parameters will be restored at the end of the call.

        "timeout_secs" is in seconds elapsed, from the method call. Note that
        you can also simply stop iterating over the sequence yielded by this
        method.

        For every frame processed, returns a tuple: (message, screenshot).
        """

        element = self.pipeline.get_by_name(element_name)

        params_backup = {}
        for key in params.keys():
            params_backup[key] = getattr(element.props, key)

        try:
            for key in params.keys():
                setattr(element.props, key, params[key])

            # Timeout after 10s in case no messages are received on the bus.
            # This happens when starting a new instance of stbt when the
            # Hauppauge HDPVR video-capture device fails to run.
            with GObjectTimeout(timeout_secs=10, handler=self.on_timeout) as t:
                self.test_timeout = t

                self.start_timestamp = None
                for message in MessageIterator(self.bus, "message::element"):
                    # Cancel test_timeout as messages are obviously received.
                    if self.test_timeout:
                        self.test_timeout.cancel()
                        self.test_timeout = None

                    st = message.structure
                    if st.get_name() == element_name:
                        buf = self.screenshot.get_property("last-buffer")
                        if not buf:
                            continue

                        if not self.start_timestamp:
                            self.start_timestamp = buf.timestamp
                        if (buf.timestamp - self.start_timestamp >
                                timeout_secs * 1000000000):
                            return

                        yield (st, buf)

        finally:
            for key in params.keys():
                setattr(element.props, key, params_backup[key])

    def on_timeout(self):
        debug("Timed out")
        _mainloop.quit()
        return False  # stop the timeout from running again

    def on_error(self, bus, message):
        assert message.type == gst.MESSAGE_ERROR
        err, dbg = message.parse_error()
        sys.stderr.write("Error: %s: %s\n%s\n" % (err, err.message, dbg))
        sys.exit(1)

    def on_warning(self, bus, message):
        assert message.type == gst.MESSAGE_WARNING
        err, dbg = message.parse_warning()
        sys.stderr.write("Warning: %s: %s\n%s\n" % (err, err.message, dbg))
        if (err.message == "OpenCV failed to load template image" or
                err.message == "OpenCV failed to load mask image"):
            sys.stderr.write("Error: %s\n" % err.message)
            sys.exit(1)

    def on_underrun(self, element):
        # Cancel test_timeout as messages are obviously received on the bus.
        if self.test_timeout:
            self.test_timeout.cancel()
            self.test_timeout = None

        if self.underrun_timeout:
            ddebug("underrun: I already saw a recent underrun; ignoring")
        else:
            ddebug("underrun: scheduling 'restart_source_bin' in 2s")
            self.underrun_timeout = GObjectTimeout(2, self.restart_source_bin)
            self.underrun_timeout.start()

    def on_running(self, element):
        # Cancel test_timeout as messages are obviously received on the bus.
        if self.test_timeout:
            self.test_timeout.cancel()
            self.test_timeout = None

        if self.underrun_timeout:
            ddebug("running: cancelling underrun timer")
            self.successive_underruns = 0
            self.underrun_timeout.cancel()
            self.underrun_timeout = None
        else:
            ddebug("running: no outstanding underrun timers; ignoring")

    def get_live_stream_timestamp(self):
        buf = self.capture_live_stream_screenshot()
        if not buf:
            raise Exception("get_live_stream_timestamp: no buffer available.")
        return buf.timestamp

    def restart_source_bin(self):
        self.successive_underruns += 1
        if self.successive_underruns > 3:
            sys.stderr.write("Error: Video loss. Too many underruns.\n")
            sys.exit(1)

        gst.element_unlink_many(self.source_bin, self.sink_bin)
        self.source_bin.set_state(gst.STATE_NULL)
        self.sink_bin.set_state(gst.STATE_READY)
        self.pipeline.remove(self.source_bin)
        self.source_bin = None
        debug("Attempting to recover from video loss: "
              "Stopping source pipeline and waiting 5s...")
        time.sleep(5)

        debug("Restarting source pipeline...")
        self.source_bin = self.create_source_bin()
        self.pipeline.add(self.source_bin)
        gst.element_link_many(self.source_bin, self.sink_bin)
        self.source_bin.set_state(gst.STATE_PLAYING)
        self.sink_bin.set_state(gst.STATE_PLAYING)
        self.pipeline.set_state(gst.STATE_PLAYING)
        self.start_timestamp = None
        debug("Restarted source pipeline")

        self.underrun_timeout.start()

        return False  # stop the timeout from running again

    def teardown(self):
        if self.pipeline:
            self.pipeline.send_event(gst.event_new_eos())
            self.pipeline.set_state(gst.STATE_NULL)


class GObjectTimeout:
    """Responsible for setting a timeout in the GTK main loop.

    Can be used as a Context Manager in a 'with' statement.
    """
    def __init__(self, timeout_secs, handler, *args):
        self.timeout_secs = timeout_secs
        self.handler = handler
        self.args = args
        self.timeout_id = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        self.cancel()

    def start(self):
        self.timeout_id = gobject.timeout_add(
            self.timeout_secs * 1000, self.handler, *self.args)

    def cancel(self):
        if self.timeout_id:
            gobject.source_remove(self.timeout_id)
        self.timeout_id = None


def uri_to_remote(uri, display):
    if uri.lower() == 'none':
        return NullRemote()
    if uri.lower() == 'test':
        return VideoTestSrcControl(display)
    vr = re.match(r'vr:(?P<hostname>[^:]*)(:(?P<port>\d+))?', uri)
    if vr:
        d = vr.groupdict()
        return VirtualRemote(d['hostname'], int(d['port'] or 2033))
    lirc = re.match(r'lirc:(?P<lircd_socket>[^:]*):(?P<control_name>.*)', uri)
    if lirc:
        d = lirc.groupdict()
        return LircRemote(d['lircd_socket'] or '/var/run/lirc/lircd',
                          d['control_name'])
    irnb = re.match(
        r'irnetbox:(?P<hostname>[^:]+):(?P<output>\d+):(?P<config>.+)', uri)
    if irnb:
        d = irnb.groupdict()
        return IRNetBoxRemote(d['hostname'], d['output'], d['config'])
    raise ConfigurationError('Invalid remote control URI: "%s"' % uri)


class NullRemote:
    def press(self, key):
        debug('NullRemote: Ignoring request to press "%s"' % key)


class VideoTestSrcControl:
    """Remote control used by selftests.

    Changes the videotestsrc image to the specified pattern ("0" to "20").
    See `gst-inspect videotestsrc`.
    """
    def __init__(self, display):
        self.videosrc = display.pipeline.get_by_name("videotestsrc0")
        if not self.videosrc:
            raise ConfigurationError('The "test" control can only be used'
                                     'with source-pipeline = "videotestsrc"')

    def press(self, key):
        if key not in [str(x) for x in range(21)]:
            raise UITestFailure('Key "%s" not valid for the "test" control'
                                ' (only "0" to "20" allowed)' % key)
        self.videosrc.props.pattern = int(key)
        debug("Pressed " + key)


class VirtualRemote:
    """Send a key-press to a set-top box running a VirtualRemote listener.

        control = VirtualRemote("192.168.0.123")
        control.press("MENU")
    """
    def __init__(self, hostname, port):
        self.hostname = hostname
        self.port = port
        # Connect once so that the test fails immediately if STB not found
        # (instead of failing at the first `press` in the script).
        debug("VirtualRemote: Connecting to %s:%d" % (hostname, port))
        self._connect()
        debug("VirtualRemote: Connected to %s:%d" % (hostname, port))

    def press(self, key):
        self._connect().sendall(
            "D\t%s\n\0U\t%s\n\0" % (key, key))  # key Down, then Up
        debug("Pressed " + key)

    def _connect(self):
        try:
            s = socket.socket()
            s.settimeout(3)
            s.connect((self.hostname, self.port))
            return s
        except socket.error as e:
            e.args = (("Failed to connect to VirtualRemote at %s:%d: %s" % (
                self.hostname, self.port, e)),)
            e.strerror = e.args[0]
            raise


class LircRemote:
    """Send a key-press via a LIRC-enabled infrared blaster.

    See http://www.lirc.org/html/technical.html#applications
    """
    def __init__(self, lircd_socket, control_name):
        self.lircd_socket = lircd_socket
        self.control_name = control_name
        # Connect once so that the test fails immediately if Lirc isn't running
        # (instead of failing at the first `press` in the script).
        debug("LircRemote: Connecting to %s" % lircd_socket)
        self._connect()
        debug("LircRemote: Connected to %s" % lircd_socket)

    def press(self, key):
        self._connect().sendall("SEND_ONCE %s %s\n" % (self.control_name, key))
        debug("Pressed " + key)

    def _connect(self):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect(self.lircd_socket)
            s.settimeout(None)
            return s
        except socket.error as e:
            e.args = (("Failed to connect to Lirc socket %s: %s" % (
                self.lircd_socket, e)),)
            e.strerror = e.args[0]
            raise


class IRNetBoxRemote:
    """Send a key-press via the network-controlled RedRat IRNetBox IR emitter.

    See http://www.redrat.co.uk/products/irnetbox.html

    """
    def __init__(self, hostname, output, config_file):
        self.hostname = hostname
        self.output = int(output)
        self.config = irnetbox.RemoteControlConfig(config_file)
        # Connect once so that the test fails immediately if irNetBox not found
        # (instead of failing at the first `press` in the script).
        debug("IRNetBoxRemote: Connecting to %s" % hostname)
        with self._connect() as irnb:
            irnb.power_on()
        time.sleep(0.5)
        debug("IRNetBoxRemote: Connected to %s" % hostname)

    def press(self, key):
        with self._connect() as irnb:
            irnb.irsend_raw(
                port=self.output, power=100, data=self.config[key])
        time.sleep(0.5)
        debug("Pressed " + key)

    def _connect(self):
        try:
            return irnetbox.IRNetBox(self.hostname)
        except socket.error as e:
            e.args = (("Failed to connect to IRNetBox %s: %s" % (
                self.hostname, e)),)
            e.strerror = e.args[0]
            raise


def uri_to_remote_recorder(uri):
    vr = re.match(r'vr:(?P<hostname>[^:]*)(:(?P<port>\d+))?', uri)
    if vr:
        d = vr.groupdict()
        return virtual_remote_listen(d['hostname'], int(d['port'] or 2033))
    lirc = re.match(r'lirc:(?P<lircd_socket>[^:]*):(?P<control_name>.*)', uri)
    if lirc:
        d = lirc.groupdict()
        return lirc_remote_listen(d['lircd_socket'] or '/var/run/lirc/lircd',
                                  d['control_name'])
    f = re.match('file://(?P<filename>.+)', uri)
    if f:
        return file_remote_recorder(f.group('filename'))
    raise ConfigurationError('Invalid remote control recorder URI: "%s"' % uri)


def file_remote_recorder(filename):
    """ A generator that returns lines from the file given by filename.

    Unfortunately treating a file as a iterator doesn't work in the case of
    interactive input, even when we provide bufsize=1 (line buffered) to the
    call to open() so we have to have this function to work around it. """
    f = open(filename, 'r')
    if filename == '/dev/stdin':
        sys.stderr.write('Waiting for keypresses from standard input...\n')
    while True:
        line = f.readline()
        if line == '':
            f.close()
            raise StopIteration
        yield line.rstrip()


def read_records(stream, sep):
    r"""Generator that splits stream into records given a separator

    >>> import StringIO
    >>> s = StringIO.StringIO('hello\n\0This\n\0is\n\0a\n\0test\n\0')
    >>> list(read_records(FileToSocket(s), '\n\0'))
    ['hello', 'This', 'is', 'a', 'test']
    """
    buf = ""
    while True:
        s = stream.recv(4096)
        if len(s) == 0:
            break
        buf += s
        cmds = buf.split(sep)
        buf = cmds[-1]
        for i in cmds[:-1]:
            yield i


def vr_key_reader(cmd_iter):
    r"""Converts virtual remote records into list of keypresses

    >>> list(vr_key_reader(['D\tHELLO', 'U\tHELLO']))
    ['HELLO']
    >>> list(vr_key_reader(['D\tCHEESE', 'D\tHELLO', 'U\tHELLO', 'U\tCHEESE']))
    ['HELLO', 'CHEESE']
    """
    for i in cmd_iter:
        (action, key) = i.split('\t')
        if action == 'U':
            yield key


def virtual_remote_listen(address, port):
    """Waits for a VirtualRemote to connect, and returns an iterator yielding
    keypresses."""
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind((address, port))
    serversocket.listen(5)
    sys.stderr.write("Waiting for connection from virtual remote control "
                     "on %s:%d...\n" % (address, port))
    (connection, address) = serversocket.accept()
    sys.stderr.write("Accepted connection from %s\n" % str(address))
    return vr_key_reader(read_records(connection, '\n\0'))


def lirc_remote_listen(lircd_socket, control_name):
    """Returns an iterator yielding keypresses received from lircd.

    See http://www.lirc.org/html/technical.html#applications
    """
    lircd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    debug("control-recorder connecting to lirc socket '%s'..." % lircd_socket)
    lircd.connect(lircd_socket)
    debug("control-recorder connected to lirc socket")
    return lirc_key_reader(lircd.makefile(), control_name)


def lirc_key_reader(cmd_iter, control_name):
    r"""Convert lircd messages into list of keypresses

    >>> list(lirc_key_reader(['0000dead 00 MENU My-IR-remote',
    ...                       '0000beef 00 OK My-IR-remote',
    ...                       '0000f00b 01 OK My-IR-remote',
    ...                       'BEGIN', 'SIGHUP', 'END'],
    ...                      'My-IR-remote'))
    ['MENU', 'OK']
    """
    for s in cmd_iter:
        debug("lirc_key_reader received: %s" % s.rstrip())
        m = re.match(
            r"\w+ (?P<repeat_count>\d+) (?P<key>\w+) %s" % control_name,
            s)
        if m and int(m.group('repeat_count')) == 0:
            yield m.group('key')


def load_config(tool):
    global _config
    if not _config:
        _config = ConfigParser.SafeConfigParser()

        # When run from the installed location (as `stbt run`), will read from
        # $SYSCONFDIR/stbt/stbt.conf (see `stbt.in`); when run from the source
        # directory (as `stbt-run`) will read config from the source directory.
        system_config = os.environ.get(
            'STBT_SYSTEM_CONFIG',
            os.path.join(os.path.dirname(__file__), 'stbt.conf'))

        files_read = _config.read([
            system_config,
            # User config: ~/.config/stbt/stbt.conf, as per freedesktop's base
            # directory specification:
            '%s/stbt/stbt.conf' % os.environ.get(
                'XDG_CONFIG_HOME', '%s/.config' % os.environ['HOME']),
            # Config files specific to the test suite / test run:
            os.environ.get('STBT_CONFIG_FILE', ''),
        ])
        assert(system_config in files_read)

    return dict(
        _config.items('global'),
        **dict(_config.items(tool)) if tool else {})


def _find_path(image):
    """Searches for the given filename and returns the full path.

    Searches in the directory of the script that called (for example)
    detect_match, then in the directory of that script's caller, etc.
    """

    if os.path.isabs(image):
        return image

    # stack()[0] is _find_path;
    # stack()[1] is _find_path's caller, e.g. detect_match;
    # stack()[2] is detect_match's caller (the user script).
    for caller in inspect.stack()[2:]:
        caller_image = os.path.join(
            os.path.dirname(inspect.getframeinfo(caller[0]).filename),
            image)
        if os.path.isfile(caller_image):
            return os.path.abspath(caller_image)

    # Fall back to image from cwd, for convenience of the selftests
    return os.path.abspath(image)


def _mkdir(d):
    try:
        os.makedirs(d)
    except OSError, e:
        if e.errno != errno.EEXIST:
            return False
    return os.path.isdir(d) and os.access(d, os.R_OK | os.W_OK)


def ddebug(s):
    """Extra verbose debug for stbt developers, not end users"""
    if _debug_level > 1:
        sys.stderr.write("%s: %s\n" % (os.path.basename(sys.argv[0]), str(s)))


def warn(s):
    sys.stderr.write("%s: warning: %s\n" % (
        os.path.basename(sys.argv[0]), str(s)))


# Tests
#===========================================================================

class FileToSocket:
    """Makes something File-like behave like a Socket for testing purposes

    >>> import StringIO
    >>> s = FileToSocket(StringIO.StringIO("Hello"))
    >>> s.recv(3)
    'Hel'
    >>> s.recv(3)
    'lo'
    """
    def __init__(self, f):
        self.file = f

    def recv(self, bufsize, flags=0):
        return self.file.read(bufsize)


def test_that_virtual_remote_is_symmetric_with_virtual_remote_listen():
    import threading

    received = []
    keys = ['DOWN', 'DOWN', 'UP', 'GOODBYE']

    def listener():
        # "* 2" is once for VirtualRemote's __init__ and once for press.
        for _ in range(len(keys) * 2):
            for k in virtual_remote_listen('localhost', 2033):
                received.append(k)

    t = threading.Thread()
    t.run = listener
    t.start()
    for k in keys:
        time.sleep(0.01)  # Give listener a chance to start listening (sorry)
        vr = VirtualRemote('localhost', 2033)
        time.sleep(0.01)
        vr.press(k)
    t.join()
    assert received == keys


def test_that_lirc_remote_is_symmetric_with_lirc_remote_listen():
    import tempfile
    import threading

    keys = ['DOWN', 'DOWN', 'UP', 'GOODBYE']

    def fake_lircd(address):
        # This needs to accept 2 connections (from LircRemote and
        # lirc_remote_listen) and, on receiving input from the LircRemote
        # connection, write to the lirc_remote_listen connection.
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(address)
        s.listen(5)
        listener, _ = s.accept()
        # "* 1" is for LircRemote's __init__.
        for _ in range(len(keys) + 1):
            control, _ = s.accept()
            for cmd in control.makefile():
                m = re.match(r'SEND_ONCE (?P<control>\w+) (?P<key>\w+)', cmd)
                if m:
                    d = m.groupdict()
                    listener.sendall(
                        '00000000 0 %s %s\n' % (d['key'], d['control']))

    lircd_socket = tempfile.mktemp()
    t = threading.Thread()
    t.run = lambda: fake_lircd(lircd_socket)
    t.start()
    time.sleep(0.01)  # Give it a chance to start listening (sorry)
    listener = lirc_remote_listen(lircd_socket, 'test')
    control = LircRemote(lircd_socket, 'test')
    for i in keys:
        control.press(i)
        assert listener.next() == i
    t.join()
