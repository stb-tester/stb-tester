from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import os
import re
import socket
import struct
import subprocess
import sys
import time
from contextlib import contextmanager
from distutils.spawn import find_executable

from . import irnetbox
from .config import ConfigurationError
from .logging import debug, scoped_debug_level
from .utils import named_temporary_directory, to_bytes

__all__ = ['uri_to_control', 'uri_to_control_recorder']

try:
    from .control_gpl import controls as gpl_controls
except ImportError:
    gpl_controls = None


# pylint: disable=abstract-method

class RemoteControl(object):
    """Base class for remote-control implementations."""

    def press(self, key):
        raise NotImplementedError(
            "%s: 'press' is not implemented" % self.__class__.__name__)

    def keydown(self, key):
        raise NotImplementedError(
            "%s: 'keydown' is not implemented" % self.__class__.__name__)

    def keyup(self, key):
        raise NotImplementedError(
            "%s: 'keyup' is not implemented" % self.__class__.__name__)


class UnknownKeyError(Exception):
    pass


def uri_to_control(uri, display=None):
    controls = [
        (r'adb(:(?P<address>.*))?', new_adb_device),
        (r'error(:(?P<message>.*))?', ErrorControl),
        (r'file(:(?P<filename>[^,]+))?', FileControl),
        (r'''irnetbox:
             (?P<hostname>[^:]+)
             (:(?P<port>\d+))?
             :(?P<output>\d+)
             :(?P<config>[^:]+)''', IRNetBoxControl),
        (r'lirc(:(?P<hostname>[^:/]+))?:(?P<port>\d+):(?P<control_name>.+)',
         new_tcp_lirc_control),
        (r'lirc:(?P<lircd_socket>[^:]+)?:(?P<control_name>.+)',
         new_local_lirc_control),
        (r'none', NullControl),
        (r'roku:(?P<hostname>[^:]+)', RokuHttpControl),
        (r'samsung:(?P<hostname>[^:/]+)(:(?P<port>\d+))?',
         _new_samsung_tcp_control),
        (r'test', lambda: VideoTestSrcControl(display)),
        (r'x11:(?P<display>[^,]+)?(,(?P<mapping>.+)?)?', X11Control),
        (r'rfb:(?P<hostname>[^:/]+)(:(?P<port>\d+))?', RemoteFrameBuffer),
    ]
    if gpl_controls is not None:
        controls += gpl_controls

    for regex, factory in controls:
        m = re.match(regex, uri, re.VERBOSE | re.IGNORECASE)
        if m:
            return factory(**m.groupdict())
    raise ConfigurationError('Invalid remote control URI: "%s"' % uri)


def uri_to_control_recorder(uri):
    controls = [
        ('file://(?P<filename>.+)', file_control_recorder),
        (r'lirc(:(?P<hostname>[^:/]+))?:(?P<port>\d+):(?P<control_name>.+)',
         lirc_control_listen_tcp),
        (r'lirc:(?P<lircd_socket>[^:]+)?:(?P<control_name>.+)',
         lirc_control_listen),
        (r'stbt-control(:(?P<keymap_file>.+))?', stbt_control_listen),
    ]

    for regex, factory in controls:
        m = re.match(regex, uri)
        if m:
            return factory(**m.groupdict())
    raise ConfigurationError('Invalid remote control recorder URI: "%s"' % uri)


def new_adb_device(address):
    from stbt.android import AdbDevice
    tcpip = bool(re.match(r"\d+\.\d+\.\d+\.\d+", address))
    return AdbDevice(adb_device=address, tcpip=tcpip)


class NullControl(RemoteControl):
    def press(self, key):
        debug('NullControl: Ignoring request to press "%s"' % key)

    def keydown(self, key):
        debug('NullControl: Ignoring request to hold "%s"' % key)

    def keyup(self, key):
        debug('NullControl: Ignoring request to release "%s"' % key)


class ErrorControl(RemoteControl):
    def __init__(self, message):
        if message is None:
            message = "No remote control configured"
        self.message = message

    def press(self, key):  # pylint:disable=unused-argument
        raise RuntimeError(self.message)

    def keydown(self, key):
        raise RuntimeError(self.message)

    def keyup(self, key):
        raise RuntimeError(self.message)


