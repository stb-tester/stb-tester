import os

import cv2
import numpy
import pytest

import stbt_core as stbt


def test_that_load_image_looks_in_callers_directory():
    # See also the test with the same name in ../test_core.py

    stbt.TEST_PACK_ROOT = os.path.abspath(os.path.join(
        os.path.dirname(__file__), ".."))

    f = stbt.load_image("videotestsrc-redblue.png")
    assert numpy.array_equal(
        f,
        cv2.imread(os.path.join(os.path.dirname(__file__),
                                "../videotestsrc-redblue-flipped.png")))
    assert f.filename == "videotestsrc-redblue.png"
    assert f.relative_filename == "subdirectory/videotestsrc-redblue.png"

    with pytest.raises(IOError):
        stbt.load_image("info.png")
