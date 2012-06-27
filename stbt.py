import ConfigParser
import os
import re
import sys


def save_frame(buf, filename):
    '''Save a gstreamer buffer to the specified file in png format.'''
    import pygst  # gstreamer
    pygst.require("0.10")
    import gst
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


def uri_to_remote(uri):
    if uri == 'None':
        return NullRemote()
    m = re.match(r'vr:(?P<hostname>[^:]*)(:(?P<port>\d+))?', uri)
    if m:
        d = m.groupdict()
        return VirtualRemote(d['hostname'], int(d['port'] or 2033))
    else:
        raise RuntimeException('Invalid remote control URI: "%s"' % uri)


class NullRemote:
    def press(self, key):
        pass


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
    m = re.match(r'vr:(?P<hostname>[^:]*)(:(?P<port>\d+))?', uri)
    if m:
        d = m.groupdict()
        return virtual_remote_listen(d['hostname'], int(d['port'] or 2033))
    m = re.match('file://(?P<filename>.+)', uri)
    if m:
        return file_remote_recorder(m.group('filename'))


def file_remote_recorder(filename):
    """ A generator that returns lines from the file given by filename.

    Unfortunately treating a file as a iterator doesn't work in the case of
    interactive input, even when we provide bufsize=1 (line buffered) to the
    call to open() so we have to have this function to work around it. """
    f = open(filename, 'r')
    while True:
        yield f.readline().rstrip()


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


def debug(s):
    sys.stderr.write(sys.argv[0] + ": " + str(s) + "\n")
