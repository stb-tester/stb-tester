import numpy

import stbt


def black(width=1280, height=720):
    return numpy.zeros((height, width, 3), dtype=numpy.uint8)


def test_that_matchresult_image_matches_template_passed_to_match():
    assert stbt.match("black.png", frame=black()).image == "black.png"


def test_that_matchresult_str_image_matches_template_passed_to_match():
    assert "image=\'black.png\'" in str(stbt.match("black.png", frame=black()))


def test_that_matchresult_str_image_matches_template_passed_to_match_custom():
    assert "image=<Custom Image>" in str(
        stbt.match(black(30, 30), frame=black()))
