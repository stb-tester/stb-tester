import re
import tempfile
from textwrap import dedent

import cv2
import numpy
import pytest

from _stbt.imgutils import _image_region, load_image
from _stbt.mask import Mask, _to_array
from _stbt.types import Region


frame_region = Region(0, 0, 6, 4)


def test_mask_arithmetic():
    r1 = Region(x=0, y=0, right=2, bottom=2)
    assert repr(Mask(r1)) == "Region(x=0, y=0, right=2, bottom=2)"
    assert pretty(Mask(r1)) == dedent("""\
        xx....
        xx....
        ......
        ......
        """)
    assert Mask(r1).to_array(frame_region) == (None, r1)

    assert repr(~r1) == "~Region(x=0, y=0, right=2, bottom=2)"
    assert pretty(~r1) == dedent("""\
        ..xxxx
        ..xxxx
        xxxxxx
        xxxxxx
        """)
    assert bounding_box(~r1) == frame_region

    r2 = Region(x=4, y=2, right=6, bottom=6)
    assert repr(r1 + r2) == \
        "Region(x=0, y=0, right=2, bottom=2) + " \
        "Region(x=4, y=2, right=6, bottom=6)"
    assert pretty(r1 + r2) == dedent("""\
        xx....
        xx....
        ....xx
        ....xx
        """)
    assert bounding_box(r1 + r2) == frame_region

    assert repr(r1 - r2) == \
        "Region(x=0, y=0, right=2, bottom=2) - " \
        "Region(x=4, y=2, right=6, bottom=6)"
    assert pretty(r1 - r2) == pretty(Mask(r1))
    assert bounding_box(r1 - r2) == r1

    r3 = Region(x=1, y=1, right=3, bottom=3)
    assert repr(~r1 - r3) == \
        "~Region(x=0, y=0, right=2, bottom=2) - " \
        "Region(x=1, y=1, right=3, bottom=3)"
    assert pretty(~r1 - r3) == dedent("""\
        ..xxxx
        ...xxx
        x..xxx
        xxxxxx
        """)
    assert bounding_box(~r1 - r3) == frame_region

    assert repr(r1 + r2 + r3) == f"{r1!r} + {r2!r} + {r3!r}"
    assert repr(r1 + r2 - r3) == f"{r1!r} + {r2!r} - {r3!r}"
    assert repr(r1 + (r2 - r3)) == f"{r1!r} + ({r2!r} - {r3!r})"
    assert repr(r1 - r2 + r3) == f"{r1!r} - {r2!r} + {r3!r}"
    assert repr(r1 - r2 - r3) == f"{r1!r} - {r2!r} - {r3!r}"
    assert repr(r1 - (r2 - r3)) == f"{r1!r} - ({r2!r} - {r3!r})"
    assert repr(r1 - ~r2 + r3) == f"{r1!r} - ~{r2!r} + {r3!r}"
    assert repr(r1 - ~(r2 - r3)) == f"{r1!r} - ~({r2!r} - {r3!r})"

    assert pretty(r1 + r2 + r3) == dedent("""\
        xx....
        xxx...
        .xx.xx
        ....xx
        """)
    assert pretty(r1 + r2 - r3) == dedent("""\
        xx....
        x.....
        ....xx
        ....xx
        """)
    assert pretty(r1 + (r2 - r3)) == pretty(r1 + r2)
    assert pretty(r1 - r2 + r3) == pretty(r1 + r3)
    assert pretty(r1 - r2 - r3) == dedent("""\
        xx....
        x.....
        ......
        ......
        """)
    assert bounding_box(r1 - r2 - r3) == r1
    assert pretty(r1 - (r2 - r3)) == pretty(Mask(r1))
    assert pretty(r1 - ~r2 + r3) == pretty(Mask(r3))
    assert pretty(r1 - ~(r2 - r3)) == dedent("""\
        ......
        ......
        ......
        ......
        """)
    assert pretty(r1 - ~(r2 - r3)) == pretty(Mask(None))

    m = ~r1
    assert repr(r1) == repr(~m)
    assert pretty(Mask(r1)) == pretty(~m)

    assert repr(Mask(Region.ALL)) == "Region.ALL"
    assert repr(Mask(None)) == "~Region.ALL"

    assert repr(Region.ALL - r1) == f"Region.ALL - {r1!r}"
    assert pretty(Region.ALL - r1) == pretty(~r1)

    # `None` means an empty region, for example the result of `Region.intersect`
    # if the input regions don't overlap.
    # See also https://github.com/stb-tester/stb-tester/pull/624
    empty = Region.intersect(r1, r2)
    assert empty is None
    assert pretty(r1 + empty) == pretty(Mask(r1))
    assert pretty(empty + r1) == pretty(Mask(r1))
    assert pretty(Mask(r1) + empty) == pretty(Mask(r1))
    assert pretty(empty + Mask(r1)) == pretty(Mask(r1))
    assert pretty(r1 - empty) == pretty(Mask(r1))
    assert pretty(empty - r1) == pretty(Mask(empty))
    assert pretty(Mask(r1) - empty) == pretty(Mask(r1))
    assert pretty(empty - Mask(r1)) == pretty(Mask(empty))
    assert pretty(~Region.ALL) == pretty(Mask(empty))
    # But we still can't support `None + None`:
    with pytest.raises(TypeError, match="unsupported operand type"):
        print(empty + empty)

    with pytest.raises(TypeError, match="unsupported operand type"):
        print(r1 + 5)
    with pytest.raises(TypeError, match="unsupported operand type"):
        print(m + 5)
    with pytest.raises(TypeError, match="unsupported operand type"):
        print(5 + r1)
    with pytest.raises(TypeError, match="unsupported operand type"):
        print(5 + m)
    with pytest.raises(TypeError, match="unsupported operand type"):
        print(r1 - 5)
    with pytest.raises(TypeError, match="unsupported operand type"):
        print(m - 5)
    with pytest.raises(TypeError, match="unsupported operand type"):
        print(5 - r1)
    with pytest.raises(TypeError, match="unsupported operand type"):
        print(5 - m)


