import cv2
import numpy
from nose.tools import raises

import stbt
from _stbt.core import _load_template


def black(width=1280, height=720):
    return numpy.zeros((height, width, 3), dtype=numpy.uint8)


def test_that_matchresult_image_matches_template_passed_to_match():
    assert stbt.match("black.png", frame=black()).image == "black.png"


def test_that_matchresult_str_image_matches_template_passed_to_match():
    assert "image=\'black.png\'" in str(stbt.match("black.png", frame=black()))


def test_that_matchresult_str_image_matches_template_passed_to_match_custom():
    assert "image=<Custom Image>" in str(
        stbt.match(black(30, 30), frame=black()))


def test_matchresult_region_when_first_pyramid_level_fails_to_match():
    f = _imread("videotestsrc-full-frame.png")
    assert stbt.Region(184, 0, width=92, height=160) == stbt.match(
        "videotestsrc-redblue-flipped.png", frame=f).region


@raises(ValueError)
def test_that_match_rejects_greyscale_template():
    grey = cv2.cvtColor(_load_template("black.png").image, cv2.cv.CV_BGR2GRAY)
    stbt.match(grey, frame=black())
