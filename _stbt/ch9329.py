import enum
import logging
import re
import struct
import typing
from .control import RemoteControl

logger = logging.getLogger(__name__)


class CH9329Control(RemoteControl):
    """Send a key-press using the CH9329 serial to USB HID adaptor."""
    def __init__(self, device: str):
        import serial
        self.device = serial.Serial(device, 9600)
        self.frame = b''

    def press(self, key: str):
        self.keydown(key)
        self.keyup(key)

    def keydown(self, key: str):
        self._request(_encode(key))

    def keyup(self, key: str):
        self._request(_encode(key, keyup=True))

    def _request(self, frame: bytes):
        logger.debug("Writing %s", frame.hex())
        self.device.timeout = 0
        while True:
            data = self.device.read(128)
            if data:
                logger.warning("Discarding unexpected data: %s", data.hex())
            else:
                break
        self.device.timeout = 10
        self.device.reset_input_buffer()
        self.device.write(frame)
        return self._read_one()

    def _read_one(self):
        while True:
            try:
                frame, length = _deframe(self.frame)
            except NeedDataError as e:
                logger.debug("Need at least %dB more to deframe", e.at_least)
                d = self.device.read(e.at_least)
                logger.debug("Read %dB: %s", len(d), d.hex())
                self.frame += d
            else:
                self.frame = self.frame[length:]
                return _parse_response(*frame)


def _encode(key: str, keyup: bool = False):
    m = re.match(r'^KEYCODE_(ACPI|KB|MM)_([a-fA-F0-9]+)$', key)
    if m:
        encoder, _ = ENCODERS[m.group(1)]
        if keyup:
            return encoder(0)
        else:
            return encoder(int(m.group(2), 16))

    # Allow more control over the packets we send for exploratory testing:
    m = re.match(r'^RAW_([a-fA-F0-9]{2})_([a-fA-F0-9]+)_([a-fA-F0-9]+)$', key)
    if m:
        command = int(m.group(1), 16)
        data = bytes.fromhex(m.group(3 if keyup else 2))
        return _frame(0, command, data)

    for encoder, key_enum in ENCODERS.values():
        try:
            keycode = getattr(key_enum, key).value
        except AttributeError:
            continue
        if keyup:
            return encoder(0)
        else:
            return encoder(keycode)

    raise ValueError("Unknown key %r" % key)


def _encode_kb_general_data(keycode: int):
    # type: (int) -> bytes
    assert keycode < 0x100
    return _frame(
        0, CH9329Command.SEND_KB_GENERAL_DATA.value,
        struct.pack('BBBBBBBB', 0, 0, keycode, 0, 0, 0, 0, 0))


def _encode_acpi_key_data(keycode: int):
    # type: (int) -> bytes
    assert keycode < 0x100
    return _frame(
        0, CH9329Command.SEND_KB_MEDIA_DATA.value,
        struct.pack('BB', 0x01, keycode))


def _encode_mm_key_data(keycode: int):
    # type: (int) -> bytes
    assert keycode < 0x1000000
    return _frame(
        0, CH9329Command.SEND_KB_MEDIA_DATA.value,
        struct.pack('>I', keycode | 0x02000000))


def _frame(address: int, command: int, payload: bytes):
    # Big endian:
    frame = struct.pack('>HBBB', 0x57ab, address, command, len(payload)) + payload
    csum = sum(frame) & 0xff
    frame += struct.pack('B', csum)
    return frame


def _deframe(frame: bytes):
    if len(frame) < 6:
        raise NeedDataError(6 - len(frame))
    start_pos = frame.find(b'\x57\xab')
    discarded = 0
    if start_pos == -1:
        raise ValueError("Couldn't find header 57ab in frame %s" % (
            frame.hex()))
    elif start_pos > 0:
        logger.warning(
            "Discarding %iB unexpected data found before frame header: %s in buffer %s",
            start_pos, frame[:start_pos].hex(),
            frame.hex())
        discarded = start_pos
        frame = frame[start_pos:]
    if len(frame) < 6:
        raise NeedDataError(6 - len(frame))
    header, address, command, length = struct.unpack('>HBBB', frame[:5])
    assert isinstance(header, int)
    assert isinstance(address, int)
    assert isinstance(command, int)
    assert isinstance(length, int)
    assert header == 0x57ab
    frame_len = 6 + length
    if len(frame) < frame_len:
        raise NeedDataError(frame_len - len(frame))
    payload = frame[5:5 + length]
    csum = frame[5 + length]
    expected_csum = sum(frame[:5 + length]) & 0xff
    if csum != expected_csum:
        raise ValueError(
            "Checksum error.  Expected %02x, got %02x for frame %s" % (
                expected_csum, csum, frame.hex()))
    return (address, command, payload), frame_len + discarded


