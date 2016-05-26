from __future__ import absolute_import

import os
import re
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from distutils.spawn import find_executable

from . import irnetbox, utils
from .config import ConfigurationError
from .logging import debug, scoped_debug_level

__all__ = ['uri_to_remote', 'uri_to_remote_recorder']

try:
    from .control_gpl import controls as gpl_controls
except:
    gpl_controls = None


def uri_to_remote(uri, display=None):
    remotes = [
        (r'''irnetbox:
             (?P<hostname>[^:]+)
             (:(?P<port>\d+))?
             :(?P<output>\d+)
             :(?P<config>[^:]+)''', IRNetBoxRemote),
        (r'lirc(:(?P<hostname>[^:/]+))?:(?P<port>\d+):(?P<control_name>.+)',
         new_tcp_lirc_remote),
        (r'lirc:(?P<lircd_socket>[^:]+)?:(?P<control_name>.+)',
         new_local_lirc_remote),
        (r'none', NullRemote),
        (r'roku:(?P<hostname>[^:]+)', RokuHttpControl),
        (r'samsung:(?P<hostname>[^:/]+)(:(?P<port>\d+))?',
         _new_samsung_tcp_remote),
        (r'test', lambda: VideoTestSrcControl(display)),
        (r'vr:(?P<hostname>[^:/]+)(:(?P<port>\d+))?', VirtualRemote),
        (r'x11:(?P<display>[^,]+)?(,(?P<mapping>.+)?)?', _X11Remote),
    ]
    if gpl_controls is not None:
        remotes += gpl_controls
    for regex, factory in remotes:
        m = re.match(regex, uri, re.VERBOSE | re.IGNORECASE)
        if m:
            return factory(**m.groupdict())
    raise ConfigurationError('Invalid remote control URI: "%s"' % uri)


def uri_to_remote_recorder(uri):
    remotes = [
        ('file://(?P<filename>.+)', file_remote_recorder),
        (r'lirc(:(?P<hostname>[^:/]+))?:(?P<port>\d+):(?P<control_name>.+)',
         lirc_remote_listen_tcp),
        (r'lirc:(?P<lircd_socket>[^:]+)?:(?P<control_name>.+)',
         lirc_remote_listen),
        (r'stbt-control(:(?P<keymap_file>.+))?', stbt_control_listen),
        (r'vr:(?P<address>[^:/]*)(:(?P<port>\d+))?', virtual_remote_listen),
    ]

    for regex, factory in remotes:
        m = re.match(regex, uri)
        if m:
            return factory(**m.groupdict())
    raise ConfigurationError('Invalid remote control recorder URI: "%s"' % uri)


class NullRemote(object):
    @staticmethod
    def press(key):
        debug('NullRemote: Ignoring request to press "%s"' % key)


class VideoTestSrcControl(object):
    """Remote control used by selftests.

    Changes the videotestsrc image to the specified pattern ("0" to "20").
    See `gst-inspect videotestsrc`.
    """

    def __init__(self, display):
        self.display = display

    @property
    def videosrc(self):
        videosrc = self.display.source_pipeline.get_by_name("videotestsrc0")
        if not videosrc:
            raise ConfigurationError('The "test" control can only be used '
                                     'with source-pipeline = "videotestsrc"')
        return videosrc

    def press(self, key):
        if key not in [
                0, "smpte",
                1, "snow",
                2, "black",
                3, "white",
                4, "red",
                5, "green",
                6, "blue",
                7, "checkers-1",
                8, "checkers-2",
                9, "checkers-4",
                10, "checkers-8",
                11, "circular",
                12, "blink",
                13, "smpte75",
                14, "zone-plate",
                15, "gamut",
                16, "chroma-zone-plate",
                17, "solid-color",
                18, "ball",
                19, "smpte100",
                20, "bar"]:
            raise RuntimeError(
                'Key "%s" not valid for the "test" control' % key)
        self.videosrc.props.pattern = key
        debug("Pressed %s" % key)


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)


