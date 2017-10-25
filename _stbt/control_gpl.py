import re
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
        # 0x0E - 0x1F Reserved
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
        # 0x39 - 0x3F Reserved
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
        # 0x4F Reserved
        "KEY_ANGLE": 80,
        "KEY_SUB_PICTURE": 81,  # <- not in input-event-codes.h
        "KEY_VOD": 82,
        "KEY_EPG": 83,
        "KEY_TIMER_PROGRAMMING": 84,  # <- not in input-event-codes.h
        "KEY_CONFIG": 85,  # Initial Configuration
        # 0x56 - 0x5F Reserved

        # Deterministic UI Functions; unlike some normal keys these never act
        # as toggles. Some of these take additional operands but we don't
        # support that (the additional operands are always optional according
        # to the CEC spec).
        # None of these _FUNCTION names are in linux-event-codes.h.
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
        # Back to normal keys.

        # 0x6E - 0x70 Reserved

        # These have 2 names:
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
        # 0x77 - 0xFF Reserved
    }

    def __init__(self, device, source, destination):
        import cec
        if source is None:
            source = 1
        if isinstance(source, (str, unicode)):
            source = int(source, 16)
        if isinstance(destination, (str, unicode)):
            destination = int(destination, 16)

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

        if destination is None:
            ds = list(self._list_active_devices())
            debug("HDMI-CEC scan complete.  Found %r" % ds)
            if len(ds) == 0:
                raise HdmiCecError(
                    "Failed to find a device on the CEC bus to talk to.")
            # Choose the last one, the first one is likely to be a TV if there's
            # one plugged in
            destination = ds[-1]
            debug("HDMI-CEC: Chose to talk to device %i %r" % (
                destination, self.lib.GetDeviceOSDName(destination)))

        self.source = source
        self.destination = destination

    def press(self, key):
        from .control import UnknownKeyError
        keycode = self._KEYNAMES.get(key)
        if keycode is None:
            if isinstance(key, int):
                keycode = key
            elif re.match(r"^[0-9]+$", key):
                keycode = int(key, base=10)
            elif re.match(r"^0[xX][0-9a-fA-F]+$", key):
                keycode = int(key, base=16)
        if keycode is None or (isinstance(keycode, int) and
                               not 0 <= keycode <= 255):
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
                    Port:     %s
                    Vendor:   %x
                    Product:  %x""") %
                (adapter.strComName, adapter.iVendorId, adapter.iProductId))
            retval = adapter.strComName
        return retval

    def _list_active_devices(self):
        self.lib.RescanActiveDevices()
        active = self.lib.GetActiveDevices()

        # We get a fixed size array back.  libcec-python doesn't implement
        # iteration or bounds checking:
        for n in range(16):
            # active.primary is us
            if n != active.primary and active[n]:
                yield n


def test_hdmi_cec_control():
    from .control import uri_to_remote
    with _fake_cec() as io:
        r = uri_to_remote('hdmi-cec:test-device:7:a')
        r.press("KEY_UP")
        r.press("KEY_UP")
        r.press("KEY_POWER")
        r.press(74)
        r.press("74")
        r.press("0x4A")
        r.press("0x4a")

    assert io.getvalue() == dedent("""\
        Open('test-device')
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <01>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <01>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <40>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <4a>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <4a>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <4a>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <4a>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        """)


def test_hdmi_cec_control_defaults():
    from .control import uri_to_remote
    with _fake_cec() as io:
        r = uri_to_remote('hdmi-cec:test-device')
        r.press("KEY_OK")

    assert io.getvalue() == dedent("""\
        Open('test-device')
        RescanActiveDevices()
        GetActiveDevices()
        GetDeviceOSDName(4)
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

    def Open(_, device):
        io.write('Open(%r)\n' % device)
        return True

    def cec_cmd_get_data(cmd):
        # Ugly, but can't find another way to do it
        import ctypes
        return str(buffer(ctypes.cast(
            int(cmd.parameters.data), ctypes.POINTER(ctypes.c_uint8)).contents,
            0, cmd.parameters.size))

    def Transmit(_, cmd):
        io.write("Transmit(dest: 0x%x, src: 0x%x, op: 0x%x, data: <%s>)\n" % (
            cmd.destination, cmd.initiator, cmd.opcode,
            cec_cmd_get_data(cmd).encode('hex')))
        return True

    def RescanActiveDevices(_):
        io.write("RescanActiveDevices()\n")

    def GetActiveDevices(_):
        io.write("GetActiveDevices()\n")

        class _L(list):
            @property
            def primary(self):
                return 1

        return _L([False, True, False, False, True] + [False] * 11)

    def GetDeviceOSDName(_, destination):
        io.write("GetDeviceOSDName(%r)\n" % destination)
        return "Test"

    with patch('cec.ICECAdapter.Open', Open), \
            patch('cec.ICECAdapter.Transmit', Transmit), \
            patch('cec.ICECAdapter.RescanActiveDevices', RescanActiveDevices), \
            patch('cec.ICECAdapter.GetActiveDevices', GetActiveDevices), \
            patch('cec.ICECAdapter.GetDeviceOSDName', GetDeviceOSDName):
        yield io

controls = [
    # pylint: disable=line-too-long
    (r'hdmi-cec(:(?P<device>[^:]+)(:(?P<source>[^:]+)(:(?P<destination>[^:]+))?)?)?',
     HdmiCecControl),
]
