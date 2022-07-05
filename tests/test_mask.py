import tempfile
from textwrap import dedent

import cv2
import numpy
import pytest

from _stbt.imgutils import load_image
from _stbt.mask import Mask
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
    assert Mask(r1).bounding_box(frame_region) == r1

    assert repr(~r1) == "~Region(x=0, y=0, right=2, bottom=2)"
    assert pretty(~r1) == dedent("""\
        ..xxxx
        ..xxxx
        xxxxxx
        xxxxxx
        """)
    assert (~r1).bounding_box(frame_region) == frame_region

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
    assert (r1 + r2).bounding_box(frame_region) == frame_region

    assert repr(r1 - r2) == \
        "Region(x=0, y=0, right=2, bottom=2) - " \
        "Region(x=4, y=2, right=6, bottom=6)"
    assert pretty(r1 - r2) == pretty(Mask(r1))
    assert (r1 - r2).bounding_box(frame_region) == r1

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
    assert (~r1 - r3).bounding_box(frame_region) == frame_region

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
    assert (r1 - r2 - r3).bounding_box(frame_region) == r1
    assert pretty(r1 - (r2 - r3)) == pretty(Mask(r1))
    assert pretty(r1 - ~r2 + r3) == pretty(Mask(r3))
    assert pretty(r1 - ~(r2 - r3)) == dedent("""\
        ......
        ......
        ......
        ......
        """)
    assert pretty(r1 - ~(r2 - r3)) == pretty(Mask(None))
    assert (r1 - ~(r2 - r3)).bounding_box(frame_region) is None

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

    with tempfile.NamedTemporaryFile(prefix="test_mask", suffix=".png") as f:
        cv2.imwrite(f.name, Mask(r1).to_array(frame_region))
        m1 = Mask(f.name)
        assert repr(m1) == f"Mask({f.name!r})"
        assert pretty(m1) == pretty(Mask(r1))
        assert repr(m1 + r2) == \
            f"Mask({f.name!r}) + Region(x=4, y=2, right=6, bottom=6)"
        assert pretty(m1 + r2) == pretty(r1 + r2)

        with pytest.raises(ValueError):
            m1.to_array(Region(0, 0, 2, 2))

        array = m1.to_array(frame_region, color_channels=3)
        m2 = Mask(array)
        assert repr(m2) == "Mask(<Image>)"
        assert pretty(m2) == pretty(m1)


def pretty(mask):
    a = Mask(mask).to_array(frame_region)
    out = ""
    for y in range(4):
        for x in range(6):
            if a[y][x]:
                out += "x"
            else:
                out += "."
        out += "\n"
    return out


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
    r = Region(x=0, y=0, right=2, bottom=2)
    a1 = Mask(r).to_array(Region(0, 0, 6, 4))
    a2 = Mask(r).to_array(Region(0, 0, 6, 4))
    assert a1 is a2

    a3 = Mask(r).to_array(Region(0, 0, 6, 4), color_channels=3)
    assert a3 is not a1

    a4 = Mask(r).to_array(Region(0, 0, 6, 4))
    assert a4 is a1

    a5 = Mask("mask-out-left-half-720p.png").to_array(Region(0, 0, 1280, 720))
    a6 = Mask("mask-out-left-half-720p.png").to_array(Region(0, 0, 1280, 720))
    assert a5 is a6

    # the mask is read-only
    with pytest.raises(ValueError):
        a1[2, 2] = 22
    assert a1[2, 2, 0] == 0


def test_mask_with_3_channels():
    m = Mask(Region(x=0, y=0, right=2, bottom=2))
    a1 = m.to_array(Region(0, 0, 6, 4))
    a3 = m.to_array(Region(0, 0, 6, 4), color_channels=3)
    assert a1.shape == (4, 6, 1)
    assert a3.shape == (4, 6, 3)
    for c in range(3):
        assert numpy.array_equal(a1[:, :, 0], a3[:, :, c])


@pytest.mark.parametrize("invert", [True, False])
@pytest.mark.parametrize("color_channels", [1, 3])
@pytest.mark.parametrize("m,region", [
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
def test_mask_to_array(m, region, color_channels, invert):
    # Basic check of all possible code paths (for different types of masks).
    # We aren't checking the output pixels but at least it shouldn't raise.
    if invert:
        array = (~m).to_array(region, color_channels)
    else:
        array = m.to_array(region, color_channels)
    expected = (region.height, region.width, color_channels)
    assert array.shape == expected


@pytest.mark.parametrize("m,frame_region,expected_region", [
    # pylint:disable=bad-whitespace,line-too-long
    (Mask("mask-out-left-half-720p.png"),                 Region(0, 0, 1280, 720), Region(640, 0, right=1280, bottom=720)),
    (Mask(load_image("mask-out-left-half-720p.png")),     Region(0, 0, 1280, 720), Region(640, 0, right=1280, bottom=720)),
    (~Mask("mask-out-left-half-720p.png"),                Region(0, 0, 1280, 720), Region(0, 0, 640, 720)),
    (~Mask(load_image("mask-out-left-half-720p.png")),    Region(0, 0, 1280, 720), Region(0, 0, 640, 720)),
    (Mask(numpy.full((4, 6, 1), 255, dtype=numpy.uint8)), frame_region,            frame_region),
    (Mask(numpy.full((4, 6, 3), 255, dtype=numpy.uint8)), frame_region,            frame_region),
    (Mask(numpy.full((4, 6), 255, dtype=numpy.uint8)),    frame_region,            frame_region),
    (Mask(Region(2, 2, 2, 2)),                            frame_region,            Region(2, 2, 2, 2)),
    (Mask(Region(2, 2, 20, 20)),                          frame_region,            Region(2, 2, right=frame_region.right, bottom=frame_region.bottom)),
    (Mask(Region.ALL),                                    frame_region,            frame_region),
    (Mask(None),                                          frame_region,            None),
    (~Region(2, 2, 2, 2),                                 frame_region,            frame_region),
    (Region(0, 0, 2, 2) + Region(2, 2, 2, 2),             frame_region,            Region(0, 0, 4, 4)),
])
def test_mask_bounding_box(m, frame_region, expected_region):  # pylint:disable=redefined-outer-name
    assert m.bounding_box(frame_region) == expected_region


def test_mask_shape_mismatch():
    with pytest.raises(ValueError,
                       match=(r"Mask\(.*\): shape \(720, 1280, 1\) doesn't "
                              r"match required shape \(1280, 720, 1\)")):
        Mask("mask-out-left-half-720p.png").to_array(Region(0, 0, 720, 1280))
