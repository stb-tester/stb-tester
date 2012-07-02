import ConfigParser
import os
import re
import sys


class ArgvHider:
    """ For use with 'with' statement:  Unsets argv and resets it.

    This is used because otherwise gst-python will exit if '-h', '--help', '-v'
    or '--version' command line arguments are given.

    Example:
    >>> sys.argv=['test', '--help']
    >>> with ArgvHider():
    ...     import pygst  # gstreamer
    ...     pygst.require("0.10")
    ...     import gst
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
    import gtk  # for main loop


class Display:
    def __init__(self, gst_source_pipeline, gst_sink_pipeline):
        imageprocessing = " ! ".join([
                # Buffer the video stream, dropping frames if downstream
                # processors aren't fast enough:
                "queue leaky=2",
                # Convert to a colorspace that templatematch can handle:
                "ffmpegcolorspace",
                # OpenCV image-processing library:
                "templatematch name=templatematch method=1",
                ])
        xvideo = " ! ".join([
                # Convert to a colorspace that xvimagesink can handle:
                "ffmpegcolorspace",
                gst_sink_pipeline,
                ])
        screenshot = ("appsink name=screenshot max-buffers=1 drop=true "
                      "sync=false")
        pipe = " ".join([
                gst_source_pipeline,
                "!", imageprocessing,
                "! tee name=t",
                "! queue leaky=2 !", screenshot,
                "t. ! queue leaky=2 !", xvideo
                ])

        # Gstreamer loads plugin libraries on demand, when elements that need
        # those libraries are first mentioned. There is a bug in gst-opencv
        # where it erroneously claims to provide appsink, preventing the
        # loading of the real appsink -- so we load it first.
        # TODO: Fix gst-opencv so that it doesn't prevent appsink from being
        #       loaded.
        gst.parse_launch("appsink")

        self.pipeline = gst.parse_launch(pipe)
        self.templatematch = self.pipeline.get_by_name("templatematch")
        self.screenshot = self.pipeline.get_by_name("screenshot")
        self.bus = self.pipeline.get_bus()
        self.bus.connect("message::error", self.on_error)
        self.bus.connect("message::warning", self.on_warning)
        self.bus.add_signal_watch()
        self.pipeline.set_state(gst.STATE_PLAYING)

    def wait_for_match(self, image, directory,
                       timeout_secs=10, certainty=0.98, consecutive_matches=3):
        """Wait for a stable match of `image` in the source video stream.

        "Stable" means 3 consecutive frames with a match certainty > 98% at the
        same x,y position.

        "timeout_secs" is in seconds elapsed, as reported by the video stream.
        """

        if os.path.isabs(image):
            template = image
        else:
            # Image is relative to the script's own directory
            template = os.path.abspath(os.path.join(directory, image))
            if not os.path.isfile(template):
                # Fall back to image from cwd, for convenience of the selftests
                template = os.path.abspath(image)

        self.templatematch.props.template = template
        self.match_count, self.last_x, self.last_y = 0, 0, 0
        self.timeout_secs = timeout_secs
        self.start_timestamp = None
        self.certainty = certainty
        self.consecutive_matches = consecutive_matches

        debug("Searching for " + template)
        self.bus.connect("message::element", self.bus_message)
        gtk.main()
        if self.match_count == self.consecutive_matches:
            debug("MATCHED " + template)
            return
        else:
            buf = self.screenshot.get_property("last-buffer")
            raise MatchTimeout(buf, template, timeout_secs)

    def on_error(self, bus, message):
        assert message.type == gst.MESSAGE_ERROR
        err, dbg = message.parse_error()
        sys.stderr.write("Error: %s: %s\n%s\n" % (err, err.message, dbg))
        sys.exit(1)

    def on_warning(self, bus, message):
        assert message.type == gst.MESSAGE_WARNING
        err, dbg = message.parse_warning()
        sys.stderr.write("Warning: %s: %s\n%s\n" % (err, err.message, dbg))
        if (message.src == self.templatematch and
                err.message == "OpenCV failed to load template image"):
            sys.stderr.write("Error: %s\n" % err.message)
            sys.exit(1)

    def bus_message(self, bus, message):
        st = message.structure
        if st.get_name() == "template_match":

            buf = self.screenshot.get_property("last-buffer")
            if self.start_timestamp == None:
                self.start_timestamp = buf.timestamp

            certainty = st["result"]
            debug("Match %d found at %d,%d (last: %d,%d) with dimensions "
                  "%dx%d. Certainty: %d%%. Timestamp: %d."
                  % (self.match_count,
                     st["x"], st["y"], self.last_x, self.last_y,
                     st["width"], st["height"],
                     certainty * 100.0, buf.timestamp))

            if certainty > self.certainty and (
                    self.match_count == 0 or
                    (st["x"], st["y"]) == (self.last_x, self.last_y)):
                self.match_count += 1
            else:
                self.match_count = 0
            self.last_x, self.last_y = st["x"], st["y"]

            timed_out = (buf.timestamp - self.start_timestamp >
                         self.timeout_secs * 1000000000)
            if self.match_count == self.consecutive_matches or (
                    timed_out and self.match_count == 0):
                self.templatematch.props.template = None
                self.bus.disconnect_by_func(self.bus_message)
                gtk.main_quit()

    def teardown(self):
        if self.pipeline:
            self.pipeline.set_state(gst.STATE_NULL)


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
        (e, debug) = msg.parse_error()
        raise RuntimeError(e.message)


def uri_to_remote(uri, display):
    if uri.lower() == 'none':
        return NullRemote()
    if uri.lower() == 'test':
        return VideoTestSrcControl(display)
    vr = re.match(r'vr:(?P<hostname>[^:]*)(:(?P<port>\d+))?', uri)
    if vr:
        d = vr.groupdict()
        return VirtualRemote(d['hostname'], int(d['port'] or 2033))
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
        self.stb = hostname
        self.port = port

    def press(self, key):
        import socket
        s = socket.socket()
        s.connect((self.stb, self.port))
        s.send("D\t%s\n\0U\t%s\n\0" % (key, key))  # send key Down, then key Up
        debug("Pressed " + key)


def uri_to_remote_recorder(uri):
    vr = re.match(r'vr:(?P<hostname>[^:]*)(:(?P<port>\d+))?', uri)
    if vr:
        d = vr.groupdict()
        return virtual_remote_listen(d['hostname'], int(d['port'] or 2033))
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


def key_reader(cmd_iter):
    r"""Converts virtual remote records into list of keys

    >>> list(key_reader(['D\tHELLO', 'U\tHELLO']))
    ['HELLO']
    >>> list(key_reader(['D\tCHEESE', 'D\tHELLO', 'U\tHELLO', 'U\tCHEESE']))
    ['HELLO', 'CHEESE']
    """
    for i in cmd_iter:
        (action, key) = i.split('\t')
        if action == 'U':
            yield key


def virtual_remote_listen(address, port):
    """Waits for a VirtualRemote to connect, and returns an iterator yielding
    keypresses."""
    import socket
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind((address, port))
    serversocket.listen(5)
    sys.stderr.write("Waiting for connection from virtual remote control "
                     "port %d...\n" % port)
    (connection, address) = serversocket.accept()
    sys.stderr.write("Accepted connection from %s\n" % str(address))
    return key_reader(read_records(connection, '\n\0'))


class UITestFailure(Exception):
    pass


class MatchTimeout(UITestFailure):
    def __init__(self, screenshot, expected, timeout_secs):
        self.screenshot = screenshot
        self.expected = expected
        self.timeout_secs = timeout_secs


class ConfigurationError(Exception):
    pass


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
        'stbt.conf'])
    assert(system_config in files_read)
    return dict(conffile.items('global'), **dict(conffile.items(tool)))


def debug(s):
    sys.stderr.write(os.path.basename(sys.argv[0]) + ": " + str(s) + "\n")
