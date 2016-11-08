from contextlib import contextmanager
from textwrap import dedent

from .logging import debug


class HdmiCecError(Exception):
    pass


class HdmiCecControl(object):
    # Map our recommended keynames (from linux input-event-codes.h) to the
    # equivalent CEC commands.
    # The mapping between CEC commands and code can be found at
    # http://www.cec-o-matic.com or in HDMI-CEC specification 1.3a
    _KEYNAMES = {
        "KEY_OK": 0,
        "KEY_UP": 1,
        "KEY_DOWN": 2,
        "KEY_LEFT": 3,
        "KEY_RIGHT": 4,
        "KEY_RIGHT_UP": 5,
        "KEY_RIGHT_DOWN": 6,
        "KEY_LEFT_UP": 7,
        "KEY_LEFT_DOWN": 8,
        "KEY_ROOT_MENU": 9,
        "KEY_SETUP": 10,
        "KEY_CONTENTS_MENU": 11,  # <- not in input-event-codes.h
        "KEY_FAVORITE_MENU": 12,  # <- not in input-event-codes.h
        "KEY_BACK": 13,
        "KEY_0": 32,
        "KEY_1": 33,
        "KEY_2": 34,
        "KEY_3": 35,
        "KEY_4": 36,
        "KEY_5": 37,
        "KEY_6": 38,
        "KEY_7": 39,
        "KEY_8": 40,
        "KEY_9": 41,
        "KEY_DOT": 42,
        "KEY_ENTER": 43,
        "KEY_CLEAR": 44,
        "KEY_NEXT_FAVORITE": 47,  # <- not in input-event-codes.h
        "KEY_CHANNELUP": 48,
        "KEY_CHANNELDOWN": 49,
        "KEY_PREVIOUS": 50,
        "KEY_SOUND_SELECT": 51,  # <- not in input-event-codes.h
        "KEY_INPUT_SELECT": 52,  # <- not in input-event-codes.h
        "KEY_INFO": 53,
        "KEY_HELP": 54,
        "KEY_PAGEUP": 55,
        "KEY_PAGEDOWN": 56,
        "KEY_POWER": 64,
        "KEY_VOLUMEUP": 65,
        "KEY_VOLUMEDOWN": 66,
        "KEY_MUTE": 67,
        "KEY_PLAY": 68,
        "KEY_STOP": 69,
        "KEY_PAUSE": 70,
        "KEY_RECORD": 71,
        "KEY_REWIND": 72,
        "KEY_FASTFORWARD": 73,
        "KEY_EJECT": 74,
        "KEY_FORWARD": 75,
        "KEY_BACKWARD": 76,
        "KEY_STOP_RECORD": 77,
        "KEY_PAUSE_RECORD": 78,
        "KEY_ANGLE": 80,
        "KEY_SUB_PICTURE": 81,  # <- not in input-event-codes.h
        "KEY_VOD": 82,
        "KEY_EPG": 83,
        "KEY_TIMER_PROGRAMMING": 84,  # <- not in input-event-codes.h
        "KEY_CONFIG": 85,

        # Not sure what the difference is between KEY_PLAY and KEY_PLAY_FUNCTION
        # is but none of these _FUNCTION keys are in linux-event-codes.h:
        "KEY_PLAY_FUNCTION": 96,
        "KEY_PAUSE_PLAY_FUNCTION": 97,
        "KEY_RECORD_FUNCTION": 98,
        "KEY_PAUSE_RECORD_FUNCTION": 99,
        "KEY_STOP_FUNCTION": 100,
        "KEY_MUTE_FUNCTION": 101,
        "KEY_RESTORE_VOLUME_FUNCTION": 102,
        "KEY_TUNE_FUNCTION": 103,
        "KEY_SELECT_MEDIA_FUNCTION": 104,
        "KEY_SELECT_AV_INPUT_FUNCTION": 105,
        "KEY_SELECT_AUDIO_INPUT_FUNCTION": 106,
        "KEY_POWER_TOGGLE_FUNCTION": 107,
        "KEY_POWER_OFF_FUNCTION": 108,
        "KEY_POWER_ON_FUNCTION": 109,

        # Back to normal keys.  We duplicate these colour buttons because HDMI
        # doesn't make a distinction:
        "KEY_F1": 113,
        "KEY_BLUE": 113,
        "KEY_F2": 114,
        "KEY_RED": 114,
        "KEY_F3": 115,
        "KEY_GREEN": 115,
        "KEY_F4": 116,
        "KEY_YELLOW": 116,

        # And back to normal keys:
        "KEY_F5": 117,
        "KEY_DATA": 118,
    }

    def __init__(self, device, source, destination):
        import cec
        if source is None:
            source = 1
        if destination is None:
            destination = 4
        if isinstance(source, (str, unicode)):
            source = int(source, 16)
        if isinstance(destination, (str, unicode)):
            destination = int(destination, 16)

        self.source = source
        self.destination = destination

        self.cecconfig = cec.libcec_configuration()
        self.cecconfig.strDeviceName = "stb-tester"
        self.cecconfig.bActivateSource = 0
        self.cecconfig.deviceTypes.Add(cec.CEC_DEVICE_TYPE_RECORDING_DEVICE)
        self.cecconfig.clientVersion = cec.LIBCEC_VERSION_CURRENT
        self.lib = cec.ICECAdapter.Create(self.cecconfig)
        debug("libCEC version %s loaded: %s" % (
            self.lib.VersionToString(self.cecconfig.serverVersion),
            self.lib.GetLibInfo()))

        if device is None:
            device = self.detect_adapter()
            if device is None:
                raise HdmiCecError("No adapter found")
        if not self.lib.Open(device):
            raise HdmiCecError("Failed to open a connection to the CEC adapter")
        debug("Connection to CEC adapter opened")

    def press(self, key):
        from .control import UnknownKeyError
        keycode = self._KEYNAMES.get(key)
        if keycode is None:
            raise UnknownKeyError("HdmiCecControl: Unknown key %r" % key)
        cec_command = "%X%X:44:%02X" % (self.source, self.destination, keycode)
        key_down_cmd = self.lib.CommandFromString(cec_command)
        key_up_cmd = self.lib.CommandFromString(
            '%X%X:45' % (self.source, self.destination))

        debug("cec: Transmit %s as %s" % (key, cec_command))
        if not self.lib.Transmit(key_down_cmd):
            raise HdmiCecError(
                "Failed to send key down command %s" % cec_command)
        if not self.lib.Transmit(key_up_cmd):
            raise HdmiCecError(
                "Failed to send key up command %s" % cec_command)

    # detect an adapter and return the com port path
    def detect_adapter(self):
        retval = None
        adapters = self.lib.DetectAdapters()
        for adapter in adapters:
            debug(
                dedent("""\
                    Found a CEC adapter:"
                    Port:     %s" + adapter.strComName)
                    Vendor:   %x" + hex(adapter.iVendorId))
                    Product:  %x" + hex(adapter.iProductId))""") %
                (adapter.strComName, adapter.iVendorId, adapter.iProductId))
            retval = adapter.strComName
        return retval


