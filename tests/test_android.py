from __future__ import division

import os
import re
import time
from textwrap import dedent
from unittest import SkipTest

import cv2
import pytest

from stbt import match, Region, wait_until
from stbt.android import (_Dimensions, _parse_display_dimensions,
                          _region_to_tuple, _to_native_coordinates, AdbDevice,
                          AdbError, CoordinateSystem)


@pytest.mark.parametrize("r", [
    Region(10, 10, width=30, height=5),
    (25, 12),
    ("25", "12"),
])
def test_region_to_tuple(r):
    assert _region_to_tuple(r) == (25, 12)


@pytest.mark.parametrize("r", [
    25,
    (25,),
    (25, 12, 15),
    "25",
])
def test_region_to_tuple_raises(r):
    with pytest.raises(TypeError):
        _region_to_tuple(r)


@pytest.mark.parametrize("orientation,device_resolution,expected_coordinates", [
    # These parameters describe the device under test.
    ("portrait", (720, 1280), (665, 105)),
    ("portrait", (750, 1334), (692, 109)),
    ("portrait", (1080, 1920), (997, 157)),
    ("landscape", (1280, 720), (1008, 48)),
    ("landscape", (1334, 750), (1051, 50)),
    ("landscape", (1920, 1080), (1513, 72)),
])
@pytest.mark.parametrize("coordinate_system", [
    # How we capture video frames from the device.
    CoordinateSystem.ADB_720P,
    CoordinateSystem.HDMI_720P,
    CoordinateSystem.CAMERA_720P,
])
def test_to_native_coordinates(
        orientation, device_resolution, expected_coordinates,
        coordinate_system):

    description = "{source}-{orientation}".format(
        source=coordinate_system.name.lower().replace("_", "-"),
        orientation=orientation)
    screenshot = cv2.imread(_find_file(
        "images/android-%s-screenshot.png" % description))
    icon = "images/android-%s-reference.png" % description

    m = match(icon, screenshot)
    screenshot_x, screenshot_y = _region_to_tuple(m.region)
    native_x, native_y = _to_native_coordinates(
        screenshot_x, screenshot_y, coordinate_system,
        _Dimensions(*device_resolution))
    print(native_x, native_y)
    assert isclose(native_x, expected_coordinates[0], absolute_tolerance=1)
    assert isclose(native_y, expected_coordinates[1], absolute_tolerance=1)


def test_parse_display_dimensions():
    moto_x2_portrait = dedent("""\
        [...]
        WINDOW MANAGER DISPLAY CONTENTS (dumpsys window displays)
          Display: mDisplayId=0
            init=1080x1920 480dpi cur=1080x1920 app=1080x1776 rng=1080x1008-1794x1704
            deferred=false layoutNeeded=false
          [...]
        """)
    assert _parse_display_dimensions(moto_x2_portrait) == \
        _Dimensions(width=1080, height=1920)

    moto_x2_landscape = dedent("""\
        [...]
        WINDOW MANAGER DISPLAY CONTENTS (dumpsys window displays)
          Display: mDisplayId=0
            init=1080x1920 480dpi cur=1920x1080 app=1794x1080 rng=1080x1008-1794x1704
            deferred=false layoutNeeded=false
          [...]
        """)
    assert _parse_display_dimensions(moto_x2_landscape) == \
        _Dimensions(width=1920, height=1080)

    samsung_galaxy_ace_2 = dedent("""\
        [...]
        WINDOW MANAGER WINDOWS (dumpsys window windows)
          Window #4 Window{43073770 RecentsPanel paused=false}:
          [...]

          Display: init=480x800 cur=480x800 app=480x800 rng=480x442-800x762
          [...]
        """)
    assert _parse_display_dimensions(samsung_galaxy_ace_2) == \
        _Dimensions(width=480, height=800)


def test_get_frame_press_tap_and_swipe(adb):  # pylint:disable=redefined-outer-name
    def match_any(basename):
        f = adb.get_frame()
        return (match("images/galaxy-ace-2/" + basename, f) or
                match("images/moto-x2/" + basename, f))

    adb.press("KEYCODE_HOME")
    m = wait_until(lambda: match_any("app-icon.png"))
    assert m
    adb.tap(m.region)
    assert wait_until(lambda: match_any("app.png"))
    adb.swipe((240, 0), (240, 600))
    assert wait_until(lambda: match_any("settings-icon.png"))


