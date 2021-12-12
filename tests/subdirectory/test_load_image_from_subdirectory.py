import os

import cv2
import numpy
import pytest

import stbt_core as stbt


def test_that_load_image_looks_in_callers_directory(test_pack_root):  # pylint:disable=unused-argument
    # See also the test with the same name in ../test_core.py

    f = stbt.load_image("videotestsrc-redblue.png")
    assert numpy.array_equal(
        f,
        cv2.imread(os.path.join(os.path.dirname(__file__),
                                "../videotestsrc-redblue-flipped.png")))
    assert f.filename == "videotestsrc-redblue.png"
    assert f.relative_filename == "subdirectory/videotestsrc-redblue.png"

    with pytest.raises(IOError):
        stbt.load_image("info.png")