class VirtualRemote(object):
    """Send a key-press to a set-top box running a VirtualRemote listener.

        control = VirtualRemote("192.168.0.123")
        control.press("MENU")
    """

    def __init__(self, hostname, port=None):
        self.hostname = hostname
        self.port = int(port or 2033)
        # Connect once so that the test fails immediately if STB not found
        # (instead of failing at the first `press` in the script).
        debug("VirtualRemote: Connecting to %s:%d" % (hostname, self.port))
        self._connect()
        debug("VirtualRemote: Connected to %s:%d" % (hostname, self.port))

    def press(self, key):
        self._connect().sendall(
            "D\t%s\n\x00U\t%s\n\x00" % (key, key))  # key Down, then Up
        debug("Pressed " + key)

    def _connect(self):
        return _connect_tcp_socket(self.hostname, self.port)


class LircRemote(object):
    """Send a key-press via a LIRC-enabled infrared blaster.

    See http://www.lirc.org/html/technical.html#applications
    """

    def __init__(self, control_name, connect_fn):
        self.control_name = control_name
        self._connect = connect_fn

    def press(self, key):
        s = self._connect()
        s.sendall("SEND_ONCE %s %s\n" % (self.control_name, key))
        _read_lircd_reply(s)
        debug("Pressed " + key)

DEFAULT_LIRCD_SOCKET = '/var/run/lirc/lircd'


def new_local_lirc_remote(lircd_socket, control_name):
    if lircd_socket is None:
        lircd_socket = DEFAULT_LIRCD_SOCKET

    def _connect():
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect(lircd_socket)
            return s
        except socket.error as e:
            e.args = (("Failed to connect to Lirc socket %s: %s" % (
                lircd_socket, e)),)
            e.strerror = e.args[0]
            raise

    # Connect once so that the test fails immediately if Lirc isn't running
    # (instead of failing at the first `press` in the script).
    debug("LircRemote: Connecting to %s" % lircd_socket)
    _connect()
    debug("LircRemote: Connected to %s" % lircd_socket)

    return LircRemote(control_name, _connect)


def new_tcp_lirc_remote(control_name, hostname=None, port=None):
    """Send a key-press via a LIRC-enabled device through a LIRC TCP listener.

        control = new_tcp_lirc_remote("localhost", "8765", "humax")
        control.press("MENU")
    """
    if hostname is None:
        hostname = 'localhost'
    if port is None:
        port = 8765

    port = int(port)

    def _connect():
        return _connect_tcp_socket(hostname, port)

    # Connect once so that the test fails immediately if Lirc isn't running
    # (instead of failing at the first `press` in the script).
    debug("TCPLircRemote: Connecting to %s:%d" % (hostname, port))
    _connect()
    debug("TCPLircRemote: Connected to %s:%d" % (hostname, port))

    return LircRemote(control_name, _connect)


class IRNetBoxRemote(object):
    """Send a key-press via the network-controlled RedRat IRNetBox IR emitter.

    See http://www.redrat.co.uk/products/irnetbox.html

    """

    def __init__(self, hostname, port, output, config):  # pylint: disable=W0621
        self.hostname = hostname
        self.port = int(port or 10001)
        self.output = int(output)
        self.config = irnetbox.RemoteControlConfig(config)
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
        debug("Pressed " + key)

    def _connect(self):
        try:
            return irnetbox.IRNetBox(self.hostname, self.port)
        except socket.error as e:
            e.args = (("Failed to connect to IRNetBox %s: %s" % (
                self.hostname, e)),)
            e.strerror = e.args[0]
            raise


class RokuHttpControl(object):
    """Send a key-press via Roku remote control protocol.

    See https://sdkdocs.roku.com/display/sdkdoc/External+Control+Guide
    """

    # Map our recommended keynames (from linux input-event-codes.h) to the
    # equivalent Roku keyname.
    _KEYNAMES = {
        "KEY_HOME": "Home",
        "KEY_REWIND": "Rev",
        "KEY_FASTFORWARD": "Fwd",
        "KEY_PLAY": "Play",
        "KEY_PAUSE": "Play",
        "KEY_PLAYPAUSE": "Play",
        "KEY_OK": "Select",
        "KEY_LEFT": "Left",
        "KEY_RIGHT": "Right",
        "KEY_DOWN": "Down",
        "KEY_UP": "Up",
        "KEY_BACK": "Back",
        "KEY_AGAIN": "InstantReplay",
        "KEY_INFO": "Info",
        "KEY_BACKSPACE": "Backspace",
        "KEY_SEARCH": "Search",
        # Enter is for completing keyboard entry fields, such as search fields
        # (it is not the same as Select).
        "KEY_ENTER": "Enter",
        "KEY_VOLUMEDOWN": "VolumeDown",
        "KEY_MUTE": "VolumeMute",
        "KEY_VOLUMEUP": "VolumeUp",
    }

    def __init__(self, hostname):
        self.hostname = hostname

    def press(self, key):
        import requests

        roku_keyname = self._KEYNAMES.get(key, key)
        response = requests.post("http://%s:8060/keypress/%s"
                                 % (self.hostname, roku_keyname))
        response.raise_for_status()
        debug("Pressed " + key)


