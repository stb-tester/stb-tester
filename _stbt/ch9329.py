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
        keydown = _encode(key)
        logger.debug("Writing %s", keydown.hex())
        self.device.write(keydown)
        self._read_one()

    def keyup(self, key: str):
        keyup = _encode(key, keyup=True)
        logger.debug("Writing %s", keyup.hex())
        self.device.write(keyup)
        self._read_one()

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
    m = re.match(r'^KEYCODE?_(ACPI|KB|MM)_([a-fA-F0-9]+)$', key)
    if m:
        encoder, _ = ENCODERS[m.group(1)]
        if keyup:
            return encoder(0)
        else:
            return encoder(int(m.group(2), 16))

    m = re.match(r'^KEY?_(ACPI|KB|MM)_(.+)$', key)
    if m:
        encoder, key_enum = ENCODERS[m.group(1)]
        keycode = getattr(key_enum, "KEY_" + m.group(2)).value
        if keyup:
            return encoder(0)
        else:
            return encoder(keycode)

    # Allow more control over the packets we send for exploratory testing:
    m = re.match(r'^RAW_([a-fA-F0-9]{2})_([a-fA-F0-9]+)_([a-fA-F0-9]+)$', key)
    if m:
        command = int(m.group(1), 16)
        data = bytes.fromhex(m.group(3 if keyup else 2))
        return _frame(0, command, data)

    for encoder, key_enum in ENCODERS.values():
        try:
            keycode = getattr(key_enum, key).value
            if keyup:
                return encoder(0)
            else:
                return encoder(keycode)
        except AttributeError:
            pass

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
    header, address, command, length = struct.unpack('>HBBB', frame[:5])
    assert isinstance(header, int)
    assert isinstance(address, int)
    assert isinstance(command, int)
    assert isinstance(length, int)
    if header != 0x57ab:
        raise ValueError("Invalid header in frame %s.  Expected 0x%04x, got 0x%04x" % (
            frame.hex(), 0x57ab, header,
        ))
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
    return (address, command, payload), frame_len


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
    KEY_A = 0x04
    KEY_B = 0x05
    KEY_C = 0x06
    KEY_D = 0x07
    KEY_E = 0x08
    KEY_F = 0x09
    KEY_G = 0x0a
    KEY_H = 0x0b
    KEY_I = 0x0c
    KEY_J = 0x0d
    KEY_K = 0x0e
    KEY_L = 0x0f
    KEY_M = 0x10
    KEY_N = 0x11
    KEY_O = 0x12
    KEY_P = 0x13
    KEY_Q = 0x14
    KEY_R = 0x15
    KEY_S = 0x16
    KEY_T = 0x17
    KEY_U = 0x18
    KEY_V = 0x19
    KEY_W = 0x1a
    KEY_X = 0x1b
    KEY_Y = 0x1c
    KEY_Z = 0x1d
    KEY_1 = 0x1e
    KEY_2 = 0x1f
    KEY_3 = 0x20
    KEY_4 = 0x21
    KEY_5 = 0x22
    KEY_6 = 0x23
    KEY_7 = 0x24
    KEY_8 = 0x25
    KEY_9 = 0x26
    KEY_0 = 0x27
    KEY_ENTER = 0x28
    KEY_ESC = 0x29
    KEY_BACKSPACE = 0x2a
    KEY_TAB = 0x2b
    KEY_SPACE = 0x2c
    KEY_MINUS = 0x2d
    KEY_EQUAL = 0x2e
    KEY_LEFTBRACE = 0x2f
    KEY_RIGHTBRACE = 0x30
    KEY_BACKSLASH = 0x31
    KEY_BACKSLASH2 = 0x32
    KEY_SEMICOLON = 0x33
    KEY_APOSTROPHE = 0x34
    KEY_GRAVE = 0x35
    KEY_COMMA = 0x36
    KEY_DOT = 0x37
    KEY_SLASH = 0x38
    KEY_CAPSLOCK = 0x39
    KEY_F1 = 0x3a
    KEY_F2 = 0x3b
    KEY_F3 = 0x3c
    KEY_F4 = 0x3d
    KEY_F5 = 0x3e
    KEY_F6 = 0x3f
    KEY_F7 = 0x40
    KEY_F8 = 0x41
    KEY_F9 = 0x42
    KEY_F10 = 0x43
    KEY_F11 = 0x44
    KEY_F12 = 0x45
    KEY_SYSRQ = 0x46
    KEY_SCROLLLOCK = 0x47
    KEY_PAUSE = 0x48
    KEY_INSERT = 0x49
    KEY_HOME = 0x4a
    KEY_PAGEUP = 0x4b
    KEY_DELETE = 0x4c
    KEY_END = 0x4d
    KEY_PAGEDOWN = 0x4e
    KEY_RIGHT = 0x4f
    KEY_LEFT = 0x50
    KEY_DOWN = 0x51
    KEY_UP = 0x52
    KEY_NUMLOCK = 0x53
    KEY_KPSLASH = 0x54
    KEY_KPASTERISK = 0x55
    KEY_KPMINUS = 0x56
    KEY_KPPLUS = 0x57
    KEY_KPENTER = 0x58
    KEY_KP1 = 0x59
    KEY_KP2 = 0x5a
    KEY_KP3 = 0x5b
    KEY_KP4 = 0x5c
    KEY_KP5 = 0x5d
    KEY_KP6 = 0x5e
    KEY_KP7 = 0x5f
    KEY_KP8 = 0x60
    KEY_KP9 = 0x61
    KEY_KP0 = 0x62
    KEY_KPDOT = 0x63
    KEY_102ND = 0x64
    KEY_COMPOSE = 0x65
    KEY_POWER = 0x66
    KEY_KPEQUAL = 0x67
    KEY_F13 = 0x68
    KEY_F14 = 0x69
    KEY_F15 = 0x6a
    KEY_F16 = 0x6b
    KEY_F17 = 0x6c
    KEY_F18 = 0x6d
    KEY_F19 = 0x6e
    KEY_F20 = 0x6f
    KEY_F21 = 0x70
    KEY_F22 = 0x71
    KEY_F23 = 0x72
    KEY_F24 = 0x73
    KEY_OPEN = 0x74
    KEY_HELP = 0x75
    KEY_PROPS = 0x76
    KEY_FRONT = 0x77
    KEY_STOP = 0x78
    KEY_AGAIN = 0x79
    KEY_UNDO = 0x7a
    KEY_CUT = 0x7b
    KEY_COPY = 0x7c
    KEY_PASTE = 0x7d
    KEY_FIND = 0x7e
    KEY_MUTE = 0x7f
    KEY_VOLUMEUP = 0x80
    KEY_VOLUMEDOWN = 0x81
    KEY_KPCOMMA = 0x85
    KEY_RO = 0x87
    KEY_KATAKANAHIRAGANA = 0x88
    KEY_YEN = 0x89
    KEY_HENKAN = 0x8a
    KEY_MUHENKAN = 0x8b
    KEY_KPJPCOMMA = 0x8c
    KEY_HANGEUL = 0x90
    KEY_HANJA = 0x91
    KEY_KATAKANA = 0x92
    KEY_HIRAGANA = 0x93
    KEY_ZENKAKUHANKAKU = 0x94
    KEY_KPLEFTPAREN = 0xb6
    KEY_KPRIGHTPAREN = 0xb7
    KEY_LEFTCTRL = 0xe0
    KEY_LEFTSHIFT = 0xe1
    KEY_LEFTALT = 0xe2
    KEY_LEFTMETA = 0xe3
    KEY_RIGHTCTRL = 0xe4
    KEY_RIGHTSHIFT = 0xe5
    KEY_RIGHTALT = 0xe6
    KEY_RIGHTMETA = 0xe7
    KEY_PLAYPAUSE = 0xe8
    KEY_STOPCD = 0xe9
    KEY_PREVIOUSSONG = 0xea
    KEY_NEXTSONG = 0xeb
    KEY_EJECTCD = 0xec
    KEY_VOLUMEUP2 = 0xed
    KEY_VOLUMEDOWN2 = 0xee
    KEY_MUTE2 = 0xef
    KEY_WWW = 0xf0
    KEY_BACK = 0xf1
    KEY_FORWARD = 0xf2
    KEY_STOP2 = 0xf3
    KEY_FIND2 = 0xf4
    KEY_SCROLLUP = 0xf5
    KEY_SCROLLDOWN = 0xf6
    KEY_EDIT = 0xf7
    KEY_SLEEP = 0xf8
    KEY_COFFEE = 0xf9
    KEY_REFRESH = 0xfa
    KEY_CALC = 0xfb


