import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time

import requests

from . import irnetbox
from .config import ConfigurationError
from .logging import debug
from .utils import named_temporary_directory, to_bytes, to_unicode

__all__ = ['uri_to_control']

try:
    from .control_gpl import controls as gpl_controls
except ImportError:
    gpl_controls = None


# pylint: disable=abstract-method

class RemoteControl():
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


def _lookup_uri_to_control(uri, display=None):
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
        (r'redrat-bt:(?P<hostname>[^:/]+):((?P<port>\d+))?:'
         r'(?P<serial_no>[^:/]+):(?P<target_bt_address>[^:/]+)',
         RedRatHttpControl.new_bt),
        (r'redrat-ir:(?P<hostname>[^:/]+):((?P<port>\d+))?:'
         r'(?P<serial_no>[^:/]+):(?P<output>[^:/]+)', RedRatHttpControl.new_ir),
        (r'bluerat:(?P<hostname>[^:/]+):((?P<port>\d+))?:'
         r'(?P<serial_no>[^:/]+):(?P<target_bt_address>[^:/]+)',
         RedRatHttpControl.new_bluerat),
    ]
    if gpl_controls is not None:
        controls += gpl_controls

    for regex, factory in controls:
        m = re.match(regex, uri, re.VERBOSE | re.IGNORECASE)
        if m:
            return (factory, m.groupdict())
    raise ConfigurationError('Invalid remote control URI: "%s"' % uri)


def uri_to_control(uri, display=None):
    factory, kwargs = _lookup_uri_to_control(uri, display)
    return factory(**kwargs)


def new_adb_device(address):
    from _stbt.android import AdbDevice
    return AdbDevice(address)


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

    def press(self, key):
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
            self.outfile = open(filename, 'w+', encoding='utf-8')

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
        self.videosrc.props.pattern = to_unicode(key)
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
        with self._connect() as s:
            command = b"SEND_ONCE %s %s" % (to_bytes(self.control_name),
                                            to_bytes(key))
            s.sendall(command + b"\n")
            _read_lircd_reply(s, command)
        debug("Pressed %s" % key)

    def keydown(self, key):
        with self._connect() as s:
            command = b"SEND_START %s %s" % (to_bytes(self.control_name),
                                             to_bytes(key))
            s.sendall(command + b"\n")
            _read_lircd_reply(s, command)
        debug("Holding %s" % key)

    def keyup(self, key):
        with self._connect() as s:
            command = b"SEND_STOP %s %s" % (to_bytes(self.control_name),
                                            to_bytes(key))
            s.sendall(command + b"\n")
            _read_lircd_reply(s, command)
        debug("Released %s" % key)


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
                                   % b" ".join(reply[5:5 + num_data_lines]))
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
            s.settimeout(10)
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

    def press(self, key):
        s = socket.create_connection((self.hostname, self.port), self.timeout)
        debug(
            "RemoteFrameBuffer: connected to %s:%d"
            % (self.hostname, self.port))

        prot_info = s.recv(20)
        if prot_info != b'RFB 003.008\n':
            raise socket.error("wrong RFB protocol info")
        s.send(b"RFB 003.003\n")
        s.recv(4)
        s.send(b'\0')
        s.recv(24)
        debug("RemoteFrameBuffer: handshake completed")

        key_code = self._KEYNAMES.get(key, key)
        s.send(struct.pack('!BBxxI', 4, 1, key_code))
        debug(
            "RemoteFrameBuffer: pressed down (0x%04x)"
            % key_code)

        s.send(struct.pack('!BBxxI', 4, 0, key_code))
        debug("RemoteFrameBuffer: release (0x%04x)" % key_code)

        s.shutdown(socket.SHUT_RDWR)
        s.close()
        debug("RemoteFrameBuffer: socket connection closed")


class IRNetBoxControl(RemoteControl):
    """Send a key-press via the network-controlled RedRat IRNetBox IR emitter.

    See http://www.redrat.co.uk/products/irnetbox.html

    """

    def __init__(self, hostname, port, output, config):
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
        debug("Pressed %s" % key)

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
        roku_keyname = self._KEYNAMES.get(key, key)
        response = requests.post(
            "http://%s:8060/keypress/%s" % (self.hostname, roku_keyname),
            timeout=self.timeout_secs)
        response.raise_for_status()
        debug("Pressed %s" % key)

    def keydown(self, key):
        roku_keyname = self._KEYNAMES.get(key, key)
        response = requests.post(
            "http://%s:8060/keydown/%s" % (self.hostname, roku_keyname),
            timeout=self.timeout_secs)
        response.raise_for_status()
        debug("Holding %s" % key)

    def keyup(self, key):
        roku_keyname = self._KEYNAMES.get(key, key)
        response = requests.post(
            "http://%s:8060/keyup/%s" % (self.hostname, roku_keyname),
            timeout=self.timeout_secs)
        response.raise_for_status()
        debug("Released %s" % key)


class RedRatHttpControlError(requests.HTTPError):
    pass