class _SamsungTCPRemote(object):
    """Send a key-press via Samsung remote control protocol.

    See http://sc0ty.pl/2012/02/samsung-tv-network-remote-control-protocol/
    """
    def __init__(self, sock):
        self.socket = sock
        self._hello()

    @staticmethod
    def _encode_string(string):
        r"""
        >>> _SamsungTCPRemote._encode_string('192.168.0.10')
        '\x10\x00MTkyLjE2OC4wLjEw'
        """
        from base64 import b64encode
        from struct import pack
        b64 = b64encode(string)
        return pack('<H', len(b64)) + b64

    def _send_payload(self, payload):
        from struct import pack
        sender = "iphone.iapp.samsung"
        packet_start = pack('<BH', 0, len(sender)) + sender
        self.socket.send(packet_start + pack('<H', len(payload)) + payload)

    def _hello(self):
        payload = bytearray([0x64, 0x00])
        payload += self._encode_string(self.socket.getsockname()[0])
        payload += self._encode_string("my_id")
        payload += self._encode_string("stb-tester")
        self._send_payload(payload)
        reply = self.socket.recv(4096)
        debug("SamsungTCPRemote reply: %s\n" % reply)

    def press(self, key):
        payload_start = bytearray([0x00, 0x00, 0x00])
        key_enc = self._encode_string(key)
        self._send_payload(payload_start + key_enc)
        debug("Pressed " + key)
        reply = self.socket.recv(4096)
        debug("SamsungTCPRemote reply: %s\n" % reply)


def _new_samsung_tcp_remote(hostname, port):
    return _SamsungTCPRemote(_connect_tcp_socket(hostname, int(port or 55000)))


def _load_key_mapping(filename):
    out = {}
    with open(filename, 'r') as mapfile:
        for line in mapfile:
            s = line.strip().split()
            if len(s) == 2 and not s[0].startswith('#'):
                out[s[0]] = s[1]
    return out


class _X11Remote(object):
    """Simulate key presses using xdotool.
    """
    def __init__(self, display=None, mapping=None):
        self.display = display
        if find_executable('xdotool') is None:
            raise Exception("x11 control: xdotool not installed")
        self.mapping = _load_key_mapping(_find_file("x-key-mapping.conf"))
        if mapping is not None:
            self.mapping.update(_load_key_mapping(mapping))

    def press(self, key):
        e = os.environ.copy()
        if self.display is not None:
            e['DISPLAY'] = self.display
        subprocess.check_call(
            ['xdotool', 'key', self.mapping.get(key, key)], env=e)
        debug("Pressed " + key)


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


def virtual_remote_listen(address, port=None):
    """Waits for a VirtualRemote to connect, and returns an iterator yielding
    keypresses."""
    if port is None:
        port = 2033
    port = int(port)
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
    if lircd_socket is None:
        lircd_socket = '/var/run/lirc/lircd'
    lircd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    debug("control-recorder connecting to lirc file socket '%s'..." %
          lircd_socket)
    lircd.connect(lircd_socket)
    debug("control-recorder connected to lirc file socket")
    return lirc_key_reader(lircd.makefile(), control_name)


def lirc_remote_listen_tcp(address, port, control_name):
    """Returns an iterator yielding keypresses received from a lircd TCP
    socket."""
    address = address or 'localhost'
    port = int(port)
    debug("control-recorder connecting to lirc TCP socket %s:%s..." %
          (address, port))
    lircd = _connect_tcp_socket(address, port, timeout=None)
    debug("control-recorder connected to lirc TCP socket")
    return lirc_key_reader(lircd.makefile(), control_name)