class FileControl(RemoteControl):
    """Writes keypress events to file.  Mostly useful for testing.  Defaults to
    writing to stdout.
    """
    def __init__(self, filename):
        if filename is None:
            self.outfile = sys.stdout
        else:
            self.outfile = open(filename, 'w+')

    def press(self, key):
        self.outfile.write(key + '\n')
        self.outfile.flush()

    def keydown(self, key):
        self.outfile.write("Holding %s\n" % key)
        self.outfile.flush()

    def keyup(self, key):
        self.outfile.write("Released %s\n" % key)
        self.outfile.flush()


class VideoTestSrcControl(RemoteControl):
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
        self.videosrc.props.pattern = to_bytes(key)
        debug("Pressed %s" % key)


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)


class LircControl(RemoteControl):
    """Send a key-press via a LIRC-enabled infrared blaster.

    See http://www.lirc.org/html/technical.html#applications
    """

    def __init__(self, control_name, connect_fn):
        self.control_name = control_name
        self._connect = connect_fn

    def press(self, key):
        s = self._connect()
        command = b"SEND_ONCE %s %s" % (to_bytes(self.control_name),
                                        to_bytes(key))
        s.sendall(command + b"\n")
        _read_lircd_reply(s, command)
        debug("Pressed " + key)

    def keydown(self, key):
        s = self._connect()
        command = b"SEND_START %s %s" % (to_bytes(self.control_name),
                                         to_bytes(key))
        s.sendall(command + b"\n")
        _read_lircd_reply(s, command)
        debug("Holding " + key)

    def keyup(self, key):
        s = self._connect()
        command = b"SEND_STOP %s %s" % (to_bytes(self.control_name),
                                        to_bytes(key))
        s.sendall(command + b"\n")
        _read_lircd_reply(s, command)
        debug("Released " + key)


def _read_lircd_reply(stream, command):
    """Waits for lircd reply and checks if a LIRC send command was successful.

    Waits for a reply message from lircd (called "reply packet" in the LIRC
    reference) for the specified command; raises exception if it times out or
    the reply contains an error message.

    The structure of a lircd reply message for a SEND_ONCE|SEND_START|SEND_STOP
    command is the following:

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
        for line in read_records(stream, b"\n"):
            if line == b"BEGIN":
                reply = []
            reply.append(line)
            if line == b"END" and reply[1] == command:
                break
    except socket.timeout:
        raise RuntimeError(
            "Timed out: No reply from LIRC remote control within %d seconds"
            % stream.gettimeout())
    if b"SUCCESS" not in reply:
        if b"ERROR" in reply and len(reply) >= 6 and reply[3] == b"DATA":
            try:
                num_data_lines = int(reply[4])
                raise RuntimeError("LIRC remote control returned error: %s"
                                   % " ".join(reply[5:5 + num_data_lines]))
            except ValueError:
                pass
        raise RuntimeError("LIRC remote control returned unknown error")

DEFAULT_LIRCD_SOCKET = '/var/run/lirc/lircd'


def new_local_lirc_control(lircd_socket, control_name):
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
    debug("LircControl: Connecting to %s" % lircd_socket)
    _connect()
    debug("LircControl: Connected to %s" % lircd_socket)

    return LircControl(control_name, _connect)


def new_tcp_lirc_control(control_name, hostname=None, port=None):
    """Send a key-press via a LIRC-enabled device through a LIRC TCP listener.

        control = new_tcp_lirc_control("localhost", "8765", "humax")
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
    debug("TCPLircControl: Connecting to %s:%d" % (hostname, port))
    _connect()
    debug("TCPLircControl: Connected to %s:%d" % (hostname, port))

    return LircControl(control_name, _connect)