class RedRatHttpControl(RemoteControl):
    """Send a key-press via RedRat HTTP REST API (see RedRat hub)."""
    def __init__(self, url, timeout_secs=3):
        self._session = requests.Session()
        self._url = url
        self.timeout_secs = timeout_secs

    @staticmethod
    def new_ir(hostname, port, serial_no, output, timeout_secs=3):
        port = int(port or 4254)
        return RedRatHttpControl(
            "http://%s:%i/api/redrats/%s/%s" % (
                hostname, port, serial_no, output), timeout_secs)

    @staticmethod
    def new_bt(hostname, port, serial_no, target_bt_address, timeout_secs=3):
        port = int(port or 4254)
        return RedRatHttpControl(
            "http://%s:%i/api/bt/modules/%s/targets/%s/send" % (
                hostname, port, serial_no, target_bt_address), timeout_secs)

    @staticmethod
    def new_bluerat(hostname, port, serial_no, target_bt_address,
                    timeout_secs=3):
        port = int(port or 4254)
        return RedRatHttpControl(
            "http://%s:%i/api/bluetoothdevices/%s/targets/%s/send" % (
                hostname, port, serial_no, target_bt_address), timeout_secs)

    def press(self, key):
        response = self._session.post(
            self._url, {"Command": key}, timeout=self.timeout_secs)
        if not response.ok:
            try:
                error_msg = response.json()["error"]
            except Exception:  # pylint:disable=broad-except
                response.raise_for_status()
            if re.match("Command '.*' is not known.", error_msg):
                raise UnknownKeyError(error_msg)
            else:
                raise RedRatHttpControlError(error_msg, response=response)
        debug("Pressed %s" % key)


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
        debug("Pressed %s" % key)
        reply = self.socket.recv(4096)
        debug("SamsungTCPControl reply: %s\n" % reply)


def _new_samsung_tcp_control(hostname, port):
    return SamsungTCPControl(_connect_tcp_socket(hostname, int(port or 55000)))


def _load_key_mapping(filename):
    out = {}
    with open(filename, 'r', encoding='utf-8') as mapfile:
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
        if shutil.which('xdotool') is None:
            raise FileNotFoundError("x11 control: xdotool not installed")
        self.mapping = _load_key_mapping(_find_file("x-key-mapping.conf"))
        if mapping is not None:
            self.mapping.update(_load_key_mapping(mapping))

    def press(self, key):
        e = os.environ.copy()
        if self.display is not None:
            e['DISPLAY'] = self.display
        subprocess.check_call(
            ['xdotool', 'key', self.mapping.get(key, key)], env=e)
        debug("Pressed %s" % key)


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


class FileToSocket():
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


def test_roku_http_control():
    import pytest
    import responses

    control = uri_to_control('roku:192.168.1.3')
    with responses.RequestsMock() as mock:
        # This raises if the URL was not accessed.
        mock.add(mock.POST, 'http://192.168.1.3:8060/keypress/Home')
        control.press("KEY_HOME")
    with responses.RequestsMock() as mock:
        mock.add(mock.POST, 'http://192.168.1.3:8060/keypress/Home')
        control.press("Home")
    with pytest.raises(requests.HTTPError):
        with responses.RequestsMock() as mock:
            mock.add(mock.POST, 'http://192.168.1.3:8060/keypress/Homeopathy',
                     status=400)
            control.press("Homeopathy")


def test_redrathttp_control():
    import pytest
    import responses

    control = uri_to_control('redrat-ir:192.168.1.3::24462:7')
    control = uri_to_control('redrat-bt:192.168.1.3::24462:CC-78-AB-79-3C-DF')
    with responses.RequestsMock() as mock:
        # This raises if the URL was not accessed.
        mock.add(mock.POST, 'http://192.168.1.3:4254/api/bt/modules/24462'
                 '/targets/CC-78-AB-79-3C-DF/send')
        control.press("KEY_HOME")
        assert mock.calls[0].request.body == "Command=KEY_HOME"

    bad_control = uri_to_control(
        'redrat-bt:192.168.1.3::24463:CC-78-AB-79-3C-DF')
    with responses.RequestsMock() as mock:
        mock.add(
            mock.POST, 'http://192.168.1.3:4254/api/bt/modules/24462/targets/'
            'CC-78-AB-79-3C-DF/send', json={
                "error": "Command 'KEY_OK2' is not known.",
                "stackTrace": ""
            }, status=500)
        with pytest.raises(
                UnknownKeyError, match="Command 'KEY_OK2' is not known."):
            control.press("KEY_OK2")

        mock.add(
            mock.POST, 'http://192.168.1.3:4254/api/bt/modules/24463/targets/'
            'CC-78-AB-79-3C-DF/send', json={
                "error": "No BT module with serial number '24463' found.",
                "stackTrace": ""
            }, status=404)
        with pytest.raises(
                RedRatHttpControlError,
                match="No BT module with serial number '24463' found."):
            bad_control.press("KEY_OK")


def test_samsung_tcp_control():
    # This is more of a regression test than anything.
    sent_data = []

    class TestSocket():
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
    if not shutil.which('Xorg') or not shutil.which('xterm'):
        raise SkipTest("Testing X11Control requires X11 and xterm")

    from .x11 import x_server

    with named_temporary_directory() as tmp, x_server(320, 240) as display:
        r = uri_to_control('x11:%s' % display)

        subprocess.Popen(
            ['xterm', '-l', '-lf', 'xterm.log'],
            env={'DISPLAY': display, 'PATH': os.environ['PATH']},
            cwd=tmp, stderr=subprocess.DEVNULL)

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
        with open(tmp + '/xterm.log', 'r', encoding='utf-8') as log:
            for line in log:
                print("xterm.log: " + line, end=' ')
        assert os.path.exists(tmp + '/good')