ACPI_KEY_REPORT_ID = 0x01


class ACPIKeyCode(enum.Enum):
    KEY_POWER = 0x01
    KEY_SLEEP = 0x02
    KEY_WAKE = 0x04


MULTIMEDIA_KEY_REPORT_ID = 0x02


class MultimediaKeyCode(enum.Enum):
    "3 bytes big endian"
    KEY_VOLUMEUP = 1 << 0 + 16
    KEY_VOLUMEDOWN = 1 << 1 + 16
    KEY_MUTE = 1 << 2 + 16
    KEY_PLAYPAUSE = 1 << 3 + 16
    KEY_NEXT = 1 << 4 + 16
    KEY_PREV = 1 << 5 + 16
    KEY_STOPCD = 1 << 6 + 16
    KEY_EJECT = 1 << 7 + 16

    KEY_EMAIL = 1 << 8
    KEY_SEARCH = 1 << 9
    KEY_FAVOURITES = 1 << 10
    KEY_HOME = 1 << 11
    KEY_BACK = 1 << 12
    KEY_FORWARD = 1 << 13
    KEY_STOP = 1 << 14
    KEY_REFRESH = 1 << 15

    KEY_MEDIA = 1 << 16 - 16
    KEY_MYCOMPUTER = 1 << 17 - 16
    KEY_CALC = 1 << 18 - 16
    KEY_SCREENSAVER = 1 << 19 - 16
    KEY_COMPUTER = 1 << 20 - 16
    KEY_MINIMIZE = 1 << 21 - 16
    KEY_RECORD = 1 << 22 - 16
    KEY_REWIND = 1 << 23 - 16


ENCODERS: "dict[str, tuple[typing.Callable[[int], bytes], typing.Type[enum.Enum]]]" = {
    # Order here is significant: the first match is used if the type is
    # unspecified.
    'KB': (_encode_kb_general_data, KeyboardPage),
    'ACPI': (_encode_acpi_key_data, ACPIKeyCode),
    'MM': (_encode_mm_key_data, MultimediaKeyCode),
}