def test_deframe():
    def assert_need_data(frame: bytes, at_least: int):
        try:
            _deframe(frame)
            assert False, "Expected NeedDataError"
        except NeedDataError as e:
            assert e.at_least == at_least, e.at_least

    def parse(frame: bytes, expected_bytes_read=None):
        if expected_bytes_read is None:
            expected_bytes_read = len(frame)
        f, length = _deframe(frame)
        assert length == expected_bytes_read
        return _parse_response(*f)

    assert_need_data(b'', 6)
    assert_need_data(b'\x57', 5)

    assert _deframe(b'\x57\xab\x00\x00\x00\x02') == ((0, 0, b''), 6)
    assert _deframe(b'\x57\xab\x00\x00\x00\x02\x00') == ((0, 0, b''), 6)

    R = bytes.fromhex("57ab0081083801000000000000c4")
    EXPECTED = (0, CH9329Command.GET_INFO, b'\x38\x01\x00\x00\x00\x00\x00\x00')

    assert parse(R) == EXPECTED

    for junk_prefix in [b'', b'\x57', b'\xab', b'\x00\x00']:
        expected_bytes_read = len(R) + len(junk_prefix)
        for suffix in [b'', b'\x00', b'\x00\x00']:
            buf = junk_prefix + R + suffix
            for n in range(expected_bytes_read):
                try:
                    data, read_bytes = _deframe(buf[:n])
                    assert False
                except NeedDataError as e:
                    assert e.at_least > 0
                    assert n + e.at_least <= expected_bytes_read

            data, read_bytes = _deframe(buf)
            assert read_bytes == expected_bytes_read
            assert _parse_response(*data) == EXPECTED


def _parse_response(address: int, command: int, payload: bytes):
    if not command & 0x80:
        raise ValueError("Response command %02x is not a response" % command)
    if command & 0x40:
        assert len(payload) == 1
        error = CH9329Error(payload[0])
        raise ValueError("Response command %02x is an error: %r" % (
            command, error))
    return address, CH9329Command(command & 0x3f), payload


class CH9329Command(enum.Enum):
    GET_INFO = 0x01
    SEND_KB_GENERAL_DATA = 0x02
    SEND_KB_MEDIA_DATA = 0x03
    CMD_SEND_MS_ABS_DATA = 0x04
    CMD_SEND_MS_REL_DATA = 0x05
    CMD_SEND_MY_HID_DATA = 0x06
    CMD_READ_MY_HID_DATA = 0x07
    CMD_GET_PARA_CFG = 0x08
    CMD_SET_PARA_CFG = 0x09
    CMD_GET_USB_STRING = 0x0a
    CMD_SET_USB_STRING = 0x0b
    CMD_SET_DEFAULT_CFG = 0x0c
    CMD_RESET = 0x0f


class CH9329Modifier(enum.Enum):
    LEFT_CTRL = 1 << 0
    LEFT_SHIFT = 1 << 1
    LEFT_ALT = 1 << 2
    LEFT_META = 1 << 3
    RIGHT_CTRL = 1 << 4
    RIGHT_SHIFT = 1 << 5
    RIGHT_ALT = 1 << 6
    RIGHT_META = 1 << 7


class CH9329Error(enum.Enum):
    SUCCESS = 0x00
    TIMEOUT = 0xe1
    HEAD = 0xe2
    CMD = 0xe3
    SUM = 0xe4
    PARA = 0xe5
    OPERATE = 0xe6


CH9329_HEADER = 0x57ab  # Big endian


class NeedDataError(Exception):
    def __init__(self, at_least: int):
        self.at_least = at_least