def test_adb_tcpip(adb):  # pylint:disable=redefined-outer-name

    # Expects a phone connected via USB. Set it to TCP/IP mode, test it over
    # TCP/IP, then use the TCP/IP connection to set it back to USB mode.

    if "7278681B045C937CEB770FD31542B16" in adb.devices():
        raise SkipTest("adb tcpip doesn't work with our old Galaxy Ace 2.")

    ip = _parse_ip_address(
        adb.adb(["shell", "ip", "addr"], capture_output=True))
    adb.adb(["tcpip", "5555"])
    time.sleep(5)
    try:
        adb2 = AdbDevice(
            adb_server="localhost",
            adb_device=ip,
            adb_binary=os.environ.get("ADB_BINARY", "adb"),
            tcpip=True,
            coordinate_system=CoordinateSystem.ADB_NATIVE)
        assert ip == _parse_ip_address(
            adb2.adb(["shell", "ip", "addr"], capture_output=True))
        assert "%s:5555" % ip in adb2.devices()
    finally:
        try:
            adb2.adb(["usb"])
            time.sleep(5)
        except AdbError:
            pass


@pytest.fixture(scope="function")
def adb():
    _adb = AdbDevice(
        adb_server=os.environ.get("ADB_SERVER", "localhost"),
        adb_device=os.environ.get("ANDROID_SERIAL", None),
        adb_binary=os.environ.get("ADB_BINARY", "adb"),
        tcpip=os.environ.get("ADB_TCPIP", False),
        coordinate_system=CoordinateSystem.ADB_NATIVE)
    if not any(
            serial in _adb.devices() for serial in [
                "7278681B045C937CEB770FD31542B16",  # Our CI Samsung Galaxy Ace2
                "model:XT1092",  # Moto X (2nd gen)
                os.environ.get("ANDROID_SERIAL", None),
            ] if serial is not None):
        raise SkipTest(
            "CI Android device not connected. You can set ADB_SERVER, "
            "ANDROID_SERIAL, and ADB_BINARY environment variables.")
    return _adb


def isclose(a, b, absolute_tolerance=0):
    return abs(a - b) <= absolute_tolerance


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)


def _parse_ip_address(output):
    # pylint:disable=line-too-long,trailing-whitespace
    r"""
    >>> from pprint import pprint
    >>> from textwrap import dedent
    >>> pprint(_parse_ip_address(dedent('''\
    ...     1: lo: <LOOPBACK,UP,LOWER_UP> mtu 16436 qdisc noqueue state UNKNOWN 
    ...         link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    ...         inet 127.0.0.1/8 scope host lo
    ...         inet6 ::1/128 scope host 
    ...            valid_lft forever preferred_lft forever
    ...     2: dummy0: <BROADCAST,NOARP,UP,LOWER_UP> mtu 1500 qdisc noqueue state UNKNOWN 
    ...         link/ether 46:ed:31:1b:fa:33 brd ff:ff:ff:ff:ff:ff
    ...         inet6 fe80::44ed:31ff:fe1b:fa33/64 scope link 
    ...            valid_lft forever preferred_lft forever
    ...     3: rmnet0: <> mtu 1410 qdisc noop state DOWN qlen 1000
    ...         link/[530] 
    ...     [...]
    ...     11: rmnet_usb0: <BROADCAST,MULTICAST> mtu 2000 qdisc noop state DOWN qlen 1000
    ...         link/ether 62:eb:12:3b:97:94 brd ff:ff:ff:ff:ff:ff
    ...     [...]
    ...     24: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP qlen 1000
    ...         link/ether 5c:51:88:34:aa:e2 brd ff:ff:ff:ff:ff:ff
    ...         inet 192.168.2.163/24 brd 192.168.2.255 scope global wlan0
    ...         inet6 fe80::5e51:88ff:fe34:aae2/64 scope link 
    ...            valid_lft forever preferred_lft forever
    ...     25: p2p0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc mq state DOWN qlen 1000
    ...         link/ether 5c:51:88:34:aa:e3 brd ff:ff:ff:ff:ff:ff
    ...     ''')))
    '192.168.2.163'
    """
    m = re.search(r"192\.168\.[0-9]{1,3}\.[0-9]{1,3}", output)
    assert m, "No local IP address found in: %s" % output
    return m.group()