class RemoteFrameBuffer(RemoteControl):
    """Send a key-press to a set-top box running a VNC Remote Frame Buffer
        protocol.
        Expected key press input:
            <KEY_LABEL>

        control = RemoteFrameBuffer("192.168.0.123")
        control.press("KEY_MENU")
    """

    # Map our recommended keynames (from linux input-event-codes.h) to the
    # equivalent RFB keyname.
    _KEYNAMES = {
        'KEY_BACK': 0xE002,
        'KEY_BLUE': 0xE203,
        'KEY_CHANNELDOWN': 0xE007,
        'KEY_CHANNELUP': 0xE006,
        'KEY_DOWN': 0xE101,
        'KEY_ELPS': 0xEF00,
        'KEY_FASTFORWARD': 0xE405,
        'KEY_GREEN': 0xE201,
        'KEY_GUIDE': 0xE00B,
        'KEY_HELP': 0xE00A,
        'KEY_HOME': 0xE015,
        'KEY_INFO': 0xE00E,
        'KEY_INPUTSELECT': 0xE010,
        'KEY_INTERACT': 0xE008,
        'KEY_0': 0xE300,
        'KEY_1': 0xE301,
        'KEY_2': 0xE302,
        'KEY_3': 0xE303,
        'KEY_4': 0xE304,
        'KEY_5': 0xE305,
        'KEY_6': 0xE306,
        'KEY_7': 0xE307,
        'KEY_8': 0xE308,
        'KEY_9': 0xE309,
        'KEY_LEFT': 0xE102,
        'KEY_MENU': 0xE00A,
        'KEY_MUTE': 0xE005,
        'KEY_MYTV': 0xE009,
        'KEY_PAUSE': 0xE401,
        'KEY_PLAY': 0xE400,
        'KEY_PLAYPAUSE': 0xE40A,
        'KEY_POWER': 0xE000,
        'KEY_PRIMAFILA': 0xEF00,
        'KEY_RECORD': 0xE403,
        'KEY_RED': 0xE200,
        'KEY_REWIND': 0xE407,
        'KEY_RIGHT': 0xE103,
        'KEY_SEARCH': 0xEF03,
        'KEY_SELECT': 0xE001,
        'KEY_SKY': 0xEF01,
        'KEY_STOP': 0xE402,
        'KEY_TEXT': 0xE00F,
        'KEY_UP': 0xE100,
        'KEY_VOLUMEDOWN': 0xE004,
        'KEY_VOLUMEUP': 0xE003,
        'KEY_YELLOW': 0xE202
    }

    def __init__(self, hostname, port=None):
        self.hostname = hostname
        self.port = int(port or 5900)
        self.timeout = 3
        self.socket = None

    def press(self, key):
        self._connect_socket()
        self._handshake()
        self._press_down(key)
        self._release(key)
        self._close()

    def _connect_socket(self):
        self.socket = socket.socket()
        s = self.socket
        if self.timeout:
            s.settimeout(self.timeout)
        s.connect((self.hostname, self.port))
        debug(
            "RemoteFrameBuffer: connected to %s:%d"
            % (self.hostname, self.port))

    def _handshake(self):
        s = self.socket
        prot_info = s.recv(20)
        if prot_info != b'RFB 003.008\n':
            raise socket.error("wrong RFB protocol info")
        s.send(b"RFB 003.003\n")
        s.recv(4)
        s.send(b'\0')
        s.recv(24)
        debug("RemoteFrameBuffer: handshake completed")

    def _press_down(self, key):
        key_code = self._get_key_code(key)
        self.socket.send(struct.pack('!BBxxI', 4, 1, key_code))
        debug(
            "RemoteFrameBuffer: pressed down (0x%04x)"
            % key_code)

    def _release(self, key):
        key_code = self._get_key_code(key)
        self.socket.send(struct.pack('!BBxxI', 4, 0, key_code))
        debug("RemoteFrameBuffer: release (0x%04x)" % key_code)

    def _close(self):
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()
        debug("RemoteFrameBuffer: socket connection closed")

    def _get_key_code(self, key):
        key_code = self._KEYNAMES.get(key, key)
        return key_code