def test_hdmi_cec_control():
    from .control import uri_to_remote
    with _fake_cec() as io:
        r = uri_to_remote('hdmi-cec:test-device:7:a')
        r.press("KEY_UP")
        r.press("KEY_UP")
        r.press("KEY_POWER")

    assert io.getvalue() == dedent("""\
        Open('test-device')
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <01>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <01>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <40>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        """)


def test_hdmi_cec_control_defaults():
    from .control import uri_to_remote
    with _fake_cec() as io:
        r = uri_to_remote('hdmi-cec:test-device')
        r.press("KEY_OK")

    assert io.getvalue() == dedent("""\
        Open('test-device')
        Transmit(dest: 0x4, src: 0x1, op: 0x44, data: <00>)
        Transmit(dest: 0x4, src: 0x1, op: 0x45, data: <>)
        """)


@contextmanager
def _fake_cec():
    import StringIO
    import pytest
    from mock import patch

    pytest.importorskip("cec")

    io = StringIO.StringIO()

    def fake_open(_, device):
        io.write('Open(%r)\n' % device)
        return True

    def cec_cmd_get_data(cmd):
        # Ugly, but can't find another way to do it
        import ctypes
        return str(buffer(ctypes.cast(
            int(cmd.parameters.data), ctypes.POINTER(ctypes.c_uint8)).contents,
            0, cmd.parameters.size))

    def fake_transmit(_, cmd):
        io.write("Transmit(dest: 0x%x, src: 0x%x, op: 0x%x, data: <%s>)\n" % (
            cmd.destination, cmd.initiator, cmd.opcode,
            cec_cmd_get_data(cmd).encode('hex')))
        return True

    with patch('cec.ICECAdapter.Open', fake_open), \
            patch('cec.ICECAdapter.Transmit', fake_transmit):
        yield io

controls = [
    # pylint: disable=line-too-long
    (r'hdmi-cec(:(?P<device>[^:]+)(:(?P<source>[^:]+)(:(?P<destination>[^:]+))?)?)?',
     HdmiCecControl),
]
