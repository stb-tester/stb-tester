# This file doesn't contain any runnable tests, but it is linted by
# `make check-pyright` to catch any type warnings.

import stbt_core as stbt

# pylint:disable=line-too-long


def f():
    lines = [
        stbt.Region(255, 390, right=1280, height=45),
        stbt.Region(255, 443, right=1280, height=45),
    ]
    all_lines = stbt.Region.bounding_box(*lines)
    print(all_lines.width)  # "width" is not a known attribute of "None" (reportOptionalMemberAccess)

    r: stbt.Region|None = stbt.Region.bounding_box(None, *lines)
    print(r)

    r2: None = stbt.Region.bounding_box()
    print(r2)
