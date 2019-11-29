from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from future.utils import string_types
import codecs
import re
import sys
import threading
import time
from contextlib import contextmanager
from textwrap import dedent

from .logging import debug
from .utils import to_bytes


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
        "KEY_MENU": 9,
        "KEY_SETUP": 10,
        "KEY_CONTENTS_MENU": 11,  # <- not in input-event-codes.h
        "KEY_FAVORITE_MENU": 12,  # <- not in input-event-codes.h
        "KEY_BACK": 13,

        # 0x0E - 0x1F Reserved
        "KEY_TV": 16,  # Apple TV

        # Back to official CEC names
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
        # On Ubuntu 18.04 `cec/__init__.py` tries to import `_cec` but can't
        # find it.
        # https://bugs.launchpad.net/ubuntu/+source/libcec/+bug/1805620
        sys.path.insert(0, "/usr/lib/python2.7/dist-packages/cec")
        try:
            import cec  # pylint:disable=import-error
        finally:
            sys.path.pop(0)

        if source is None:
            source = 1
        if isinstance(source, string_types):
            source = int(source, 16)
        if isinstance(destination, string_types):
            destination = int(destination, 16)

        self.cecconfig = cec.libcec_configuration()
        self.cecconfig.strDeviceName = b"stb-tester"
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
        device = to_bytes(device)
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

        self.press_and_hold_thread = None
        self.press_and_holding = False
        self.lock = threading.Condition()

    def press(self, key):
        with self.lock:
            if self.press_and_holding:
                raise HdmiCecError(
                    "Can't call 'press' while holding another key")

            if not self.lib.Transmit(self.keydown_command(key)):
                raise HdmiCecError("Failed to send keydown for %s" % key)
            if not self.lib.Transmit(self.keyup_command()):
                raise HdmiCecError("Failed to send keyup for %s" % key)

        debug("Pressed %s" % key)

    def keydown(self, key):
        # CEC spec section 13.13.3 says that the receiver should assume a
        # keyup if it hasn't seen one within a receiver-determined timeframe
        # which can't be less than 550ms. For press-and-hold the initiator
        # should send repeated keydown commands (200 to 450ms apart) followed
        # by the final keyup.

        with self.lock:
            if self.press_and_holding:
                raise HdmiCecError(
                    "Can't call 'keydown' while holding another key")
            self.press_and_holding = True

            if not self.lib.Transmit(self.keydown_command(key)):
                raise HdmiCecError("Failed to send keydown for %s" % key)

            self.press_and_hold_thread = threading.Thread(
                target=self.send_keydowns, args=(key,))
            self.press_and_hold_thread.daemon = True
            self.press_and_hold_thread.start()
        debug("Holding %s" % key)

    def keyup(self, key):
        with self.lock:
            if not self.press_and_holding:
                raise HdmiCecError("Called 'keyup' when not holding a key down")
            self.press_and_holding = False
            thread = self.press_and_hold_thread
            self.press_and_hold_thread = None
            self.lock.notify_all()

        thread.join()

        with self.lock:
            if not self.lib.Transmit(self.keyup_command()):
                raise HdmiCecError("Failed to send keyup for %s" % key)
        debug("Released %s" % key)

    def send_keydowns(self, key):
        # CEC spec section 13.13.3 says that the receiver should assume a keyup
        # if it hasn't seen one within a receiver-determined timeframe which
        # can't be less than 550ms. For press-and-hold the initiator should
        # send repeated keydown commands (200 to 450ms apart) followed by the
        # final keyup.
        end_time = time.time() + 60
        next_press_deadline = time.time() + 0.3
        with self.lock:
            while True:
                self.lock.wait(max(0, next_press_deadline - time.time()))
                if not self.press_and_holding:
                    return
                if time.time() > end_time:
                    debug("cec: Warning: Releasing %s as I've been holding it "
                          "longer than 60 seconds" % key)
                    return
                next_press_deadline = time.time() + 0.3
                if not self.lib.Transmit(self.keydown_command(key)):
                    debug("cec: Warning: Failed to send repeated keydown for %s"
                          % key)

    def keydown_command(self, key):
        keycode = self.get_keycode(key)
        keydown_str = b"%X%X:44:%02X" % (self.source, self.destination, keycode)
        return self.lib.CommandFromString(keydown_str)

    def keyup_command(self):
        keyup_str = b"%X%X:45" % (self.source, self.destination)
        return self.lib.CommandFromString(keyup_str)

    def get_keycode(self, key):
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
        return keycode

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
    from .control import uri_to_control
    with _fake_cec() as io:
        r = uri_to_control('hdmi-cec:test-device:7:a')
        r.press("KEY_UP")
        r.press("KEY_UP")
        r.press("KEY_POWER")
        r.press(74)
        r.press("74")
        r.press("0x4A")
        r.press("0x4a")
        r.keydown("KEY_ROOT_MENU")
        time.sleep(0.7)
        r.keyup("KEY_ROOT_MENU")

    expected = dedent("""\
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
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <09>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <09>)
        Transmit(dest: 0xa, src: 0x7, op: 0x44, data: <09>)
        Transmit(dest: 0xa, src: 0x7, op: 0x45, data: <>)
        """)
    assert expected == io.getvalue()


def test_hdmi_cec_control_defaults():
    from .control import uri_to_control
    with _fake_cec() as io:
        r = uri_to_control('hdmi-cec:test-device')
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
    import io
    import pytest
    try:
        from unittest.mock import patch
    except ImportError:
        from mock import patch  # Python 2 backport

    pytest.importorskip("cec")

    io = io.BytesIO()

    def Open(_, device):
        io.write(b'Open(%r)\n' % device)
        return True

    def cec_cmd_get_data(cmd):
        # Ugly, but can't find another way to do it
        import ctypes
        return bytes(memoryview(ctypes.cast(  # pylint:disable=undefined-variable
            int(cmd.parameters.data), ctypes.POINTER(ctypes.c_uint8)).contents,
            0, cmd.parameters.size))

    def Transmit(_, cmd):
        io.write(b"Transmit(dest: 0x%x, src: 0x%x, op: 0x%x, data: <%s>)\n" % (
            cmd.destination, cmd.initiator, cmd.opcode,
            codecs.encode(cec_cmd_get_data(cmd), 'hex')))
        return True

    def RescanActiveDevices(_):
        io.write(b"RescanActiveDevices()\n")

    def GetActiveDevices(_):
        io.write(b"GetActiveDevices()\n")

        class _L(list):
            @property
            def primary(self):
                return 1

        return _L([False, True, False, False, True] + [False] * 11)

    def GetDeviceOSDName(_, destination):
        io.write(b"GetDeviceOSDName(%r)\n" % destination)
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