def test_mask_from_png_and_from_array():
    with tempfile.NamedTemporaryFile(prefix="test_mask", suffix=".png") as f:
        r1 = Region(x=0, y=0, right=2, bottom=2)
        r2 = Region(x=4, y=2, right=6, bottom=6)
        cv2.imwrite(f.name, _to_array(Mask(r1), frame_region))
        m1 = Mask(f.name)
        assert repr(m1) == f"Mask({f.name!r})"
        assert pretty(m1) == pretty(Mask(r1))
        assert repr(m1 + r2) == \
            f"Mask({f.name!r}) + Region(x=4, y=2, right=6, bottom=6)"
        assert pretty(m1 + r2) == pretty(r1 + r2)

        with pytest.raises(ValueError):
            # Requested frame_region doesn't match file's size
            m1.to_array(Region(0, 0, 2, 2))

        array = numpy.array([[1, 1, 0, 0, 0, 0],
                             [1, 1, 0, 0, 0, 0],
                             [0, 0, 0, 0, 1, 1],
                             [0, 0, 0, 0, 1, 1]], dtype=numpy.uint8) * 255
        m2 = Mask(array)
        assert repr(m2) == "Mask(<Image>)"
        assert pretty(m2) == pretty(r1 + r2)

        array = cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)
        m3 = Mask(array)
        assert repr(m3) == "Mask(<Image>)"
        assert pretty(m3) == pretty(r1 + r2)


def pretty(mask):
    a = _to_array(Mask(mask), frame_region)
    out = ""
    for y in range(4):
        for x in range(6):
            if a[y][x]:
                out += "x"
            else:
                out += "."
        out += "\n"
    return out


def bounding_box(mask):
    return mask.to_array(frame_region)[1]


def test_mask_comparison():
    r = Region(x=0, y=0, right=2, bottom=2)
    assert Mask(r) == Mask(r)
    assert Mask(r) == r
    assert r == Mask(r)
    assert Mask(r) == ~Mask(~r)

    assert Mask(r) != ~r
    assert Mask(r) != r.translate(1)

    assert Mask(Region.ALL) == Region.ALL
    assert Region.ALL == Mask(Region.ALL)
    assert ~Mask(Region.ALL) == Mask(None)
    assert ~Mask(Region.ALL) != None  # that'd be going too far


def test_mask_memoization():
    a1, _ = (Region(0, 0, 2, 2) + Region(2, 2, 2, 2)).to_array(frame_region)
    a2, _ = (Region(0, 0, 2, 2) + Region(2, 2, 2, 2)).to_array(frame_region)
    assert a1 is a2

    a3, _ = (Region(0, 0, 2, 2) + Region(2, 2, 2, 2)).to_array(frame_region,
                                                               color_channels=3)
    assert a3 is not a1

    a4, _ = (Region(0, 0, 2, 2) + Region(2, 2, 2, 2)).to_array(frame_region)
    assert a4 is a1

    a5, _ = Mask("mask-out-left-half-720p.png").to_array(Region(0, 0,
                                                                1280, 720))
    a6, _ = Mask("mask-out-left-half-720p.png").to_array(Region(0, 0,
                                                                1280, 720))
    assert a5 is a6

    # the mask is read-only
    with pytest.raises(ValueError):
        a1[2, 2] = 22
    assert a1[2, 2, 0] == 255