def stbt_control_listen(keymap_file):
    """Returns an iterator yielding keypresses received from `stbt control`.
    """
    import imp
    stbt_control = imp.load_source(
        'stbt_control', _find_file('../stbt-control'))

    with scoped_debug_level(0):
        # Don't mess up printed keymap with debug messages
        return stbt_control.main_loop(
            'stbt record', keymap_file or stbt_control.default_keymap_file())


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


def _connect_tcp_socket(address, port, timeout=3):
    """Connects to a TCP listener on 'address':'port'."""
    try:
        s = socket.socket()
        if timeout:
            s.settimeout(timeout)
        s.connect((address, port))
        return s
    except socket.error as e:
        e.args = (("Failed to connect to remote control at %s:%d: %s" % (
            address, port, e)),)
        e.strerror = e.args[0]
        raise


def _read_lircd_reply(stream):
    """Waits for lircd reply and checks if a LIRC send command was successful.

    Waits for a reply message from lircd (called "reply packet" in the LIRC
    reference) for a SEND_ONCE command, raises exception if it times out or
    the reply contains an error message.

    The structure of a lircd reply message for a SEND_ONCE command is the
    following:

    BEGIN
    <command>
    (SUCCESS|ERROR)
    [DATA
    <number-of-data-lines>
    <error-message>]
    END

    See: http://www.lirc.org/html/technical.html#applications
    """
    reply = []
    try:
        for line in read_records(stream, "\n"):
            if line == "BEGIN":
                reply = []
            reply.append(line)
            if line == "END" and "SEND_ONCE" in reply[1]:
                break
    except socket.timeout:
        raise RuntimeError(
            "Timed out: No reply from LIRC remote control within %d seconds"
            % stream.gettimeout())
    if "SUCCESS" not in reply:
        if "ERROR" in reply and len(reply) >= 6 and reply[3] == "DATA":
            num_data_lines = int(reply[4])
            raise RuntimeError("LIRC remote control returned error: %s"
                               % " ".join(reply[5:5 + num_data_lines]))
        raise RuntimeError("LIRC remote control returned unknown error")


class FileToSocket(object):
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
    received = []
    keys = ['DOWN', 'DOWN', 'UP', 'GOODBYE']

    def listener():
        # "* 2" is once for VirtualRemote's __init__ and once for press.
        for _ in range(len(keys) * 2):
            for k in uri_to_remote_recorder('vr:localhost:2033'):
                received.append(k)

    t = threading.Thread()
    t.daemon = True
    t.run = listener
    t.start()
    for k in keys:
        time.sleep(0.1)  # Give listener a chance to start listening (sorry)
        vr = uri_to_remote('vr:localhost:2033')
        time.sleep(0.1)
        vr.press(k)
    t.join()
    assert received == keys


@contextmanager
def _fake_lircd():
    import multiprocessing
    # This needs to accept 2 connections (from LircRemote and
    # lirc_remote_listen) and, on receiving input from the LircRemote
    # connection, write to the lirc_remote_listen connection.
    with utils.named_temporary_directory(prefix="stbt-fake-lircd-") as tmp:
        address = tmp + '/lircd'
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(address)
        s.listen(6)

        def listen():
            import signal
            signal.signal(signal.SIGTERM, lambda _, __: sys.exit(0))

            listener, _ = s.accept()
            while True:
                control, _ = s.accept()
                for cmd in control.makefile():
                    m = re.match(r'SEND_ONCE (?P<ctrl>\w+) (?P<key>\w+)', cmd)
                    if m:
                        listener.sendall(
                            '00000000 0 %(key)s %(ctrl)s\n' % m.groupdict())
                    control.sendall('BEGIN\n%sSUCCESS\nEND\n' % cmd)
                control.close()

        t = multiprocessing.Process(target=listen)
        t.daemon = True
        t.start()
        try:
            yield address
        finally:
            t.terminate()


def test_that_lirc_remote_is_symmetric_with_lirc_remote_listen():
    with _fake_lircd() as lircd_socket:
        listener = uri_to_remote_recorder('lirc:%s:test' % lircd_socket)
        control = uri_to_remote('lirc:%s:test' % (lircd_socket))
        for key in ['DOWN', 'DOWN', 'UP', 'GOODBYE']:
            control.press(key)
            assert listener.next() == key


