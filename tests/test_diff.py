import stbt_core as stbt

# Note: BGRDiff is also tested by `test_press_and_wait*`.


def test_bgrdiff():
    frame1 = stbt.load_image("images/diff/xfinity-search-keyboard-1.png")
    frame2 = stbt.load_image("images/diff/xfinity-search-keyboard-2.png")

    # GrayscaleDiff doesn't see the difference in the "?123"
    assert not stbt.GrayscaleDiff(frame1).diff(frame2)

    # BGRDiff does see it:
    result = stbt.BGRDiff(frame1).diff(frame2)
    assert result
    assert result.region == stbt.Region(x=87, y=145, right=129, bottom=161)
