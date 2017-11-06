import os

import numpy
import pytest

import _stbt.opencv_shim as cv2
import stbt


def test_that_load_image_looks_in_callers_directory():
    # See also the test with the same name in ../test_core.py
    assert numpy.array_equal(
        stbt.load_image("videotestsrc-redblue.png"),
        cv2.imread(os.path.join(os.path.dirname(__file__),
                                "../videotestsrc-redblue-flipped.png")))

    with pytest.raises(IOError):
        stbt.load_image("info.png")