def test_that_local_lirc_socket_is_correctly_defaulted():
    global DEFAULT_LIRCD_SOCKET
    old_default = DEFAULT_LIRCD_SOCKET
    try:
        with _fake_lircd() as lircd_socket:
            DEFAULT_LIRCD_SOCKET = lircd_socket
            listener = uri_to_remote_recorder('lirc:%s:test' % lircd_socket)
            uri_to_remote('lirc::test').press('KEY')
            assert listener.next() == 'KEY'
    finally:
        DEFAULT_LIRCD_SOCKET = old_default


def test_roku_http_control():
    import responses
    from nose.tools import assert_raises  # pylint:disable=no-name-in-module
    from requests.exceptions import HTTPError

    control = uri_to_remote('roku:192.168.1.3')
    with responses.RequestsMock() as mock:
        # This raises if the URL was not accessed.
        mock.add(mock.POST, 'http://192.168.1.3:8060/keypress/Home')
        control.press("KEY_HOME")
    with responses.RequestsMock() as mock:
        mock.add(mock.POST, 'http://192.168.1.3:8060/keypress/Home')
        control.press("Home")
    with assert_raises(HTTPError):
        with responses.RequestsMock() as mock:
            mock.add(mock.POST, 'http://192.168.1.3:8060/keypress/Homeopathy',
                     status=400)
            control.press("Homeopathy")


def test_samsung_tcp_remote():
    # This is more of a regression test than anything.
    sent_data = []

    class TestSocket(object):
        def send(self, data):
            sent_data.append(data)

        def recv(self, _):
            return ""

        def getsockname(self):
            return ['192.168.0.8', 12345]

    r = _SamsungTCPRemote(TestSocket())
    assert len(sent_data) == 1
    assert sent_data[0] == (
        b'\x00\x13\x00iphone.iapp.samsung0\x00d\x00\x10\x00MTkyLjE2OC4wLjg=' +
        b'\x08\x00bXlfaWQ=\x10\x00c3RiLXRlc3Rlcg==')
    r.press('KEY_0')
    assert len(sent_data) == 2
    assert sent_data[1] == (
        b'\x00\x13\x00iphone.iapp.samsung\r\x00\x00\x00\x00\x08\x00S0VZXzA=')


def test_x11_remote():
    from nose.plugins.skip import SkipTest
    from .x11 import x_server
    if not find_executable('Xorg') or not find_executable('xterm'):
        raise SkipTest("Testing X11Remote requires X11 and xterm")

    with utils.named_temporary_directory() as tmp, \
            x_server(320, 240) as display:
        r = uri_to_remote('x11:%s' % display)

        subprocess.Popen(
            ['xterm', '-l', '-lf', 'xterm.log'],
            env={'DISPLAY': display, 'PATH': os.environ['PATH']},
            cwd=tmp, stderr=open('/dev/null', 'w'))

        # Can't be sure how long xterm will take to get ready:
        for _ in range(0, 20):
            for keysym in ['KEY_T', 'KEY_O', 'KEY_U', 'KEY_C', 'KEY_H',
                           'KEY_SPACE',
                           'g', 'o', 'o', 'd',
                           'KEY_OK']:
                r.press(keysym)
            if os.path.exists(tmp + '/good'):
                break
            time.sleep(0.5)
        with open(tmp + '/xterm.log', 'r') as log:
            for line in log:
                print "xterm.log: " + line,
        assert os.path.exists(tmp + '/good')


def test_uri_to_remote():
    global IRNetBoxRemote  # pylint: disable=W0601
    orig_IRNetBoxRemote = IRNetBoxRemote
    try:
        # pylint: disable=W0621
        def IRNetBoxRemote(hostname, port, output, config):
            return ":".join([hostname, str(port or '10001'), output, config])
        out = uri_to_remote("irnetbox:localhost:1234:1:conf")
        assert out == "localhost:1234:1:conf", (
            "Failed to parse uri with irnetbox port. Output was '%s'" % out)
        out = uri_to_remote("irnetbox:localhost:1:conf")
        assert out == "localhost:10001:1:conf", (
            "Failed to parse uri without irnetbox port. Output was '%s'" % out)
        try:
            uri_to_remote("irnetbox:localhost::1:conf")
            assert False, "Uri with empty field should have raised"
        except ConfigurationError:
            pass
    finally:
        IRNetBoxRemote = orig_IRNetBoxRemote