def test_mask_with_3_channels():
    m = Region(0, 0, 2, 2) + Region(2, 2, 2, 2)
    a1, _ = m.to_array(Region(0, 0, 6, 4))
    a3, _ = m.to_array(Region(0, 0, 6, 4), color_channels=3)
    assert a1.shape == (4, 4, 1)
    assert a3.shape == (4, 4, 3)
    for c in range(3):
        assert numpy.array_equal(a1[:, :, 0], a3[:, :, c])


@pytest.mark.parametrize("invert", [True, False])
@pytest.mark.parametrize("color_channels", [1, 3])
@pytest.mark.parametrize("m,frame_region", [
    # pylint:disable=bad-whitespace,line-too-long
    (Mask("mask-out-left-half-720p.png"),                 Region(0, 0, 1280, 720)),
    (Mask(load_image("mask-out-left-half-720p.png")),     Region(0, 0, 1280, 720)),
    (Mask(numpy.full((4, 6, 1), 255, dtype=numpy.uint8)), frame_region),
    (Mask(numpy.full((4, 6, 3), 255, dtype=numpy.uint8)), frame_region),
    (Mask(numpy.full((4, 6), 255, dtype=numpy.uint8)),    frame_region),
    (Mask(Region(2, 2, 2, 2)),                            frame_region),
    (Mask(Region.ALL),                                    frame_region),
    (Mask(None),                                          frame_region),
    (~Region(2, 2, 2, 2),                                 frame_region),
    (Region(0, 0, 2, 2) + Region(2, 2, 2, 2),             frame_region),
])
def test_mask_to_array_basic_check(m, frame_region, color_channels, invert):  # pylint:disable=redefined-outer-name
    # Basic check of all possible code paths (for different types of masks).
    # We aren't checking the output pixels but at least it shouldn't raise.
    if invert:
        m = ~m
    try:
        array, _ = m.to_array(frame_region, color_channels)
        if array is not None:
            assert array.shape[2] == color_channels
    except ValueError as e:
        assert re.match(r".* doesn't overlap with the frame's Region", str(e))