class KeyboardPage(enum.Enum):
    "From https://source.android.com/docs/core/interaction/input/keyboard-devices"
    KEY_KB_A = 0x04
    KEY_KB_B = 0x05
    KEY_KB_C = 0x06
    KEY_KB_D = 0x07
    KEY_KB_E = 0x08
    KEY_KB_F = 0x09
    KEY_KB_G = 0x0a
    KEY_KB_H = 0x0b
    KEY_KB_I = 0x0c
    KEY_KB_J = 0x0d
    KEY_KB_K = 0x0e
    KEY_KB_L = 0x0f
    KEY_KB_M = 0x10
    KEY_KB_N = 0x11
    KEY_KB_O = 0x12
    KEY_KB_P = 0x13
    KEY_KB_Q = 0x14
    KEY_KB_R = 0x15
    KEY_KB_S = 0x16
    KEY_KB_T = 0x17
    KEY_KB_U = 0x18
    KEY_KB_V = 0x19
    KEY_KB_W = 0x1a
    KEY_KB_X = 0x1b
    KEY_KB_Y = 0x1c
    KEY_KB_Z = 0x1d
    KEY_KB_1 = 0x1e
    KEY_KB_2 = 0x1f
    KEY_KB_3 = 0x20
    KEY_KB_4 = 0x21
    KEY_KB_5 = 0x22
    KEY_KB_6 = 0x23
    KEY_KB_7 = 0x24
    KEY_KB_8 = 0x25
    KEY_KB_9 = 0x26
    KEY_KB_0 = 0x27
    KEY_KB_ENTER = 0x28
    KEY_KB_ESC = 0x29
    KEY_KB_BACKSPACE = 0x2a
    KEY_KB_TAB = 0x2b
    KEY_KB_SPACE = 0x2c
    KEY_KB_MINUS = 0x2d
    KEY_KB_EQUAL = 0x2e
    KEY_KB_LEFTBRACE = 0x2f
    KEY_KB_RIGHTBRACE = 0x30
    KEY_KB_BACKSLASH = 0x31
    KEY_KB_BACKSLASH2 = 0x32
    KEY_KB_SEMICOLON = 0x33
    KEY_KB_APOSTROPHE = 0x34
    KEY_KB_GRAVE = 0x35
    KEY_KB_COMMA = 0x36
    KEY_KB_DOT = 0x37
    KEY_KB_SLASH = 0x38
    KEY_KB_CAPSLOCK = 0x39
    KEY_KB_F1 = 0x3a
    KEY_KB_F2 = 0x3b
    KEY_KB_F3 = 0x3c
    KEY_KB_F4 = 0x3d
    KEY_KB_F5 = 0x3e
    KEY_KB_F6 = 0x3f
    KEY_KB_F7 = 0x40
    KEY_KB_F8 = 0x41
    KEY_KB_F9 = 0x42
    KEY_KB_F10 = 0x43
    KEY_KB_F11 = 0x44
    KEY_KB_F12 = 0x45
    KEY_KB_SYSRQ = 0x46
    KEY_KB_SCROLLLOCK = 0x47
    KEY_KB_PAUSE = 0x48
    KEY_KB_INSERT = 0x49
    KEY_KB_HOME = 0x4a
    KEY_KB_PAGEUP = 0x4b
    KEY_KB_DELETE = 0x4c
    KEY_KB_END = 0x4d
    KEY_KB_PAGEDOWN = 0x4e
    KEY_KB_RIGHT = 0x4f
    KEY_KB_LEFT = 0x50
    KEY_KB_DOWN = 0x51
    KEY_KB_UP = 0x52
    KEY_KB_NUMLOCK = 0x53
    KEY_KB_KPSLASH = 0x54
    KEY_KB_KPASTERISK = 0x55
    KEY_KB_KPMINUS = 0x56
    KEY_KB_KPPLUS = 0x57
    KEY_KB_KPENTER = 0x58
    KEY_KB_KP1 = 0x59
    KEY_KB_KP2 = 0x5a
    KEY_KB_KP3 = 0x5b
    KEY_KB_KP4 = 0x5c
    KEY_KB_KP5 = 0x5d
    KEY_KB_KP6 = 0x5e
    KEY_KB_KP7 = 0x5f
    KEY_KB_KP8 = 0x60
    KEY_KB_KP9 = 0x61
    KEY_KB_KP0 = 0x62
    KEY_KB_KPDOT = 0x63
    KEY_KB_102ND = 0x64
    KEY_KB_COMPOSE = 0x65
    KEY_KB_POWER = 0x66
    KEY_KB_KPEQUAL = 0x67
    KEY_KB_F13 = 0x68
    KEY_KB_F14 = 0x69
    KEY_KB_F15 = 0x6a
    KEY_KB_F16 = 0x6b
    KEY_KB_F17 = 0x6c
    KEY_KB_F18 = 0x6d
    KEY_KB_F19 = 0x6e
    KEY_KB_F20 = 0x6f
    KEY_KB_F21 = 0x70
    KEY_KB_F22 = 0x71
    KEY_KB_F23 = 0x72
    KEY_KB_F24 = 0x73
    KEY_KB_OPEN = 0x74
    KEY_KB_HELP = 0x75
    KEY_KB_PROPS = 0x76
    KEY_KB_FRONT = 0x77
    KEY_KB_STOP = 0x78
    KEY_KB_AGAIN = 0x79
    KEY_KB_UNDO = 0x7a
    KEY_KB_CUT = 0x7b
    KEY_KB_COPY = 0x7c
    KEY_KB_PASTE = 0x7d
    KEY_KB_FIND = 0x7e
    KEY_KB_MUTE = 0x7f
    KEY_KB_VOLUMEUP = 0x80
    KEY_KB_VOLUMEDOWN = 0x81
    KEY_KB_KPCOMMA = 0x85
    KEY_KB_RO = 0x87
    KEY_KB_KATAKANAHIRAGANA = 0x88
    KEY_KB_YEN = 0x89
    KEY_KB_HENKAN = 0x8a
    KEY_KB_MUHENKAN = 0x8b
    KEY_KB_KPJPCOMMA = 0x8c
    KEY_KB_HANGEUL = 0x90
    KEY_KB_HANJA = 0x91
    KEY_KB_KATAKANA = 0x92
    KEY_KB_HIRAGANA = 0x93
    KEY_KB_ZENKAKUHANKAKU = 0x94
    KEY_KB_KPLEFTPAREN = 0xb6
    KEY_KB_KPRIGHTPAREN = 0xb7
    KEY_KB_LEFTCTRL = 0xe0
    KEY_KB_LEFTSHIFT = 0xe1
    KEY_KB_LEFTALT = 0xe2
    KEY_KB_LEFTMETA = 0xe3
    KEY_KB_RIGHTCTRL = 0xe4
    KEY_KB_RIGHTSHIFT = 0xe5
    KEY_KB_RIGHTALT = 0xe6
    KEY_KB_RIGHTMETA = 0xe7
    KEY_KB_PLAYPAUSE = 0xe8
    KEY_KB_STOPCD = 0xe9
    KEY_KB_PREVIOUSSONG = 0xea
    KEY_KB_NEXTSONG = 0xeb
    KEY_KB_EJECTCD = 0xec
    KEY_KB_VOLUMEUP2 = 0xed
    KEY_KB_VOLUMEDOWN2 = 0xee
    KEY_KB_MUTE2 = 0xef
    KEY_KB_WWW = 0xf0
    KEY_KB_BACK = 0xf1
    KEY_KB_FORWARD = 0xf2
    KEY_KB_STOP2 = 0xf3
    KEY_KB_FIND2 = 0xf4
    KEY_KB_SCROLLUP = 0xf5
    KEY_KB_SCROLLDOWN = 0xf6
    KEY_KB_EDIT = 0xf7
    KEY_KB_SLEEP = 0xf8
    KEY_KB_COFFEE = 0xf9
    KEY_KB_REFRESH = 0xfa
    KEY_KB_CALC = 0xfb

    # Useful defaults, we may expand these in the future based on experience
    # with real devices:
    KEY_UP = KEY_KB_UP
    KEY_DOWN = KEY_KB_DOWN
    KEY_LEFT = KEY_KB_LEFT
    KEY_RIGHT = KEY_KB_RIGHT
    KEY_OK = KEY_KB_ENTER