class IRNetBoxControl(RemoteControl):
    """Send a key-press via the network-controlled RedRat IRNetBox IR emitter.

    See http://www.redrat.co.uk/products/irnetbox.html

    """

    def __init__(self, hostname, port, output, config):  # pylint:disable=redefined-outer-name
        self.hostname = hostname
        self.port = int(port or 10001)
        self.output = int(output)
        self.config = irnetbox.RemoteControlConfig(config)
        # Connect once so that the test fails immediately if irNetBox not found
        # (instead of failing at the first `press` in the script).
        debug("IRNetBoxControl: Connecting to %s" % hostname)
        with self._connect() as irnb:
            irnb.power_on()
        time.sleep(0.5)
        debug("IRNetBoxControl: Connected to %s" % hostname)

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


class RokuHttpControl(RemoteControl):
    """Send a key-press via Roku remote control protocol.

    See https://sdkdocs.roku.com/display/sdkdoc/External+Control+API
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

    def __init__(self, hostname, timeout_secs=3):
        self.hostname = hostname
        self.timeout_secs = timeout_secs

    def press(self, key):
        import requests

        roku_keyname = self._KEYNAMES.get(key, key)
        response = requests.post(
            "http://%s:8060/keypress/%s" % (self.hostname, roku_keyname),
            timeout=self.timeout_secs)
        response.raise_for_status()
        debug("Pressed " + key)

    def keydown(self, key):
        import requests

        roku_keyname = self._KEYNAMES.get(key, key)
        response = requests.post(
            "http://%s:8060/keydown/%s" % (self.hostname, roku_keyname),
            timeout=self.timeout_secs)
        response.raise_for_status()
        debug("Holding " + key)

    def keyup(self, key):
        import requests

        roku_keyname = self._KEYNAMES.get(key, key)
        response = requests.post(
            "http://%s:8060/keyup/%s" % (self.hostname, roku_keyname),
            timeout=self.timeout_secs)
        response.raise_for_status()
        debug("Released " + key)


class SamsungTCPControl(RemoteControl):
    """Send a key-press via Samsung remote control protocol.

    See http://sc0ty.pl/2012/02/samsung-tv-network-remote-control-protocol/
    """
    def __init__(self, sock):
        self.socket = sock
        self._hello()

    @staticmethod
    def _encode_string(string):
        r"""
        >>> SamsungTCPControl._encode_string('192.168.0.10')
        '\x10\x00MTkyLjE2OC4wLjEw'
        """
        from base64 import b64encode
        b64 = b64encode(to_bytes(string))
        return struct.pack('<H', len(b64)) + b64

    def _send_payload(self, payload):
        sender = b"iphone.iapp.samsung"
        packet_start = struct.pack('<BH', 0, len(sender)) + sender
        self.socket.send(packet_start +
                         struct.pack('<H', len(payload)) +
                         payload)

    def _hello(self):
        payload = bytearray([0x64, 0x00])
        payload += self._encode_string(self.socket.getsockname()[0])
        payload += self._encode_string("my_id")
        payload += self._encode_string("stb-tester")
        self._send_payload(payload)
        reply = self.socket.recv(4096)
        debug("SamsungTCPControl reply: %s\n" % reply)

    def press(self, key):
        payload_start = bytearray([0x00, 0x00, 0x00])
        key_enc = self._encode_string(key)
        self._send_payload(payload_start + key_enc)
        debug("Pressed " + key)
        reply = self.socket.recv(4096)
        debug("SamsungTCPControl reply: %s\n" % reply)


def _new_samsung_tcp_control(hostname, port):
    return SamsungTCPControl(_connect_tcp_socket(hostname, int(port or 55000)))


def _load_key_mapping(filename):
    out = {}
    with open(filename, 'r') as mapfile:
        for line in mapfile:
            s = line.strip().split()
            if len(s) == 2 and not s[0].startswith('#'):
                out[s[0]] = s[1]
    return out


class X11Control(RemoteControl):
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


def file_control_recorder(filename):
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
            return
        yield line.rstrip()


def read_records(stream, sep):
    r"""Generator that splits stream into records given a separator

    >>> import io
    >>> s = io.BytesIO(b'hello\n\0This\n\0is\n\0a\n\0test\n\0')
    >>> list(read_records(FileToSocket(s), b'\n\0'))
    ['hello', 'This', 'is', 'a', 'test']
    """
    buf = b""
    while True:
        s = stream.recv(4096)
        if len(s) == 0:
            break
        buf += s
        cmds = buf.split(sep)
        buf = cmds[-1]
        for i in cmds[:-1]:
            yield i


def lirc_control_listen(lircd_socket, control_name):
    """Returns an iterator yielding keypresses received from a lircd file
    socket -- that is, the keypresses that lircd received from a hardware
    infrared receiver and is now sending on to us.

    See http://www.lirc.org/html/technical.html#applications
    """
    if lircd_socket is None:
        lircd_socket = DEFAULT_LIRCD_SOCKET
    lircd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    debug("control-recorder connecting to lirc file socket '%s'..." %
          lircd_socket)
    lircd.connect(lircd_socket)
    debug("control-recorder connected to lirc file socket")
    return lirc_key_reader(lircd.makefile("rb"), control_name)


def lirc_control_listen_tcp(address, port, control_name):
    """Returns an iterator yielding keypresses received from a lircd TCP
    socket."""
    address = address or 'localhost'
    port = int(port)
    debug("control-recorder connecting to lirc TCP socket %s:%s..." %
          (address, port))
    lircd = _connect_tcp_socket(address, port, timeout=None)
    debug("control-recorder connected to lirc TCP socket")
    return lirc_key_reader(lircd.makefile("rb"), control_name)


def stbt_control_listen(keymap_file):
    """Returns an iterator yielding keypresses received from `stbt control`.
    """
    import imp
    try:
        from .vars import libexecdir
        sc = "%s/stbt/stbt_control.py" % libexecdir
    except ImportError:
        sc = _find_file('../stbt_control.py')
    stbt_control = imp.load_source('stbt_control', sc)

    with scoped_debug_level(0):
        # Don't mess up printed keymap with debug messages
        return stbt_control.main_loop(
            'stbt record', keymap_file or stbt_control.default_keymap_file())


def lirc_key_reader(cmd_iter, control_name):
    r"""Convert lircd messages into list of keypresses

    >>> list(lirc_key_reader([b'0000dead 00 MENU My-IR-remote',
    ...                       b'0000beef 00 OK My-IR-remote',
    ...                       b'0000f00b 01 OK My-IR-remote',
    ...                       b'BEGIN', b'SIGHUP', b'END'],
    ...                      'My-IR-remote'))
    ['MENU', 'OK']
    """
    for s in cmd_iter:
        debug("lirc_key_reader received: %s" % s.rstrip())
        m = re.match(
            br"\w+ (?P<repeat_count>\d+) (?P<key>\w+) %s" % (
                to_bytes(control_name)),
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


class FileToSocket(object):
    """Makes something File-like behave like a Socket for testing purposes

    >>> import io
    >>> s = FileToSocket(io.BytesIO(b"Hello"))
    >>> s.recv(3)
    'Hel'
    >>> s.recv(3)
    'lo'
    """
    def __init__(self, f):
        self.file = f

    def recv(self, bufsize, flags=0):  # pylint:disable=unused-argument
        return self.file.read(bufsize)


@contextmanager
def _fake_lircd():
    import multiprocessing
    # This needs to accept 2 connections (from LircControl and
    # lirc_control_listen) and, on receiving input from the LircControl
    # connection, write to the lirc_control_listen connection.
    with named_temporary_directory(prefix="stbt-fake-lircd-") as tmp:
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
                for cmd in control.makefile("rb"):
                    m = re.match(br'SEND_ONCE (?P<ctrl>\S+) (?P<key>\S+)', cmd)
                    if m:
                        listener.sendall(
                            b'00000000 0 %(key)s %(ctrl)s\n' %
                            {b"key": m.group("key"),
                             b"ctrl": m.group("ctrl")})
                    control.sendall(b'BEGIN\n%sSUCCESS\nEND\n' % cmd)
                control.close()

        t = multiprocessing.Process(target=listen)
        t.daemon = True
        t.start()
        try:
            yield address
        finally:
            t.terminate()


def test_that_lirc_control_is_symmetric_with_lirc_control_listen():
    with _fake_lircd() as lircd_socket:
        listener = uri_to_control_recorder('lirc:%s:test' % lircd_socket)
        control = uri_to_control('lirc:%s:test' % (lircd_socket))
        for key in ['DOWN', 'DOWN', 'UP', 'GOODBYE']:
            control.press(key)
            assert next(listener) == to_bytes(key)


def test_that_local_lirc_socket_is_correctly_defaulted():
    global DEFAULT_LIRCD_SOCKET
    old_default = DEFAULT_LIRCD_SOCKET
    try:
        with _fake_lircd() as lircd_socket:
            DEFAULT_LIRCD_SOCKET = lircd_socket
            listener = uri_to_control_recorder('lirc:%s:test' % lircd_socket)
            uri_to_control('lirc::test').press('KEY')
            assert next(listener) == b'KEY'
    finally:
        DEFAULT_LIRCD_SOCKET = old_default


def test_roku_http_control():
    import pytest
    import responses
    from requests.exceptions import HTTPError

    control = uri_to_control('roku:192.168.1.3')
    with responses.RequestsMock() as mock:
        # This raises if the URL was not accessed.
        mock.add(mock.POST, 'http://192.168.1.3:8060/keypress/Home')
        control.press("KEY_HOME")
    with responses.RequestsMock() as mock:
        mock.add(mock.POST, 'http://192.168.1.3:8060/keypress/Home')
        control.press("Home")
    with pytest.raises(HTTPError):
        with responses.RequestsMock() as mock:
            mock.add(mock.POST, 'http://192.168.1.3:8060/keypress/Homeopathy',
                     status=400)
            control.press("Homeopathy")


def test_samsung_tcp_control():
    # This is more of a regression test than anything.
    sent_data = []

    class TestSocket(object):
        def send(self, data):
            sent_data.append(data)

        def recv(self, _):
            return ""

        def getsockname(self):
            return ['192.168.0.8', 12345]

    r = SamsungTCPControl(TestSocket())
    assert len(sent_data) == 1
    assert sent_data[0] == (
        b'\x00\x13\x00iphone.iapp.samsung0\x00d\x00\x10\x00MTkyLjE2OC4wLjg=' +
        b'\x08\x00bXlfaWQ=\x10\x00c3RiLXRlc3Rlcg==')
    r.press('KEY_0')
    assert len(sent_data) == 2
    assert sent_data[1] == (
        b'\x00\x13\x00iphone.iapp.samsung\r\x00\x00\x00\x00\x08\x00S0VZXzA=')


def test_x11_control():
    from unittest import SkipTest
    if os.environ.get('enable_virtual_stb') != 'yes':
        raise SkipTest('Set $enable_virtual_stb=yes to run this test')
    if not find_executable('Xorg') or not find_executable('xterm'):
        raise SkipTest("Testing X11Control requires X11 and xterm")

    from .x11 import x_server

    with named_temporary_directory() as tmp, x_server(320, 240) as display:
        r = uri_to_control('x11:%s' % display)

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
                print("xterm.log: " + line, end=' ')
        assert os.path.exists(tmp + '/good')


def test_uri_to_control():
    global IRNetBoxControl  # pylint:disable=global-variable-undefined
    orig_IRNetBoxControl = IRNetBoxControl
    try:
        # pylint:disable=redefined-outer-name
        def IRNetBoxControl(hostname, port, output, config):
            return ":".join([hostname, str(port or '10001'), output, config])
        out = uri_to_control("irnetbox:localhost:1234:1:conf")
        assert out == "localhost:1234:1:conf", (
            "Failed to parse uri with irnetbox port. Output was '%s'" % out)
        out = uri_to_control("irnetbox:localhost:1:conf")
        assert out == "localhost:10001:1:conf", (
            "Failed to parse uri without irnetbox port. Output was '%s'" % out)
        try:
            uri_to_control("irnetbox:localhost::1:conf")
            assert False, "Uri with empty field should have raised"
        except ConfigurationError:
            pass
    finally:
        IRNetBoxControl = orig_IRNetBoxControl
