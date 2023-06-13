import numpy

import stbt_core as stbt
from _stbt import diff, libstbt
from _stbt.imgutils import crop
from _stbt.motion import DetectMotion

# Note: BGRDiff is also tested by `test_press_and_wait*`.


def test_bgrdiff():
    frame1 = stbt.load_image("images/diff/xfinity-search-keyboard-1.png")
    frame2 = stbt.load_image("images/diff/xfinity-search-keyboard-2.png")

    # GrayscaleDiff doesn't see the difference in the "?123"
    assert not DetectMotion(stbt.GrayscaleDiff(), frame1).diff(frame2)

    # BGRDiff does see it:
    result = DetectMotion(stbt.BGRDiff(), frame1).diff(frame2)
    assert result
    assert result.region == stbt.Region(x=87, y=145, right=129, bottom=161)


def test_bgrdiff_c_equivalence():
    f = numpy.random.random_integers(0, 255, (720, 1280, 3)).astype(numpy.uint8)

    def bgrdiff(f1, f2, threshold):
        n = diff._threshold_diff_bgr_numpy(f1, f2, threshold)
        c = libstbt.threshold_diff_bgr(f1, f2, threshold)
        assert numpy.all(n == c)
        return c

    assert_np_eq(bgrdiff(f, f, 0), numpy.ones((720, 1280), dtype=numpy.uint8))
    assert_np_eq(bgrdiff(f, f, 1), numpy.zeros((720, 1280), dtype=numpy.uint8))

    f1 = f.copy()
    f1[30:40, 70:80, 0] = 35
    f1[30:40, 70:80, 1] = 45
    f1[30:40, 70:80, 2] = 55

    f2 = f1.copy()
    f2[30:40, 70:80, 0] = 32  # 3^2 ==  9
    f2[30:40, 70:80, 1] = 50  # 5^2 == 25
    f2[30:40, 70:80, 2] = 56  # 1^2 ==  1
    #                    total diff == 35

    expected = numpy.zeros((720, 1280), dtype=numpy.uint8)
    expected[30:40, 70:80] = 1
    assert_np_eq(bgrdiff(f1, f2, 35), expected)
    assert_np_eq(bgrdiff(f, f, 35), numpy.zeros((720, 1280), dtype=numpy.uint8))

    # And with cropping
    r = stbt.Region(65, 25, 10, 10)

    # Get the stride, etc. of f2 to be different to f1:
    f2 = crop(f2, r.dilate(1)).copy()
    f2 = f2[1:-1, 1:-1, :]

    expected = numpy.zeros((10, 10), dtype=numpy.uint8)
    expected[5:10, 5:10] = 1
    assert_np_eq(bgrdiff(crop(f1, r), f2, 35), expected)


def assert_np_eq(a, b):
    assert a.dtype == b.dtype
    assert a.shape == b.shape
    assert numpy.all(a == b)