ACPI_KEY_REPORT_ID = 0x01


class ACPIKeyCode(enum.Enum):
    KEY_ACPI_POWER = 0x01
    KEY_ACPI_SLEEP = 0x02
    KEY_ACPI_WAKE = 0x04


MULTIMEDIA_KEY_REPORT_ID = 0x02


class MultimediaKeyCode(enum.Enum):
    "3 bytes big endian"
    KEY_MM_VOLUMEUP = 1 << 0 + 16
    KEY_MM_VOLUMEDOWN = 1 << 1 + 16
    KEY_MM_MUTE = 1 << 2 + 16
    KEY_MM_PLAYPAUSE = 1 << 3 + 16
    KEY_MM_NEXT = 1 << 4 + 16
    KEY_MM_PREV = 1 << 5 + 16
    KEY_MM_STOPCD = 1 << 6 + 16
    KEY_MM_EJECT = 1 << 7 + 16

    KEY_MM_EMAIL = 1 << 8
    KEY_MM_SEARCH = 1 << 9
    KEY_MM_FAVOURITES = 1 << 10
    KEY_MM_HOME = 1 << 11
    KEY_MM_BACK = 1 << 12
    KEY_MM_FORWARD = 1 << 13
    KEY_MM_STOP = 1 << 14
    KEY_MM_REFRESH = 1 << 15

    KEY_MM_MEDIA = 1 << 16 - 16
    KEY_MM_MYCOMPUTER = 1 << 17 - 16
    KEY_MM_CALC = 1 << 18 - 16
    KEY_MM_SCREENSAVER = 1 << 19 - 16
    KEY_MM_COMPUTER = 1 << 20 - 16
    KEY_MM_MINIMIZE = 1 << 21 - 16
    KEY_MM_RECORD = 1 << 22 - 16
    KEY_MM_REWIND = 1 << 23 - 16


ENCODERS: "dict[str, tuple[typing.Callable[[int], bytes], typing.Type[enum.Enum]]]" = {
    'KB': (_encode_kb_general_data, KeyboardPage),
    'ACPI': (_encode_acpi_key_data, ACPIKeyCode),
    'MM': (_encode_mm_key_data, MultimediaKeyCode),
}
