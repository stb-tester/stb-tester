import tempfile
from textwrap import dedent

import cv2
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
    assert repr(Mask(r1)) == repr(~m)
    assert pretty(Mask(r1)) == pretty(~m)

    assert repr(Region.ALL - r1) == f"Region.ALL - {r1!r}"
    assert pretty(Region.ALL - r1) == pretty(~r1)

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
