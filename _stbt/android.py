# -*- coding: utf-8 -*-

"""Python module to control Android devices via `ADB`_ from Stb-tester scripts.

Copyright © 2017-2022 Stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).

.. _ADB: https://developer.android.com/studio/command-line/adb.html
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
import typing
from collections import namedtuple
from contextlib import contextmanager
from logging import getLogger

from enum import Enum

from _stbt.config import ConfigurationError, get_config

if typing.TYPE_CHECKING:
    from _stbt.imgutils import Frame


__all__ = [
    "adb",
    "AdbDevice",
    "AdbError",
    "CoordinateSystem",
]


logger = getLogger("stbt.android")


class CoordinateSystem(Enum):
    """How to translate coordinates from the video-frames processed by your
    test script, to the coordinates expected by ADB for tap & swipe events.

    When you tell ADB to send a tap or swipe event you must give it x & y
    coordinates. The coordinate system matches the orientation of the device.
    We'll call these the physical coordinates. For example my phone's display
    is Full HD (1080 pixels x 1920 pixels):

    ===================  ======  ======  ======================================
    Logical orientation  x       y       (0, 0) is
    ===================  ======  ======  ======================================
    Portrait             0-1080  0-1920  top-left
    Landscape            0-1920  0-1080  top-left (i.e. the top-right corner if
                                         the phone is physically in portrait)
    ===================  ======  ======  ======================================

    Note that an app can force the device to think it's in portrait orientation
    even if you're physically holding the device in landscape orientation. We
    call this the "logical orientation". Similarly, an app can force the device
    into logical landscape orientation even if you have switched off auto-rotate
    in the device's settings menu.

    The video-frames that you analyse in your test scripts may not match the
    physical resolution of the device. For example if you're using a camera
    pointed at the device's screen, the resolution of your screenshots (even
    after geometric correction by the `Stb-tester CAMERA`_) will depend on the
    resolution of the camera, not of the device under test.

    You can give `AdbDevice.tap` and `AdbDevice.swipe` the coordinates from
    your video-frame (for example, you can pass in ``stbt.match(...).region``)
    and the CoordinateSystem will ensure that the coordinates are converted to
    physical coordinates in the appropriate way before passing them on to ADB.

    .. _Stb-tester CAMERA: https://stb-tester.com/stb-tester-camera
    """

    ADB_NATIVE = 0
    """Frames are captured via ADB screenshot.

    Frames will be in the same orientation & resolution as the physical device.
    """

    ADB_720P = 1
    """Frames are captured via ADB screenshot and then scaled to 720p.

    Frames will be in the same orientation as the physical device, but scaled.
    """

    HDMI_720P = 2
    """
    Frames are captured via HDMI and scaled to 720p.

    Frames will always be in landscape orientation. If a mobile device is in
    portrait orientation, you'll get black bars to the left & right. If the
    device is in landscape orientation, the frame will match what you see on
    the device (this assumes that the device's physical aspect ratio matches
    the aspect ratio of HDMI).
    """

    CAMERA_720P = 3
    """Frames are captured from an `Stb-tester CAMERA`_ pointing at the
    device's screen.

    The camera & device must both be physically in landscape orientation.

    Frames will always be in landscape orientation; if the device is in logical
    portrait orientation the image will appear rotated 90° anti-clockwise.
    """


def adb(args, **subprocess_kwargs) -> subprocess.CompletedProcess:
    """Send commands to an Android device using `ADB`_.

    This is a convenience function. It will construct an `AdbDevice` with the
    default parameters (taken from your config files) and call `AdbDevice.adb`
    with the parameters given here.

    .. _ADB: https://developer.android.com/studio/command-line/adb.html
    """
    return AdbDevice().adb(args, **subprocess_kwargs)


class AdbDevice():
    """Send commands to an Android device using `ADB`_.

    Default values for each parameter can be specified in your "stbt.conf"
    config file under the "[android]" section.

    :param string address:
        IP address (if using Network ADB) or serial number (if connected via
        USB) of the Android device. You can get the serial number by running
        ``adb devices -l``. If not specified, this is read from
        "device_under_test.ip_address" in your :ref:`node-specific-config`.
    :param string adb_server:
        The ADB server (that is, the PC connected to the Android device).
        Defaults to localhost.
    :param string adb_binary:
        The path to the ADB client executable. Defaults to "adb".
    :param bool tcpip:
        The ADB server communicates with the Android device via TCP/IP, not
        USB. This requires that you have enabled Network ADB access on the
        device. Defaults to True if ``address`` is an IP address, False
        otherwise.

    .. _ADB: https://developer.android.com/studio/command-line/adb.html
    """

    def __init__(self, address: str|None = None,
                 adb_server: str|None = None,
                 adb_binary: str|None = None,
                 tcpip: bool|None = None,
                 coordinate_system: CoordinateSystem|None = None):

        self.address = address or get_config("device_under_test", "ip_address",
                                             default=None)
        self.adb_server = adb_server or get_config("android", "adb_server",
                                                   default=None)
        self.adb_binary = adb_binary or get_config("android", "adb_binary",
                                                   default="adb")

        if tcpip is None:
            tcpip = get_config("android", "tcpip", default=None, type_=bool)
        if tcpip is None:
            tcpip = _is_ip_address(self.address)
        self.tcpip = tcpip

        if self.tcpip:
            if not self.address:
                raise ConfigurationError('AdbDevice: If "tcpip=True" '
                                         'you must specify "address"')
            if ":" not in self.address:
                self.address = self.address + ":5555"

        self.coordinate_system = coordinate_system or get_config(
            "android", "coordinate_system", default=CoordinateSystem.HDMI_720P,
            type_=CoordinateSystem)

        self._setup_adb_key()

        if self.tcpip:
            self._connect(timeout=60)

    def _setup_adb_key(self):
        if os.path.exists(os.path.join(os.environ["HOME"], ".android/adbkey")):
            return
        import stbt_core
        root = stbt_core.TEST_PACK_ROOT
        if root is None:
            return
        if not os.path.exists(os.path.join(root, "config/android/adbkey")):
            raise ConfigurationError(
                "To run adb on the Stb-tester Node you must generate an ADB "
                "host key by running 'adb keygen config/android/adbkey' and "
                "commit the 'config/android' directory to git.")
        shutil.copytree(os.path.join(root, "config/android"),
                        os.path.join(os.environ["HOME"], ".android"))
        os.chmod(os.path.join(os.environ["HOME"], ".android/adbkey"), 0o600)

    def adb(self, args, *, timeout=None, **subprocess_kwargs) \
            -> subprocess.CompletedProcess:
        """Run any ADB command.

        For example, the following code will use "adb shell am start" to launch
        an app on the device::

            d = AdbDevice(...)
            d.adb(["shell", "am", "start", "-S",
                   "com.example.myapp/com.example.myapp.MainActivity"])

        Any keyword arguments are passed on to `subprocess.run`.

        :returns: `subprocess.CompletedProcess` from `subprocess.run`.
        :raises: `subprocess.CalledProcessError` if ``check`` is true and
            the adb process returns a non-zero exit status.
        :raises: `subprocess.TimeoutExpired` if ``timeout`` is specified and
            the adb process doesn't finish within that number of seconds.
        :raises: `stbt.android.AdbError` if ``adb connect`` fails.
        """
        if self.tcpip:
            self._connect(timeout)
        return self._adb(args, timeout=timeout, **subprocess_kwargs)

    def devices(self) -> str:
        """Output of ``adb devices -l``."""
        return self._adb(["devices", "-l"], verbose=False, timeout=5,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         encoding="utf-8").stdout

    def get_frame(self, coordinate_system=None) -> Frame:
        """Take a screenshot using ADB.

        If you are capturing video from the Android device via another method
        (namely, HDMI capture) sometimes it can be useful to capture a frame
        via ADB for debugging. This function will manipulate the ADB screenshot
        (scale and/or rotate it) to match the screenshots from your main
        video-capture method as closely as possible.

        :returns: A `stbt.Frame`, that is, an image in OpenCV format. Note that
            the ``time`` attribute won't be very accurate (probably to <0.5s or
            so).
        """

        import cv2
        import numpy
        from _stbt.imgutils import Frame

        if coordinate_system is None:
            coordinate_system = self.coordinate_system

        for attempt in range(1, 4):
            timestamp = time.time()
            data = self.adb(["shell", "screencap", "-p"],
                            timeout=60, capture_output=True) \
                       .stdout
            assert isinstance(data, bytes)
            header = data[:10]
            if data.startswith(b"\x89PNG\r\r\n"):
                # Older versions of `adb shell` convert LF to CRLF.
                # The PNG format is designed to detect this: It should start
                # with 0x89, followed by "PNG", followed by CRLF.
                data = data.replace(b"\r\n", b"\n")
            img = cv2.imdecode(
                numpy.asarray(bytearray(data), dtype=numpy.uint8),
                cv2.IMREAD_COLOR)
            if img is None:
                logger.warning(
                    "AdbDevice.get_frame: Failed to get screenshot "
                    "via ADB (attempt %d/3)\n"
                    "Header: %s, length: %d", attempt, header, len(data))
            else:
                break
        else:
            raise AdbError(
                "Failed to capture screenshot from android device")

        img = _resize(img, coordinate_system)
        return Frame(img, time=timestamp)

    def press(self, key) -> None:
        """Send a keypress.

        :param str key: An Android keycode as listed in
          <https://developer.android.com/reference/android/view/KeyEvent.html>.
          Also accepts standard Stb-tester key names like "KEY_HOME" and
          "KEY_BACK".
        """
        # "adb shell input keyevent xxx" always returns success, so we need to
        # validate key names.
        if key in _KEYCODE_MAPPINGS:  # pylint:disable=consider-using-get
            key = _KEYCODE_MAPPINGS[key]  # Map Stb-tester names to Android ones
        if key not in _ANDROID_KEYCODES:
            raise ValueError("Unknown key code %r" % (key,))
        logger.info("AdbDevice.press(%r)", key)
        self.adb(["shell", "input", "keyevent", key], timeout=10)

    def swipe(self, start_position, end_position) -> None:
        """Swipe from one point to another point.

        :param start_position:
            A `stbt.Region` or (x, y) tuple of coordinates at which to start.
        :param end_position:
            A `stbt.Region` or (x, y) tuple of coordinates at which to stop.

        Example::

          d.swipe((100, 100), (100, 400))

        """
        x1, y1 = _centre_point(start_position)
        x2, y2 = _centre_point(end_position)
        logger.info("AdbDevice.swipe((%d,%d), (%d,%d))", x1, y1, x2, y2)

        x1, y1 = self._to_native_coordinates(x1, y1)
        x2, y2 = self._to_native_coordinates(x2, y2)
        command = ["shell", "input", "swipe",
                   str(x1), str(y1), str(x2), str(y2)]
        self.adb(command, timeout=10)

    def tap(self, position) -> None:
        """Tap on a particular location.

        :param position: A `stbt.Region`, or an (x,y) tuple.

        Example::

            d.tap((100, 20))
            d.tap(stbt.match(...).region)

        """
        x, y = _centre_point(position)
        logger.info("AdbDevice.tap((%d,%d))", x, y)

        x, y = self._to_native_coordinates(x, y)
        self.adb(["shell", "input", "tap", str(x), str(y)], timeout=10)

    @contextmanager
    def logcat(self, filename="logcat.log", logcat_args=None):
        """Run ``adb logcat`` and stream the logs to ``filename``.

        This is a context manager. See :doc:`logs` for the recommended way
        to use it.

        :param str filename:
            Where the logs are written.

        :param list logcat_args:
            Optional arguments to pass on to ``adb logcat``, such as filter
            expressions. For example:
            ``logcat_args=["ActivityManager:I", "MyApp:D", "*:S"]``.
            See the `logcat documentation
            <https://developer.android.com/studio/command-line/logcat#options>`__.
        """
        collector = _LogcatCollector(filename, self, logcat_args)
        self.adb(["logcat", "--clear"])
        collector.run_in_background()
        try:
            yield
        finally:
            collector.stop()

    def _adb(self, args, verbose=True, **kwargs):
        _command = self._build_adb_command() + args
        if verbose:
            logger.debug("AdbDevice.adb: About to run command: %r", _command)
        return subprocess.run(_command, **kwargs)  # pylint:disable=subprocess-run-check

    def _Popen(self, args, **kwargs):
        """Like `AdbDevice.adb`, but runs `subprocess.Popen` instead of
        `subprocess.run`.
        """
        if self.tcpip:
            self._connect()
        _command = self._build_adb_command() + args
        logger.debug("AdbDevice._Popen: About to run command: %r", _command)
        return subprocess.Popen(_command, **kwargs)

    def _build_adb_command(self):
        _command = []
        _command += [self.adb_binary]
        if self.adb_server:
            _command += ["-H", self.adb_server]
        if self.address:
            _command += ["-s", self.address]
        return _command

    def _connect(self, timeout=None):
        assert self.address
        if self.address in self.devices():
            return

        if timeout is None:
            timeout = 60

        # "adb connect" always returns success; we have to parse the output
        # which looks like "connected to 192.168.2.163:5555" or
        # "already connected to 192.168.2.163:5555" or
        # "unable to connect to 192.168.2.100:5555".
        output = self._adb(["connect", self.address], timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           encoding="utf-8") \
                     .stdout
        if ("connected to %s" % self.address) not in output:
            logger.debug("%s", output)
            raise AdbError("adb connect %s failed" % self.address,
                           output=output, devices=self.devices())
        time.sleep(2)

    def _to_native_coordinates(self, x, y):
        if self.coordinate_system == CoordinateSystem.ADB_NATIVE:
            return x, y
        else:
            return _to_native_coordinates(
                x, y, self.coordinate_system, self._get_display_dimensions())

    def _get_display_dimensions(self):
        return _parse_display_dimensions(
            self.adb(["shell", "dumpsys", "window"],
                     timeout=10, capture_output=True).stdout)


class AdbError(Exception):
    """Exception raised by `AdbDevice.adb`.

    :ivar int returncode: Exit status of the adb command.
    :ivar list cmd: The command that failed, as given to `AdbDevice.adb`.
    :ivar str output: The output from adb.
    :ivar str devices: The output from "adb devices -l" (useful for
        debugging connection errors).
    """

    def __init__(self, message, returncode=None, cmd=None, output=None,
                 devices=None):
        super().__init__()
        self.message = message
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
        self.devices = devices

    def __str__(self):
        return self.message


class _LogcatCollector():
    def __init__(self, filename, adb_device, logcat_args=None):
        self.filename = filename
        self.adb_device = adb_device
        self.logcat_args = logcat_args or []
        self.stopping = False
        self.thread = None
        self.process = None

    def run_in_background(self):
        thread = threading.Thread(target=self.run)
        thread.daemon = True
        self.thread = thread
        thread.start()

    def run(self):
        with open(self.filename, "wb", 0) as f:
            while True:
                # Re-run "adb logcat" in case of disconnections. I assume this
                # means the device-under-test crashed/rebooted so we don't need
                # to run "logcat --clear" again. If this assumption is wrong
                # we'll end up with some duplicate log lines. :shrug:
                self.process = self.adb_device._Popen(
                    ['logcat'] + self.logcat_args, stdout=f)
                self.process.wait()
                if self.stopping:
                    return
                logger.warning("logcat: Lost adb connection")
                time.sleep(1)

    def stop(self):
        self.stopping = True
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()


# https://developer.android.com/reference/android/view/KeyEvent.html
#
# I generated this list with:
#
#   curl https://android.googlesource.com/platform/frameworks/base/+/master/core/java/android/view/KeyEvent.java?format=TEXT |
#   base64 -d | grep -o 'KEYCODE_[A-Z0-9_]*' | sort | uniq |
#   grep -v -e KEYCODE_UNKNOWN -e 'KEYCODE_$' | sed 's/^.*$/    "&",/'
_ANDROID_KEYCODES = [
    "KEYCODE_0",
    "KEYCODE_1",
    "KEYCODE_11",
    "KEYCODE_12",
    "KEYCODE_2",
    "KEYCODE_3",
    "KEYCODE_3D_MODE",
    "KEYCODE_4",
    "KEYCODE_5",
    "KEYCODE_6",
    "KEYCODE_7",
    "KEYCODE_8",
    "KEYCODE_9",
    "KEYCODE_A",
    "KEYCODE_ALL_APPS",
    "KEYCODE_ALT_LEFT",
    "KEYCODE_ALT_RIGHT",
    "KEYCODE_APOSTROPHE",
    "KEYCODE_APP_SWITCH",
    "KEYCODE_ASSIST",
    "KEYCODE_AT",
    "KEYCODE_AVR_INPUT",
    "KEYCODE_AVR_POWER",
    "KEYCODE_B",
    "KEYCODE_BACK",
    "KEYCODE_BACKSLASH",
    "KEYCODE_BOOKMARK",
    "KEYCODE_BREAK",
    "KEYCODE_BRIGHTNESS_DOWN",
    "KEYCODE_BRIGHTNESS_UP",
    "KEYCODE_BUTTON_1",
    "KEYCODE_BUTTON_10",
    "KEYCODE_BUTTON_11",
    "KEYCODE_BUTTON_12",
    "KEYCODE_BUTTON_13",
    "KEYCODE_BUTTON_14",
    "KEYCODE_BUTTON_15",
    "KEYCODE_BUTTON_16",
    "KEYCODE_BUTTON_2",
    "KEYCODE_BUTTON_3",
    "KEYCODE_BUTTON_4",
    "KEYCODE_BUTTON_5",
    "KEYCODE_BUTTON_6",
    "KEYCODE_BUTTON_7",
    "KEYCODE_BUTTON_8",
    "KEYCODE_BUTTON_9",
    "KEYCODE_BUTTON_A",
    "KEYCODE_BUTTON_B",
    "KEYCODE_BUTTON_C",
    "KEYCODE_BUTTON_L1",
    "KEYCODE_BUTTON_L2",
    "KEYCODE_BUTTON_MODE",
    "KEYCODE_BUTTON_R1",
    "KEYCODE_BUTTON_R2",
    "KEYCODE_BUTTON_SELECT",
    "KEYCODE_BUTTON_START",
    "KEYCODE_BUTTON_THUMBL",
    "KEYCODE_BUTTON_THUMBR",
    "KEYCODE_BUTTON_X",
    "KEYCODE_BUTTON_Y",
    "KEYCODE_BUTTON_Z",
    "KEYCODE_C",
    "KEYCODE_CALCULATOR",
    "KEYCODE_CALENDAR",
    "KEYCODE_CALL",
    "KEYCODE_CAMERA",
    "KEYCODE_CAPS_LOCK",
    "KEYCODE_CAPTIONS",
    "KEYCODE_CHANNEL_DOWN",
    "KEYCODE_CHANNEL_UP",
    "KEYCODE_CLEAR",
    "KEYCODE_COMMA",
    "KEYCODE_CONTACTS",
    "KEYCODE_COPY",
    "KEYCODE_CTRL_LEFT",
    "KEYCODE_CTRL_RIGHT",
    "KEYCODE_CUT",
    "KEYCODE_D",
    "KEYCODE_DEL",
    "KEYCODE_DPAD_CENTER",
    "KEYCODE_DPAD_DOWN",
    "KEYCODE_DPAD_DOWN_LEFT",
    "KEYCODE_DPAD_DOWN_RIGHT",
    "KEYCODE_DPAD_LEFT",
    "KEYCODE_DPAD_RIGHT",
    "KEYCODE_DPAD_UP",
    "KEYCODE_DPAD_UP_LEFT",
    "KEYCODE_DPAD_UP_RIGHT",
    "KEYCODE_DVR",
    "KEYCODE_E",
    "KEYCODE_EISU",
    "KEYCODE_ENDCALL",
    "KEYCODE_ENTER",
    "KEYCODE_ENVELOPE",
    "KEYCODE_EQUALS",
    "KEYCODE_ESCAPE",
    "KEYCODE_EXPLORER",
    "KEYCODE_F",
    "KEYCODE_F1",
    "KEYCODE_F10",
    "KEYCODE_F11",
    "KEYCODE_F12",
    "KEYCODE_F2",
    "KEYCODE_F3",
    "KEYCODE_F4",
    "KEYCODE_F5",
    "KEYCODE_F6",
    "KEYCODE_F7",
    "KEYCODE_F8",
    "KEYCODE_F9",
    "KEYCODE_FOCUS",
    "KEYCODE_FORWARD",
    "KEYCODE_FORWARD_DEL",
    "KEYCODE_FUNCTION",
    "KEYCODE_G",
    "KEYCODE_GRAVE",
    "KEYCODE_GUIDE",
    "KEYCODE_H",
    "KEYCODE_HEADSETHOOK",
    "KEYCODE_HELP",
    "KEYCODE_HENKAN",
    "KEYCODE_HOME",
    "KEYCODE_I",
    "KEYCODE_INFO",
    "KEYCODE_INSERT",
    "KEYCODE_J",
    "KEYCODE_K",
    "KEYCODE_KANA",
    "KEYCODE_KATAKANA_HIRAGANA",
    "KEYCODE_L",
    "KEYCODE_LANGUAGE_SWITCH",
    "KEYCODE_LAST_CHANNEL",
    "KEYCODE_LEFT_BRACKET",
    "KEYCODE_M",
    "KEYCODE_MANNER_MODE",
    "KEYCODE_MEDIA_AUDIO_TRACK",
    "KEYCODE_MEDIA_CLOSE",
    "KEYCODE_MEDIA_EJECT",
    "KEYCODE_MEDIA_FAST_FORWARD",
    "KEYCODE_MEDIA_NEXT",
    "KEYCODE_MEDIA_PAUSE",
    "KEYCODE_MEDIA_PLAY",
    "KEYCODE_MEDIA_PLAY_PAUSE",
    "KEYCODE_MEDIA_PREVIOUS",
    "KEYCODE_MEDIA_RECORD",
    "KEYCODE_MEDIA_REWIND",
    "KEYCODE_MEDIA_SKIP_BACKWARD",
    "KEYCODE_MEDIA_SKIP_FORWARD",
    "KEYCODE_MEDIA_STEP_BACKWARD",
    "KEYCODE_MEDIA_STEP_FORWARD",
    "KEYCODE_MEDIA_STOP",
    "KEYCODE_MEDIA_TOP_MENU",
    "KEYCODE_MENU",
    "KEYCODE_META_LEFT",
    "KEYCODE_META_RIGHT",
    "KEYCODE_MINUS",
    "KEYCODE_MOVE_END",
    "KEYCODE_MOVE_HOME",
    "KEYCODE_MUHENKAN",
    "KEYCODE_MUSIC",
    "KEYCODE_MUTE",
    "KEYCODE_N",
    "KEYCODE_NAVIGATE_IN",
    "KEYCODE_NAVIGATE_NEXT",
    "KEYCODE_NAVIGATE_OUT",
    "KEYCODE_NAVIGATE_PREVIOUS",
    "KEYCODE_NOTIFICATION",
    "KEYCODE_NUM",
    "KEYCODE_NUM_LOCK",
    "KEYCODE_NUMPAD_0",
    "KEYCODE_NUMPAD_1",
    "KEYCODE_NUMPAD_2",
    "KEYCODE_NUMPAD_3",
    "KEYCODE_NUMPAD_4",
    "KEYCODE_NUMPAD_5",
    "KEYCODE_NUMPAD_6",
    "KEYCODE_NUMPAD_7",
    "KEYCODE_NUMPAD_8",
    "KEYCODE_NUMPAD_9",
    "KEYCODE_NUMPAD_ADD",
    "KEYCODE_NUMPAD_COMMA",
    "KEYCODE_NUMPAD_DIVIDE",
    "KEYCODE_NUMPAD_DOT",
    "KEYCODE_NUMPAD_ENTER",
    "KEYCODE_NUMPAD_EQUALS",
    "KEYCODE_NUMPAD_LEFT_PAREN",
    "KEYCODE_NUMPAD_MULTIPLY",
    "KEYCODE_NUMPAD_RIGHT_PAREN",
    "KEYCODE_NUMPAD_SUBTRACT",
    "KEYCODE_O",
    "KEYCODE_P",
    "KEYCODE_PAGE_DOWN",
    "KEYCODE_PAGE_UP",
    "KEYCODE_PAIRING",
    "KEYCODE_PASTE",
    "KEYCODE_PERIOD",
    "KEYCODE_PICTSYMBOLS",
    "KEYCODE_PLUS",
    "KEYCODE_POUND",
    "KEYCODE_POWER",
    "KEYCODE_PROG_BLUE",
    "KEYCODE_PROG_GREEN",
    "KEYCODE_PROG_RED",
    "KEYCODE_PROG_YELLOW",
    "KEYCODE_Q",
    "KEYCODE_R",
    "KEYCODE_RIGHT_BRACKET",
    "KEYCODE_RO",
    "KEYCODE_S",
    "KEYCODE_SCROLL_LOCK",
    "KEYCODE_SEARCH",
    "KEYCODE_SEMICOLON",
    "KEYCODE_SETTINGS",
    "KEYCODE_SHIFT_LEFT",
    "KEYCODE_SHIFT_RIGHT",
    "KEYCODE_SLASH",
    "KEYCODE_SLEEP",
    "KEYCODE_SOFT_LEFT",
    "KEYCODE_SOFT_RIGHT",
    "KEYCODE_SOFT_SLEEP",
    "KEYCODE_SPACE",
    "KEYCODE_STAR",
    "KEYCODE_STB_INPUT",
    "KEYCODE_STB_POWER",
    "KEYCODE_STEM_1",
    "KEYCODE_STEM_2",
    "KEYCODE_STEM_3",
    "KEYCODE_STEM_PRIMARY",
    "KEYCODE_SWITCH_CHARSET",
    "KEYCODE_SYM",
    "KEYCODE_SYSRQ",
    "KEYCODE_SYSTEM_NAVIGATION_DOWN",
    "KEYCODE_SYSTEM_NAVIGATION_LEFT",
    "KEYCODE_SYSTEM_NAVIGATION_RIGHT",
    "KEYCODE_SYSTEM_NAVIGATION_UP",
    "KEYCODE_T",
    "KEYCODE_TAB",
    "KEYCODE_TV",
    "KEYCODE_TV_ANTENNA_CABLE",
    "KEYCODE_TV_AUDIO_DESCRIPTION",
    "KEYCODE_TV_AUDIO_DESCRIPTION_MIX_DOWN",
    "KEYCODE_TV_AUDIO_DESCRIPTION_MIX_UP",
    "KEYCODE_TV_CONTENTS_MENU",
    "KEYCODE_TV_DATA_SERVICE",
    "KEYCODE_TV_INPUT",
    "KEYCODE_TV_INPUT_COMPONENT_1",
    "KEYCODE_TV_INPUT_COMPONENT_2",
    "KEYCODE_TV_INPUT_COMPOSITE_1",
    "KEYCODE_TV_INPUT_COMPOSITE_2",
    "KEYCODE_TV_INPUT_HDMI_1",
    "KEYCODE_TV_INPUT_HDMI_2",
    "KEYCODE_TV_INPUT_HDMI_3",
    "KEYCODE_TV_INPUT_HDMI_4",
    "KEYCODE_TV_INPUT_VGA_1",
    "KEYCODE_TV_MEDIA_CONTEXT_MENU",
    "KEYCODE_TV_NETWORK",
    "KEYCODE_TV_NUMBER_ENTRY",
    "KEYCODE_TV_POWER",
    "KEYCODE_TV_RADIO_SERVICE",
    "KEYCODE_TV_SATELLITE",
    "KEYCODE_TV_SATELLITE_BS",
    "KEYCODE_TV_SATELLITE_CS",
    "KEYCODE_TV_SATELLITE_SERVICE",
    "KEYCODE_TV_TELETEXT",
    "KEYCODE_TV_TERRESTRIAL_ANALOG",
    "KEYCODE_TV_TERRESTRIAL_DIGITAL",
    "KEYCODE_TV_TIMER_PROGRAMMING",
    "KEYCODE_TV_ZOOM_MODE",
    "KEYCODE_U",
    "KEYCODE_V",
    "KEYCODE_VOICE_ASSIST",
    "KEYCODE_VOLUME_DOWN",
    "KEYCODE_VOLUME_MUTE",
    "KEYCODE_VOLUME_UP",
    "KEYCODE_W",
    "KEYCODE_WAKEUP",
    "KEYCODE_WINDOW",
    "KEYCODE_X",
    "KEYCODE_Y",
    "KEYCODE_YEN",
    "KEYCODE_Z",
    "KEYCODE_ZENKAKU_HANKAKU",
    "KEYCODE_ZOOM_IN",
    "KEYCODE_ZOOM_OUT",
]


# Map a few standard Stb-tester key names to Android keycodes.
# So far we just map the buttons on the Amazon Fire TV & NVidia Shield remote
# controls:
# https://developer.amazon.com/docs/fire-tv/remote-input.html#input-event-reference
_KEYCODE_MAPPINGS = {
    "KEY_BACK": "KEYCODE_BACK",
    "KEY_DOWN": "KEYCODE_DPAD_DOWN",
    "KEY_FASTFORWARD": "KEYCODE_MEDIA_FAST_FORWARD",
    "KEY_HOME": "KEYCODE_HOME",
    "KEY_LEFT": "KEYCODE_DPAD_LEFT",
    "KEY_MENU": "KEYCODE_MENU",
    "KEY_MUTE": "KEYCODE_VOLUME_MUTE",
    "KEY_OK": "KEYCODE_ENTER",
    "KEY_PAUSE": "KEYCODE_MEDIA_PAUSE",
    "KEY_PLAY": "KEYCODE_MEDIA_PLAY",
    "KEY_PLAYPAUSE": "KEYCODE_MEDIA_PLAY_PAUSE",
    "KEY_POWER": "KEYCODE_POWER",
    "KEY_REWIND": "KEYCODE_MEDIA_REWIND",
    "KEY_RIGHT": "KEYCODE_DPAD_RIGHT",
    "KEY_UP": "KEYCODE_DPAD_UP",
    "KEY_VOLUMEDOWN": "KEYCODE_VOLUME_DOWN",
    "KEY_VOLUMEUP": "KEYCODE_VOLUME_UP",
}


def _is_ip_address(address):
    """
    >>> _is_ip_address("")
    False
    >>> _is_ip_address(None)
    False
    >>> _is_ip_address("7278681B045C937CEB770FD31542B16")
    False
    >>> _is_ip_address("192.168.2.11")
    True
    >>> _is_ip_address("192.168.2.11:5555")
    True
    >>> _is_ip_address("192.168.2.11:5555")
    True
    """
    return bool(re.match(r"^\d+\.\d+\.\d+\.\d+(:\d+)?$", str(address)))


def _resize(img, coordinate_system):
    import cv2
    import numpy

    w, h = img.shape[1], img.shape[0]

    if coordinate_system == CoordinateSystem.ADB_NATIVE:
        pass
    elif coordinate_system == CoordinateSystem.ADB_720P:
        # Resize to 720p preserving orientation
        if w > h:
            img = cv2.resize(img, (1280, 720))
        else:
            img = cv2.resize(img, (720, 1280))
    elif coordinate_system == CoordinateSystem.HDMI_720P:
        if w > h:
            # Landscape: The device's screen fills the HDMI frame.
            # (this assumes that the device's aspect ratio is 16:9).
            img = cv2.resize(img, (1280, 720))
        else:
            # Portrait image in a landscape frame, with black letterboxing
            # on either side.
            ratio = float(h) / 720
            w_new = int(w // ratio)
            img = cv2.resize(img, (w_new, 720))
            left = (1280 - w_new) // 2
            img = cv2.copyMakeBorder(img, 0, 0, left, 1280 - w_new - left,
                                     cv2.BORDER_CONSTANT, (0, 0, 0))
    elif coordinate_system == CoordinateSystem.CAMERA_720P:
        # Resize to 720p landscape for compatibility with screenshots from
        # `stbt.get_frame` with the Stb-tester CAMERA.
        if w > h:
            img = cv2.resize(img, (1280, 720))
        else:
            img = numpy.rot90(cv2.resize(img, (720, 1280)))
    else:
        raise NotImplementedError(
            "AdbDevice.get_frame not implemented for %s. "
            "Use coordinate_system=CoordinateSystem.ADB_NATIVE"
            % coordinate_system)

    return img


def _centre_point(r):
    try:
        if all(hasattr(r, name) for name in ("x", "y", "right", "bottom")):
            return (int((r.x + r.right) // 2), int((r.y + r.bottom) // 2))
        elif isinstance(r, tuple) and len(r) == 2:
            return (int(r[0]), int(r[1]))
    except (TypeError, ValueError):
        pass
    raise TypeError("Expected stbt.Region or (x,y) tuple but got %r" % (r,))


_Dimensions = namedtuple("Dimensions", "width height")


def _to_native_coordinates(x, y, coordinate_system, device):
    if coordinate_system == CoordinateSystem.ADB_720P:
        # x & y orientation matches device's orientation
        if device.width > device.height:
            return int(x * device.width / 1280), int(y * device.height / 720)
        else:
            return int(x * device.width / 720), int(y * device.height / 1280)
    elif coordinate_system == CoordinateSystem.HDMI_720P:
        if device.width > device.height:
            # Landscape: Assume the device's native resolution is the same
            # aspect ratio as the HDMI output (i.e. no letterboxing).
            return int(x * device.width / 1280), int(y * device.height / 720)
        else:
            # Portrait image within a landscape screenshot, with black
            # letterboxing on either side. If we assume the device is 16:9
            # aspect ratio and fills the frame vertically, then the device
            # fills pixels 438 to 842 horizontally (404px wide).
            #
            # /-----------------\
            # |######     ######|  ^
            # |######     ######| 720
            # |######     ######|
            # |######     ######|  v
            # \-----------------/
            #        <404>
            #
            if not 438 <= x < 842:
                raise ValueError(
                    "Coordinates %d,%d are outside of the image area that "
                    "corresponds to the device under test" % (x, y))
            x = (x - 438) * 720 / 404
            return int(x * device.width / 720), int(y * device.height / 720)
    elif coordinate_system == CoordinateSystem.CAMERA_720P:
        # x & y coordinates are always from a 720p landscape screenshot.
        if device.width > device.height:
            # Landscape: Device orientation matches x & y.
            return int(x * device.width / 1280), int(y * device.height / 720)
        else:
            # Portrait: The image is rotated 90° anti-clockwise. The device's
            # origin (top-left) corresponds to the bottom-left corner of the
            # screenshot.
            #
            # /--------------------\    /-----\
            # |                    |    |     |
            # |                    |    |     |
            # |                    | => |%    |
            # |                    |    |     |
            # |  %                 |    |     |
            # \--------------------/    ~     ~
            #
            x, y = 720 - y, x
            return int(x * device.width / 720), int(y * device.height / 1280)
    else:
        raise NotImplementedError(
            "AdbDevice: Mapping to native coordinates not implemented for %s"
            % coordinate_system)


def _parse_display_dimensions(dumpsys_output):
    in_display = False
    for line in dumpsys_output.split("\n"):
        if "Display:" in line:
            in_display = True
        if not in_display:
            continue
        m = re.search(r"cur=(\d+)x(\d+)", line)
        if m:
            return _Dimensions(width=int(m.group(1)), height=int(m.group(2)))
    raise AdbError("Didn't find display size in dumpsys output",
                   output=dumpsys_output)
