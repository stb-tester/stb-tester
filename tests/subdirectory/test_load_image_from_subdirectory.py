from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import (ascii, chr, filter, hex, input, map, next, oct, open, pow,  # pylint:disable=redefined-builtin,unused-import,wildcard-import,wrong-import-order
                      range, round, super, zip)
import os

import cv2
import numpy
import pytest

import stbt


def test_that_load_image_looks_in_callers_directory():
    # See also the test with the same name in ../test_core.py
    assert numpy.array_equal(
        stbt.load_image("videotestsrc-redblue.png"),
        cv2.imread(os.path.join(os.path.dirname(__file__),
                                "../videotestsrc-redblue-flipped.png")))

    with pytest.raises(IOError):
        stbt.load_image("info.png")