@pytest.mark.parametrize("m,frame_region,expect_array,expected_region", [
    # pylint:disable=bad-whitespace,line-too-long
    (Mask("mask-out-left-half-720p.png"),                 Region(0, 0, 1280, 720), False, Region(640, 0, right=1280, bottom=720)),
    (Mask(load_image("mask-out-left-half-720p.png")),     Region(0, 0, 1280, 720), False, Region(640, 0, right=1280, bottom=720)),
    (~Mask("mask-out-left-half-720p.png"),                Region(0, 0, 1280, 720), False, Region(0, 0, 640, 720)),
    (~Mask(load_image("mask-out-left-half-720p.png")),    Region(0, 0, 1280, 720), False, Region(0, 0, 640, 720)),
    (Mask("videotestsrc-mask-non-black.png"),             Region(0, 0, 320, 240),  True,  Region(46, 160, right=274, bottom=240)),
    (Mask(load_image("videotestsrc-mask-non-black.png")), Region(0, 0, 320, 240),  True,  Region(46, 160, right=274, bottom=240)),
    (~Mask("videotestsrc-mask-non-black.png"),            Region(0, 0, 320, 240),  True,  Region(0, 0, 320, 240)),
    (~Mask(load_image("videotestsrc-mask-non-black.png")), Region(0, 0, 320, 240), True,  Region(0, 0, 320, 240)),
    (Mask("black-full-frame.png"),                        Region(0, 0, 320, 240),  False, None),
    (Mask(load_image("black-full-frame.png")),            Region(0, 0, 320, 240),  False, None),
    (~Mask("black-full-frame.png"),                       Region(0, 0, 320, 240),  False, Region(0, 0, 320, 240)),
    (~Mask(load_image("black-full-frame.png")),           Region(0, 0, 320, 240),  False, Region(0, 0, 320, 240)),
    (Mask(numpy.full((4, 6, 1), 255, dtype=numpy.uint8)), frame_region,            False, frame_region),
    (Mask(numpy.full((4, 6, 3), 255, dtype=numpy.uint8)), frame_region,            False, frame_region),
    (Mask(numpy.full((4, 6), 255, dtype=numpy.uint8)),    frame_region,            False, frame_region),
    (~Mask(numpy.full((4, 6, 1), 255, dtype=numpy.uint8)), frame_region,           False, None),
    (~Mask(numpy.full((4, 6, 3), 255, dtype=numpy.uint8)), frame_region,           False, None),
    (~Mask(numpy.full((4, 6), 255, dtype=numpy.uint8)),   frame_region,            False, None),
    (Mask(numpy.zeros((4, 6, 1), dtype=numpy.uint8)),     frame_region,            False, None),
    (Mask(numpy.zeros((4, 6, 3), dtype=numpy.uint8)),     frame_region,            False, None),
    (Mask(numpy.zeros((4, 6), dtype=numpy.uint8)),        frame_region,            False, None),
    (~Mask(numpy.zeros((4, 6, 1), dtype=numpy.uint8)),    frame_region,            False, frame_region),
    (~Mask(numpy.zeros((4, 6, 3), dtype=numpy.uint8)),    frame_region,            False, frame_region),
    (~Mask(numpy.zeros((4, 6), dtype=numpy.uint8)),       frame_region,            False, frame_region),
    (Mask(Region(2, 2, 2, 2)),                            frame_region,            False, Region(2, 2, 2, 2)),
    (Mask(Region(2, 2, 20, 20)),                          frame_region,            False, Region(2, 2, right=frame_region.right, bottom=frame_region.bottom)),
    (Mask(Region.ALL),                                    frame_region,            False, frame_region),
    (Mask(None),                                          frame_region,            False, None),
    (~Region(2, 2, 2, 2),                                 frame_region,            True,  frame_region),
    (Region(0, 0, 2, 2) + Region(2, 2, 2, 2),             frame_region,            True,  Region(0, 0, 4, 4)),
    (Region(0, 0, 1, 1) + Region(3, 3, 1, 1),             frame_region,            True,  Region(0, 0, 4, 4)),
])
def test_mask_to_array(m, frame_region, expect_array, expected_region):  # pylint:disable=redefined-outer-name
    if expected_region is None:
        with pytest.raises(ValueError,
                           match=r".* doesn't overlap with the frame's Region"):
            m.to_array(frame_region)

    else:
        array, bounding_box = m.to_array(frame_region)  # pylint:disable=redefined-outer-name
        if expect_array:
            assert array is not None
            assert array.shape == (expected_region.height,
                                   expected_region.width, 1)
        else:
            assert array is None
        assert bounding_box == expected_region


def test_mask_shape_mismatch():
    with pytest.raises(ValueError,
                       match=(r"Mask\(.*\): shape \(720, 1280, 1\) doesn't "
                              r"match required shape \(1280, 720, 1\)")):
        Mask("mask-out-left-half-720p.png").to_array(Region(0, 0, 720, 1280))


def test_1080p_mask():
    frame = load_image("images/1080p/appletv.png")
    assert _image_region(frame) == Region(x=0, y=0, right=1920, bottom=1080)

    alpha = Mask(load_image("images/1080p/appletv_background.png")[:, :, 3])

    # Old coordinates from 720p test script don't intersect mask from 1080p
    # image:
    mask = Region(x=26, y=500, right=1244, bottom=674)
    mask = mask - ~alpha  # mask & alpha
    with pytest.raises(ValueError, match=(
            r"Region\(.*\) - ~Mask\(.*\) doesn't overlap with the frame's "
            r"Region\(x=0, y=0, right=1920, bottom=1080\)")):
        mask.to_array(_image_region(frame))

    # Coordinates updated for 1080p image:
    mask = Region(x=39, y=750, right=1866, bottom=1011)
    mask = mask - ~alpha  # mask & alpha
    mask_pixels, mask_region = mask.to_array(_image_region(frame))
    assert mask_region == Region(x=49, y=750, right=1866, bottom=1011)
    assert mask_pixels.shape == (261, 1817, 1)


def test_mask_from_alpha_channel():
    # Image without alpha channel
    assert Mask.from_alpha_channel("videotestsrc-full-frame.png") == \
        Region(0, 0, 320, 240)

    # Image with alpha channel
    alpha = Mask.from_alpha_channel("videotestsrc-blacktransparent-blue.png")
    _, mask_region = alpha.to_array(Region(0, 0, 138, 160))
    assert mask_region == Region(0, 0, 138, 160)
    _, mask_region = (~alpha).to_array(Region(0, 0, 138, 160))
    assert mask_region == Region(46, 0, right=92, bottom=160)
