from collections import namedtuple
import argparse
import ConfigParser
import Queue
import errno
import inspect
import os
import re
import socket
import sys
import time


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

with ArgvHider():
    import pygst  # gstreamer
    pygst.require("0.10")
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


class Position(namedtuple('Position', 'x y')):
    """
    * `x` and `y`: Integer coordinates from the top left corner of the video
      frame.
    """
    pass


class MatchResult(
    namedtuple('MatchResult', 'timestamp match position first_pass_result')):
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
            result = MatchResult(timestamp=buf.timestamp,
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


def detect_motion(timeout_secs=10, mask=None):
    """Generator that yields a sequence of one `MotionResult` for each frame
    processed from the source video stream.

    Returns after `timeout_secs` seconds. (Note that the caller can also choose
    to stop iterating over this function's results at any time.)

    `mask` is a black and white image that specifies which part of the image
    to search for motion. White pixels select the area to search; black pixels
    the area to ignore.
    """

    debug("Searching for motion")
    params = {"enabled": True}
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
            debug("%s detected. Timestamp: %d." %
                ("Motion" if result.motion else "No motion", result.timestamp))
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

    screenshot = display.capture_screenshot()
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


def wait_for_motion(timeout_secs=10, consecutive_frames=10, mask=None):
    """Search for motion in the source video stream.

    Returns `MotionResult` when motion is detected.
    Raises `MotionTimeout` if no motion is detected after `timeout_secs`
    seconds.

    Considers the video stream to have motion if there were differences between
    10 consecutive frames (or the number specified with `consecutive_frames`).

    `mask` is a black and white image that specifies which part of the image
    to search for motion. White pixels select the area to search; black pixels
    the area to ignore.
    """
    debug("Waiting for %d consecutive frames with motion" % consecutive_frames)
    consecutive_frames_count = 0
    for res in detect_motion(timeout_secs, mask):
        if res.motion:
            consecutive_frames_count += 1
        else:
            consecutive_frames_count = 0
        if consecutive_frames_count == consecutive_frames:
            debug("Motion detected.")
            return res

    screenshot = display.capture_screenshot()
    raise MotionTimeout(screenshot, mask, timeout_secs)


def save_frame(buf, filename):
    '''Save a gstreamer buffer to the specified file in png format.'''
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


class ConfigurationError(UITestError):
    pass


# stbt-run initialisation and convenience functions
# (you will need these if writing your own version of stbt-run)
#===========================================================================

def argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--control',
        help='The remote control to control the stb (default: %(default)s)')
    parser.add_argument('--source-pipeline',
        help='A gstreamer pipeline to use for A/V input (default: '
             '%(default)s)')
    parser.add_argument('--sink-pipeline',
        help='A gstreamer pipeline to use for video output '
             '(default: %(default)s)')

    class IncreaseDebugLevel(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            global _debug_level
            _debug_level += 1
            setattr(namespace, self.dest, _debug_level)

    global _debug_level
    _debug_level = 0
    parser.add_argument('-v', '--verbose', action=IncreaseDebugLevel, nargs=0,
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
                imageprocessing,
                "! tee name=t",
                "t. ! queue leaky=2 !", screenshot,
                "t. ! queue leaky=2 !", xvideo
                ])

        # Gstreamer loads plugin libraries on demand, when elements that need
        # those libraries are first mentioned. There is a bug in gst-opencv
        # where it erroneously claims to provide appsink, preventing the
        # loading of the real appsink -- so we load it first.
        # TODO: Fix gst-opencv so that it doesn't prevent appsink from being
        #       loaded.
        gst.parse_launch("appsink")

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
        self.test_timeout = None
        self.successive_underruns = 0
        self.underrun_timeout = None
        self.queue.connect("underrun", self.on_underrun)
        self.queue.connect("running", self.on_running)

    def create_source_bin(self):
        source_bin = gst.parse_bin_from_description(
            self.source_pipeline_description +
                " ! capsfilter name=padforcer caps=video/x-raw-yuv",
            False)
        source_bin.add_pad(
            gst.GhostPad(
                "source",
                source_bin.get_by_name("padforcer").src_pads().next()))
        return source_bin

    def capture_screenshot(self):
        return self.screenshot.get_property("last-buffer")

    def detect(self, element_name, params, timeout_secs):
        """Generator that yields the messages emitted by the named gstreamer
        element configured with the parameters `params`.

        "element_name" is the name of the gstreamer element as specified in the
        pipeline. The name must be the same in the pipeline and in the messages
        returned by gstreamer.

        "params" is a dictionary of parameters to setup the element. The
        original parameters will be restored at the end of the call.

        "timeout_secs" is in seconds elapsed, from the method call. Note that
        stopping iterating also enables to interrupt the method.

        For every frame processed, a tuple is returned: (message, screenshot).
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

                start_timestamp = None
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

                        if not start_timestamp:
                            start_timestamp = buf.timestamp
                        if (buf.timestamp - start_timestamp >
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
        self.pipeline.set_state(gst.STATE_PLAYING)
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
        self.s = socket.socket()
        debug("VirtualRemote: Connecting to %s:%d" % (hostname, port))
        try:
            self.s.settimeout(3)
            self.s.connect((hostname, port))
            self.s.settimeout(None)
            debug("VirtualRemote: Connected to %s:%d" % (hostname, port))
        except socket.error as e:
            e.args = (("Failed to connect to VirtualRemote at %s:%d: %s" % (
                hostname, port, e)),)
            e.strerror = e.args[0]
            raise

    def press(self, key):
        self.s.send("D\t%s\n\0U\t%s\n\0" % (key, key))  # key Down, then key Up
        debug("Pressed " + key)

    def close(self):
        self.s.close()
        self.s = None


class LircRemote:
    """Send a key-press via a LIRC-enabled infrared blaster.

    See http://www.lirc.org/html/technical.html#applications
    """
    def __init__(self, lircd_socket, control_name):
        self.control_name = control_name
        self.lircd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        debug("LircRemote: Connecting to %s" % lircd_socket)
        try:
            self.lircd.settimeout(3)
            self.lircd.connect(lircd_socket)
            self.lircd.settimeout(None)
            debug("LircRemote: Connected to %s" % lircd_socket)
        except socket.error as e:
            e.args = (("Failed to connect to Lirc socket %s: %s" % (
                        lircd_socket, e)),)
            e.strerror = e.args[0]
            raise

    def press(self, key):
        self.lircd.send("SEND_ONCE %s %s\n" % (self.control_name, key))
        debug("Pressed " + key)

    def close(self):
        self.lircd.close()
        self.lircd = None


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
    l = len(sep)
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
        m = re.match(r"\w+ (?P<repeat_count>\d+) (?P<key>\w+) %s" %
                         control_name,
                     s)
        if m and int(m.group('repeat_count')) == 0:
            yield m.group('key')


def load_defaults(tool):
    conffile = ConfigParser.SafeConfigParser()
    conffile.add_section('global')
    conffile.add_section(tool)

    # When run from the installed location (as `stbt run`), will read config
    # from $SYSCONFDIR/stbt/stbt.conf (see `stbt.in`); when run from the source
    # directory (as `stbt-run`) will read config from the source directory.
    system_config = os.environ.get(
        'STBT_SYSTEM_CONFIG',
        os.path.join(os.path.dirname(__file__), 'stbt.conf'))

    files_read = conffile.read([
        system_config,
        # User config: ~/.config/stbt/stbt.conf, as per freedesktop's base
        # directory specification:
        '%s/stbt/stbt.conf' % os.environ.get('XDG_CONFIG_HOME',
                                            '%s/.config' % os.environ['HOME']),
        # Config files specific to the test suite / test run:
        os.environ.get('STBT_CONFIG_FILE', ''),
        ])
    assert(system_config in files_read)
    return dict(conffile.items('global'), **dict(conffile.items(tool)))


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


def debug(s):
    if _debug_level > 0:
        sys.stderr.write("%s: %s\n" % (os.path.basename(sys.argv[0]), str(s)))


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
    import time
    t = threading.Thread()
    vrl = []
    t.run = lambda: vrl.append(virtual_remote_listen('localhost', 2033))
    t.start()
    time.sleep(0.01)  # Give it a chance to start listening (sorry)
    vr = VirtualRemote('localhost', 2033)
    t.join()
    for i in ['DOWN', 'DOWN', 'UP', 'GOODBYE']:
        vr.press(i)
    vr.close()
    assert list(vrl[0]) == ['DOWN', 'DOWN', 'UP', 'GOODBYE']


def fake_lircd(address):
    import tempfile

    # This needs to accept 2 connections (from LircRemote and
    # lirc_remote_listen) and, on receiving input from the LircRemote
    # connection, write to the lirc_remote_listen connection.
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(address)
    s.listen(5)
    listener, _ = s.accept()
    control, _ = s.accept()
    for cmd in control.makefile():
        m = re.match(r'SEND_ONCE (?P<control>\w+) (?P<key>\w+)', cmd)
        if m:
            d = m.groupdict()
            listener.send('00000000 0 %s %s\n' % (d['key'], d['control']))


def test_that_lirc_remote_is_symmetric_with_lirc_remote_listen():
    import tempfile
    import threading
    import time

    lircd_socket = tempfile.mktemp()
    t = threading.Thread()
    t.run = lambda: fake_lircd(lircd_socket)
    t.start()
    time.sleep(0.01)  # Give it a chance to start listening (sorry)
    listener = lirc_remote_listen(lircd_socket, 'test')
    control = LircRemote(lircd_socket, 'test')
    for i in ['DOWN', 'DOWN', 'UP', 'GOODBYE']:
        control.press(i)
        assert listener.next() == i
    control.close()
    t.join()
