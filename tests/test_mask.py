from _stbt.mask import Mask
from _stbt.types import Region


def test_mask_repr():
    r1 = Region(x=0, y=0, right=2, bottom=2)
    assert repr(Mask(r1)) == "Region(x=0, y=0, right=2, bottom=2)"
    assert repr(~r1) == "~Region(x=0, y=0, right=2, bottom=2)"

    r2 = Region(x=4, y=4, right=6, bottom=6)
    assert repr(r1 + r2) == \
        "Region(x=0, y=0, right=2, bottom=2) + " \
        "Region(x=4, y=4, right=6, bottom=6)"

    r3 = Region(x=1, y=1, right=3, bottom=3)
    assert repr(~r1 - r3) == \
        "~Region(x=0, y=0, right=2, bottom=2) - " \
        "Region(x=1, y=1, right=3, bottom=3)"

    assert repr(r1 + r2 + r3) == f"{r1!r} + {r2!r} + {r3!r}"
    assert repr(r1 + r2 - r3) == f"{r1!r} + {r2!r} - {r3!r}"
    assert repr(r1 + (r2 - r3)) == f"{r1!r} + ({r2!r} - {r3!r})"
    assert repr(r1 - r2 + r3) == f"{r1!r} - {r2!r} + {r3!r}"
    assert repr(r1 - (r2 - r3)) == f"{r1!r} - ({r2!r} - {r3!r})"
    assert repr(r1 - ~r2 + r3) == f"{r1!r} - ~{r2!r} + {r3!r}"
    assert repr(r1 - ~(r2 - r3)) == f"{r1!r} - ~({r2!r} - {r3!r})"

    m = ~r1
    assert repr(r1) == repr(~m)
