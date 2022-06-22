import tempfile
from textwrap import dedent

import cv2
import numpy
import pytest

from _stbt.mask import Mask
from _stbt.types import Region


def test_mask_arithmetic():
    r1 = Region(x=0, y=0, right=2, bottom=2)
    assert repr(Mask(r1)) == "Region(x=0, y=0, right=2, bottom=2)"
    assert repr(~r1) == "~Region(x=0, y=0, right=2, bottom=2)"
    assert pretty(Mask(r1)) == dedent("""\
        xx....
        xx....
        ......
        ......
        """)
    assert pretty(~r1) == dedent("""\
        ..xxxx
        ..xxxx
        xxxxxx
        xxxxxx
        """)
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

    assert repr(r1 - r2) == \
        "Region(x=0, y=0, right=2, bottom=2) - " \
        "Region(x=4, y=2, right=6, bottom=6)"
    assert pretty(r1 - r2) == pretty(Mask(r1))

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
        cv2.imwrite(f.name, Mask(r1).to_array(shape=(4, 6, 1)))
        m1 = Mask(f.name)
        assert repr(m1) == f"Mask({f.name!r})"
        assert pretty(m1) == pretty(Mask(r1))
        assert repr(m1 + r2) == \
            f"Mask({f.name!r}) + Region(x=4, y=2, right=6, bottom=6)"
        assert pretty(m1 + r2) == pretty(r1 + r2)

        m1.to_array(shape=(4, 6, 3))
        with pytest.raises(ValueError):
            m1.to_array(shape=(2, 2, 1))


def pretty(mask):
    a = mask.to_array(shape=(4, 6, 1))
    out = ""
    for y in range(4):
        for x in range(6):
            if a[y][x]:
                out += "x"
            else:
                out += "."
        out += "\n"
    return out


def test_mask_memoization():
    r = Region(x=0, y=0, right=2, bottom=2)
    a1 = Mask(r).to_array(shape=(4, 6, 1))
    a2 = Mask(r).to_array(shape=(4, 6, 1))
    assert a1 is a2

    a3 = Mask(r).to_array(shape=(4, 6, 3))
    assert a3 is not a1

    a4 = Mask(r).to_array(shape=(4, 6, 1))
    assert a4 is a1

    a5 = Mask("mask-out-left-half-720p.png").to_array((720, 1280, 1))
    a6 = Mask("mask-out-left-half-720p.png").to_array((720, 1280, 1))
    assert a5 is a6

    # the mask is read-only
    with pytest.raises(ValueError):
        a1[2, 2] = 22
    assert a1[2, 2, 0] == 0


def test_mask_with_3_channels():
    m = Mask(Region(x=0, y=0, right=2, bottom=2))
    a1 = m.to_array(shape=(4, 6, 1))
    a3 = m.to_array(shape=(4, 6, 3))
    for c in range(3):
        assert numpy.array_equal(a1[:, :, 0], a3[:, :, c])


def test_mask_to_array_with_2ary_shape():
    m1 = Mask(Region(x=0, y=0, right=2, bottom=2))
    assert m1.to_array(shape=(4, 6)).shape == (4, 6, 1)

    m2 = Mask("mask-out-left-half-720p.png")
    assert m2.to_array(shape=(720, 1280)).shape == (720, 1280, 1)


def test_mask_shape_mismatch():
    with pytest.raises(ValueError,
                       match=(r"Mask shape \(720, 1280, 1\) and required shape "
                              r"\(1280, 720, 1\) don't match")):
        Mask("mask-out-left-half-720p.png").to_array((1280, 720, 1))
