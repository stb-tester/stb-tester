"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/drothlis/stb-tester/blob/master/LICENSE for details).
"""

from collections import namedtuple, deque
import argparse
import ConfigParser
import contextlib
import Queue
import errno
import inspect
import os
import re
import socket
import sys
import time
import warnings

import irnetbox


@contextlib.contextmanager
def hide_argv():
    """ For use with 'with' statement: Provides a context with an empty
    argument list.

    This is used because otherwise gst-python will exit if '-h', '--help', '-v'
    or '--version' command line arguments are given.
    """
    old_argv = sys.argv[:]
    sys.argv = [sys.argv[0]]
    try:
        yield
    finally:
        sys.argv = old_argv


@contextlib.contextmanager
def hide_stderr():
    """For use with 'with' statement: Hide stderr output.

    This is used because otherwise gst-python will print
    'pygobject_register_sinkfunc is deprecated'.
    """
    fd = sys.__stderr__.fileno()
    saved_fd = os.dup(fd)
    sys.__stderr__.flush()
    null_stream = open(os.devnull, 'w', 0)
    os.dup2(null_stream.fileno(), fd)
    try:
        yield
    finally:
        sys.__stderr__.flush()
        os.dup2(saved_fd, sys.__stderr__.fileno())
        null_stream.close()


import pygst  # gstreamer
pygst.require("0.10")
with hide_argv(), hide_stderr():
    import gst
import gobject
import glib


warnings.filterwarnings(
    action="always", category=DeprecationWarning, module='stbt')


_config = None


# Functions available to stbt scripts
#===========================================================================

def get_config(key, section='global'):
    """Read the value of `key` from `section` of the stbt config file.

    See 'CONFIGURATION' in the stbt(1) man page for the config file search
    path.

    Raises `ConfigurationError` if the specified `section` or `key` is not
    found.
    """

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

    try:
        return _config.get(section, key)
    except ConfigParser.Error as e:
        raise ConfigurationError(e.message)


def press(key):
    """Send the specified key-press to the system under test.

    The mechanism used to send the key-press depends on what you've configured
    with `--control`.

    `key` is a string. The allowed values depend on the control you're using:
    If that's lirc, then `key` is a key name from your lirc config file.
    """
    return _control.press(key)


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


def detect_match(image, timeout_secs=10, noise_threshold=None, **kwargs):
    """Generator that yields a sequence of one `MatchResult` for each frame
    processed from the source video stream.

    Returns after `timeout_secs` seconds. (Note that the caller can also choose
    to stop iterating over this function's results at any time.)

    The templatematch parameter `noise_threshold` is marked for deprecation
    but appears in the args for backward compatibility with positional
    argument syntax. It is now a synonym for `confirm_threshold`. Please use
    `confirm_threshold` from now on.

    Any other keyword arguments passed to the function using `kwargs` will be
    used to customise the templatematch algorithm parameters. If no
    templatematch arguments are explicitly passed, then the default values
    from `stbt.conf` will be used instead.

    See the section `CUSTOMISING THE TEMPLATEMATCH ALGORITHM`_ (in the
    README.rst or man page) for a description of all templatematch parameters.
    """

    templatematch_params = build_templatematch_params(
        noise_threshold=noise_threshold, **kwargs)

    properties = {  # Properties of GStreamer element
        "template": _find_path(image),
        "matchMethod": templatematch_params['match_method'],
        "matchThreshold": templatematch_params['match_threshold'],
        "confirmMethod": templatematch_params['confirm_method'],
        "erodePasses": templatematch_params['erode_passes'],
        "confirmThreshold": templatematch_params['confirm_threshold'],
    }
    debug("Searching for " + properties["template"])
    if not os.path.isfile(properties["template"]):
        raise UITestError("No such template file: %s" % image)

    for message, buf in _display.detect(
            "template_match", properties, timeout_secs):
        # Discard messages generated from previous call with different template
        if message["template_path"] == properties["template"]:
            result = MatchResult(
                timestamp=buf.timestamp,
                match=message["match"],
                position=Position(message["x"], message["y"]),
                first_pass_result=message["first_pass_result"])
            # pylint: disable=E1101
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
    properties = {  # Properties of GStreamer element
        "enabled": True,
        "noiseThreshold": noise_threshold,
    }
    if mask:
        properties["mask"] = _find_path(mask)
        debug("Using mask %s" % (properties["mask"]))
        if not os.path.isfile(properties["mask"]):
            debug("No such mask file: %s" % mask)
            raise UITestError("No such mask file: %s" % mask)

    for msg, buf in _display.detect("motiondetect", properties, timeout_secs):
        # Discard messages generated from previous calls with a different mask
        if ((mask and msg["masked"] and msg["mask_path"] == properties["mask"])
                or (not mask and not msg["masked"])):
            result = MotionResult(timestamp=buf.timestamp,
                                  motion=msg["has_motion"])
            # pylint: disable=E1101
            debug("%s detected. Timestamp: %d." % (
                "Motion" if result.motion else "No motion", result.timestamp))
            yield result


def wait_for_match(image, timeout_secs=10, consecutive_matches=1,
                   noise_threshold=None, **kwargs):
    """Search for `image` in the source video stream.

    Returns `MatchResult` when `image` is found.
    Raises `MatchTimeout` if no match is found after `timeout_secs` seconds.

    `consecutive_matches` forces this function to wait for several consecutive
    frames with a match found at the same x,y position. Increase
    `consecutive_matches` to avoid false positives due to noise.

    The templatematch parameter `noise_threshold` is marked for deprecation
    but appears in the args for backward compatibility with positional
    argument syntax. It is now a synonym for `confirm_threshold`. Please use
    `confirm_threshold` from now on.

    Any other keyword arguments passed to the function using `kwargs` will be
    used to customise the templatematch algorithm parameters. If no
    templatematch arguments are explicitly passed, then the default values
    from `stbt.conf` will be used instead.

    See the section `CUSTOMISING THE TEMPLATEMATCH ALGORITHM`_ (in the
    README.rst or man page) for a description of all templatematch parameters.
    """

    match_count = 0
    last_pos = Position(0, 0)
    for res in detect_match(
            image, timeout_secs, noise_threshold=noise_threshold, **kwargs):
        if res.match and (match_count == 0 or res.position == last_pos):
            match_count += 1
        else:
            match_count = 0
        last_pos = res.position
        if match_count == consecutive_matches:
            debug("Matched " + image)
            return res

    screenshot = _display.capture_screenshot()
    raise MatchTimeout(screenshot, image, timeout_secs)


def press_until_match(key, image, interval_secs=3, noise_threshold=None,
                      max_presses=10, **kwargs):
    """Calls `press` as many times as necessary to find the specified `image`.

    Returns `MatchResult` when `image` is found.
    Raises `MatchTimeout` if no match is found after `max_presses` times.

    `interval_secs` is the number of seconds to wait for a match before
    pressing again.

    The templatematch parameter `noise_threshold` is marked for deprecation
    but appears in the args for backward compatibility with positional
    argument syntax. It is now a synonym for `confirm_threshold`. Please use
    `confirm_threshold` from now on.

    Any other keyword arguments passed to the function using `kwargs` will be
    used to customise the templatematch algorithm parameters. If no
    templatematch arguments are explicitly passed, then the default values
    from `stbt.conf` will be used instead.

    See the section `CUSTOMISING THE TEMPLATEMATCH ALGORITHM`_ (in the
    README.rst or man page) for a description of all templatematch parameters.
    """

    i = 0

    while True:
        try:
            return wait_for_match(image, timeout_secs=interval_secs,
                                  noise_threshold=noise_threshold, **kwargs)
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

    screenshot = _display.capture_screenshot()
    raise MotionTimeout(screenshot, mask, timeout_secs)


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
    return _display.capture_screenshot()


def debug(msg):
    """Print the given string to stderr if stbt run `--verbose` was given."""
    if _debug_level > 0:
        sys.stderr.write(
            "%s: %s\n" % (os.path.basename(sys.argv[0]), str(msg)))


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
        super(MatchTimeout, self).__init__()
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
        super(MotionTimeout, self).__init__()
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
        default=get_config('control', section='global'),
        help='The remote control to control the stb (default: %(default)s)')
    parser.add_argument(
        '--source-pipeline',
        default=get_config('source_pipeline', section='global'),
        help='A gstreamer pipeline to use for A/V input (default: '
             '%(default)s)')
    parser.add_argument(
        '--sink-pipeline',
        default=get_config('sink_pipeline', section='global'),
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
        default=get_config('verbose', section='global'),
        help='Enable debug output (specify twice to enable GStreamer element '
             'dumps to ./stbt-debug directory)')

    return parser


def init_run(gst_source_pipeline, gst_sink_pipeline, control_uri):
    global _display, _control
    _display = Display(gst_source_pipeline, gst_sink_pipeline)
    _control = uri_to_remote(control_uri, _display)


def teardown_run():
    _display.teardown()


# Internal
#===========================================================================

_debug_level = 0
_mainloop = glib.MainLoop()

_display = None
_control = None


def MessageIterator(bus, signal):
    queue = Queue.Queue()

    def sig(_bus, message):
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
            "stbt-templatematch name=template_match",
        ])
        xvideo = " ! ".join([
            # Convert to a colorspace that xvimagesink can handle:
            "ffmpegcolorspace",
            sink_pipeline_description,
        ])
        screenshot = ("appsink name=screenshot max-buffers=1 drop=true "
                      "sync=false")
        pipe = " ".join([
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
        self.start_timestamp = None
        self.test_timeout = None
        self.successive_underruns = 0
        self.underrun_timeout = None
        self.queue.connect("underrun", self.on_underrun)
        self.queue.connect("running", self.on_running)

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

    def capture_screenshot(self):
        return self.screenshot.get_property("last-buffer")

    def detect(self, element_name, properties, timeout_secs):
        """Generator that yields the messages emitted by the named gstreamer
        element configured with the specified `properties`.

        "element_name" is the name of the gstreamer element as specified in the
        pipeline. The name must be the same in the pipeline and in the messages
        returned by gstreamer.

        "properties" is a dictionary of properties to set on the gstreamer
        element. The original properties will be restored at the end of the
        call.

        "timeout_secs" is in seconds elapsed, from the method call. Note that
        you can also simply stop iterating over the sequence yielded by this
        method.

        For every frame processed, returns a tuple: (message, screenshot).
        """

        element = self.pipeline.get_by_name(element_name)

        properties_backup = {}
        for key in properties.keys():
            properties_backup[key] = getattr(element.props, key)

        try:
            for key in properties.keys():
                setattr(element.props, key, properties[key])

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
            for key in properties.keys():
                setattr(element.props, key, properties_backup[key])

    @staticmethod
    def on_timeout(*_args):
        debug("Timed out")
        _mainloop.quit()
        return False  # stop the timeout from running again

    @staticmethod
    def on_error(_bus, message):
        assert message.type == gst.MESSAGE_ERROR
        err, dbg = message.parse_error()
        sys.stderr.write("Error: %s: %s\n%s\n" % (err, err.message, dbg))
        sys.exit(1)

    @staticmethod
    def on_warning(_bus, message):
        assert message.type == gst.MESSAGE_WARNING
        err, dbg = message.parse_warning()
        sys.stderr.write("Warning: %s: %s\n%s\n" % (err, err.message, dbg))
        if (err.message == "OpenCV failed to load template image" or
                err.message == "OpenCV failed to load mask image"):
            sys.stderr.write("Error: %s\n" % err.message)
            sys.exit(1)

    def on_underrun(self, _element):
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

    def on_running(self, _element):
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

    def __exit__(self, ex_type, ex_value, traceback):
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
    tcp_lirc = re.match(
        r'lirc(:(?P<hostname>[^:]*))?:(?P<port>\d+):(?P<control_name>.*)', uri)
    if tcp_lirc:
        d = tcp_lirc.groupdict()
        return TCPLircRemote(d['hostname'] or 'localhost',
                             int(d['port']), d['control_name'])
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
    @staticmethod
    def press(key):
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
            "D\t%s\n\x00U\t%s\n\x00" % (key, key))  # key Down, then Up
        debug("Pressed " + key)

    def _connect(self):
        return _connect_tcp_socket(self.hostname, self.port)


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
        self._connect().sendall(_lirc_command(self.control_name, key))
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


class TCPLircRemote:
    """Send a key-press via a LIRC-enabled device through a LIRC TCP listener.

        control = TCPLircRemote("localhost", "8765", "humax")
        control.press("MENU")
    """

    def __init__(self, hostname, port, control_name):
        self.hostname = hostname
        self.port = port
        self.control_name = control_name
        # Connect once so that the test fails immediately if lircd isn't bound
        # to the port (instead of failing at the first `press` in the script).
        debug("TCPLircRemote: Connecting to %s:%d" % (hostname, port))
        self._connect()
        debug("TCPLircRemote: Connected to %s:%d" % (hostname, port))

    def press(self, key):
        self._connect().sendall(_lirc_command(self.control_name, key))
        debug("Pressed " + key)

    def _connect(self):
        return _connect_tcp_socket(self.hostname, self.port)


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
    tcp_lirc = re.match(
        r'lirc(:(?P<hostname>[^:]*))?:(?P<port>\d+):(?P<control_name>.*)', uri)
    if tcp_lirc:
        d = tcp_lirc.groupdict()
        return lirc_remote_listen_tcp(d['hostname'] or 'localhost',
                                      int(d['port']), d['control_name'])
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
    return vr_key_reader(read_records(connection, '\n\x00'))


def lirc_remote_listen(lircd_socket, control_name):
    """Returns an iterator yielding keypresses received from a lircd file
    socket.

    See http://www.lirc.org/html/technical.html#applications
    """
    lircd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    debug("control-recorder connecting to lirc file socket '%s'..." %
          lircd_socket)
    lircd.connect(lircd_socket)
    debug("control-recorder connected to lirc file socket")
    return lirc_key_reader(lircd.makefile(), control_name)


def lirc_remote_listen_tcp(address, port, control_name):
    """Returns an iterator yielding keypresses received from a lircd TCP
    socket."""
    debug("control-recorder connecting to lirc TCP socket %s:%s..." %
          (address, port))
    lircd = _connect_tcp_socket(address, port, timeout=None)
    debug("control-recorder connected to lirc TCP socket")
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


def build_templatematch_params(**kwargs):
    """Build and return a dict of complete templatematch parameters.

    Templatematch parameters are looked up in this sequence:
    1. any templatematch params specified in stbt configuration files
    2. any parameters passed in to this function overrides (1)
    """

    # warnings to be removed once noise_threshold is unsupported
    if kwargs.get('noise_threshold') and kwargs.get('confirm_threshold'):
        raise ConfigurationError(
            "`noise_threshold` and `confirm_threshold` "
            "cannot be used together. "
            "`noise_threshold` is marked for deprecation.")
    elif kwargs.get('noise_threshold'):
        warnings.warn(
            "`noise_threshold` is marked for deprecation. "
            "Please use `confirm_threshold` instead.",
            DeprecationWarning, stacklevel=2)
        kwargs['confirm_threshold'] = kwargs.pop('noise_threshold')

    # config-file value -> correctly typed gst pipeline value
    key_type = {'match_method': str,
                'match_threshold': float,
                'confirm_method': str,
                'erode_passes': int,
                'confirm_threshold': float}

    params = {}
    for key, _type in key_type.items():
        params[key] = kwargs.get(
            key,
            _type(get_config(key, section='global')))

    return params


def _connect_tcp_socket(address, port, timeout=3):
    """Connects to a TCP listener on 'address':'port'."""
    try:
        s = socket.socket()
        if timeout:
            s.settimeout(timeout)
        s.connect((address, port))
        return s
    except socket.error as e:
        e.args = (("Failed to connect to remote at %s:%d: %s" % (
            address, port, e)),)
        e.strerror = e.args[0]
        raise


def _lirc_command(control_name, key):
    """Returns a LIRC send key command string."""
    return "SEND_ONCE %s %s\n" % (control_name, key)


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

    def recv(self, bufsize, flags=0):  # pylint: disable=W0613
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
    t.daemon = True
    t.run = listener
    t.start()
    for k in keys:
        time.sleep(0.1)  # Give listener a chance to start listening (sorry)
        vr = VirtualRemote('localhost', 2033)
        time.sleep(0.1)
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
        # "+ 1" is for LircRemote's __init__.
        for _ in range(len(keys) + 1):
            control, _ = s.accept()
            for cmd in control.makefile():
                m = re.match(r'SEND_ONCE (?P<control>\w+) (?P<key>\w+)', cmd)
                if m:
                    d = m.groupdict()
                    message = '00000000 0 %s %s\n' % (d['key'], d['control'])
                    listener.sendall(message)  # pylint: disable=E1101

    lircd_socket = tempfile.mktemp()
    t = threading.Thread()
    t.daemon = True
    t.run = lambda: fake_lircd(lircd_socket)
    t.start()
    time.sleep(0.01)  # Give it a chance to start listening (sorry)
    listener = lirc_remote_listen(lircd_socket, 'test')
    control = LircRemote(lircd_socket, 'test')
    for i in keys:
        control.press(i)
        assert listener.next() == i
    t.join()


def test_build_templatematch_params_detects_undefined():
    global get_config  # pylint: disable=W0601
    _get_config = get_config

    def mock_get_config(key, section='global'):
        # missing 'confirm_threshold'
        try:
            return dict(match_method="sqdiff-normed",
                        match_threshold="0.80",
                        confirm_method="normed-absdiff",
                        erode_passes="1")[key]
        except KeyError:
            raise ConfigurationError(
                "No option '%s' in section: '%s'" % (key, section))

    get_config = mock_get_config
    try:
        build_templatematch_params()
    except ConfigurationError:  # what we expect
        pass
    else:
        assert False            # fail test
    finally:
        get_config = _get_config


def test_build_templatematch_params_uses_kwargs():
    params = build_templatematch_params(erode_passes=-5)
    assert params['erode_passes'] == -5
