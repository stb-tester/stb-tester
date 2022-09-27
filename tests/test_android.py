import os
from textwrap import dedent

import cv2
import pytest
from numpy import isclose

from stbt_core import match, Region
from _stbt.android import (_centre_point, _Dimensions,
                           _parse_display_dimensions, _resize,
                           _to_native_coordinates, AdbDevice, CoordinateSystem)


@pytest.mark.parametrize("r", [
    Region(10, 10, width=30, height=5),
    (25, 12),
    ("25", "12"),
])
def test_centre_point(r):
    assert _centre_point(r) == (25, 12)


@pytest.mark.parametrize("r", [
    25,
    (25,),
    (25, 12, 15),
    "25",
])
def test_centre_point_raises(r):
    with pytest.raises(TypeError):
        _centre_point(r)


@pytest.mark.parametrize("orientation", [
    "portrait",
    "landscape",
])
@pytest.mark.parametrize("coordinate_system", [
    CoordinateSystem.ADB_NATIVE,
    CoordinateSystem.ADB_720P,
    CoordinateSystem.HDMI_720P,
    CoordinateSystem.CAMERA_720P,
])
def test_that_get_frame_resizes_to_match_coordinate_system(
        orientation, coordinate_system):

    source = cv2.imread(_find_file(
        "images/android/resize/source-1080p-%s.png" % orientation))
    out = _resize(source, coordinate_system)
    expected_filename = \
        "images/android/resize/expected-{system}-{orientation}.png".format(
            system=coordinate_system.name.lower().replace("_", "-"),
            orientation=orientation)
    expected = cv2.imread(_find_file(expected_filename))
    assert match(expected, out)


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
        "images/android/coordinates/%s-screenshot.png" % description))
    icon = "images/android/coordinates/%s-reference.png" % description

    m = match(icon, screenshot)
    screenshot_x, screenshot_y = _centre_point(m.region)
    native_x, native_y = _to_native_coordinates(
        screenshot_x, screenshot_y, coordinate_system,
        _Dimensions(*device_resolution))
    print((native_x, native_y))
    assert isclose(native_x, expected_coordinates[0], atol=1)
    assert isclose(native_y, expected_coordinates[1], atol=1)


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


# This is a regression test.
def test_adbdevice_default_constructor():
    adb = AdbDevice()
    assert adb.coordinate_system == CoordinateSystem.HDMI_720P


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)
