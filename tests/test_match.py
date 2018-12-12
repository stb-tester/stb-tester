import cv2
import numpy
import pytest

import stbt
from stbt import MatchParameters as mp


def black(width=1280, height=720, value=0):
    return numpy.ones((height, width, 3), dtype=numpy.uint8) * value


def test_that_matchresult_image_matches_template_passed_to_match():
    assert stbt.match("black.png", frame=black()).image == "black.png"


def test_that_matchresult_str_image_matches_template_passed_to_match():
    assert "image=\'black.png\'" in str(stbt.match("black.png", frame=black()))


def test_that_matchresult_str_image_matches_template_passed_to_match_custom():
    assert "image=<Custom Image>" in str(
        stbt.match(black(30, 30), frame=black()))


def test_matchresult_region_when_first_pyramid_level_fails_to_match():
    f = stbt.load_image("videotestsrc-full-frame.png")
    assert stbt.Region(184, 0, width=92, height=160) == stbt.match(
        "videotestsrc-redblue-flipped.png", frame=f).region


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_that_match_rejects_greyscale_template(match_method):
    grey = cv2.cvtColor(stbt.load_image("black.png"), cv2.COLOR_BGR2GRAY)
    with pytest.raises(ValueError):
        stbt.match(grey, frame=black(),
                   match_parameters=mp(match_method=match_method))


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_matching_greyscale_template(match_method):
    assert stbt.match(
        cv2.cvtColor(stbt.load_image("videotestsrc-redblue.png"),
                     cv2.COLOR_BGR2GRAY),
        frame=cv2.cvtColor(stbt.load_image("videotestsrc-full-frame.png"),
                           cv2.COLOR_BGR2GRAY),
        match_parameters=mp(match_method=match_method))


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_that_if_image_doesnt_match_match_all_returns_empty_array(match_method):
    assert [] == list(stbt.match_all(
        'button.png', frame=stbt.load_image('black-full-frame.png'),
        match_parameters=mp(match_method=match_method)))


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
    stbt.MatchMethod.CCORR_NORMED,
    stbt.MatchMethod.CCOEFF_NORMED,
])
def test_that_match_all_finds_all_matches(match_method):
    plain_buttons = [stbt.Region(x, y, width=135, height=44) for x, y in [
        (28, 1), (163, 1), (177, 75), (177, 119), (177, 163), (298, 1)]]

    matches = list(m.region for m in stbt.match_all(
        'button.png', frame=stbt.load_image('buttons.png'),
        match_parameters=mp(match_method=match_method)))
    print matches
    assert plain_buttons == sorted(matches)


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_that_match_all_can_find_labelled_matches(match_method):
    plain_buttons = [stbt.Region(x, y, width=135, height=44) for x, y in [
        (28, 1), (163, 1), (177, 75), (177, 119), (177, 163), (298, 1)]]
    labelled_buttons = [stbt.Region(x, y, width=135, height=44) for x, y in [
        (1, 65), (6, 137), (123, 223)]]
    overlapped_button = stbt.Region(3, 223, width=135, height=44)

    frame = stbt.load_image('buttons.png')

    matches = list(m.region for m in stbt.match_all(
        'button.png', frame=frame,
        match_parameters=mp(match_method=match_method,
                            confirm_method=stbt.ConfirmMethod.NONE)))
    print matches
    assert overlapped_button not in matches
    assert sorted(plain_buttons + labelled_buttons) == sorted(matches)


def test_that_match_all_can_be_used_with_ocr_to_read_buttons():
    # Demonstrates how match_all can be used with ocr for UIs consisting of text
    # on buttons
    frame = stbt.load_image('buttons.png')
    button = stbt.load_image('button.png')

    text = [
        stbt.ocr(frame=cv2.absdiff(stbt.crop(frame, m.region), button))
        for m in stbt.match_all(
            button, frame=frame, match_parameters=mp(confirm_method='none'))]
    text = sorted([t for t in text if t not in ['', '\\s']])
    print text
    assert text == [u'Button 1', u'Button 2', u'Buttons']


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_that_results_dont_overlap(match_method):
    # This is a regression test for a bug seen in an earlier implementation of
    # `match_all`.
    frame = stbt.load_image("action-panel.png")
    all_matches = set()
    for m in stbt.match_all("action-panel-template.png", frame=frame,
                            match_parameters=mp(match_method=match_method)):
        print m
        assert m.region not in all_matches, "Match %s already seen:\n    %s" % (
            m, "\n    ".join(str(x) for x in all_matches))
        assert all(stbt.Region.intersect(m.region, x) is None
                   for x in all_matches)
        all_matches.add(m.region)

    assert all_matches == set([
        stbt.Region(x=135, y=433, width=222, height=40),
        stbt.Region(x=135, y=477, width=222, height=40),
        stbt.Region(x=135, y=521, width=222, height=40),
        stbt.Region(x=135, y=565, width=222, height=40),
        stbt.Region(x=135, y=609, width=222, height=40)])


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_that_match_all_obeys_region(match_method):
    matches = sorted(m.region for m in stbt.match_all(
        "button.png", frame=stbt.load_image("buttons.png"),
        match_parameters=mp(match_method=match_method),
        region=stbt.Region(x=160, y=60, right=340, bottom=190)))
    print matches
    assert matches == [stbt.Region(x, y, width=135, height=44) for x, y in [
        (177, 75), (177, 119)]]


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_match_all_with_an_image_that_matches_everywhere(match_method):
    matches = sorted(m.region for m in stbt.match_all(
        "repeating-pattern.png",
        frame=stbt.load_image("repeating-pattern-full-frame.png"),
        match_parameters=mp(match_method=match_method)))

    expected_matches = sorted([stbt.Region(x, y, width=16, height=16)
                               for x in range(0, 320, 16)
                               for y in range(0, 240, 16)])

    print matches
    assert matches == expected_matches


def test_that_sqdiff_matches_black_images():
    black_reference = black(10, 10)
    almost_black_reference = black(10, 10, value=1)
    black_frame = black(1280, 720)
    almost_black_frame = black(1280, 720, value=2)

    sqdiff = mp(match_method=stbt.MatchMethod.SQDIFF)
    sqdiff_normed = mp(match_method=stbt.MatchMethod.SQDIFF_NORMED)

    assert not stbt.match(black_reference, black_frame, sqdiff_normed)
    assert not stbt.match(almost_black_reference, black_frame, sqdiff_normed)
    assert not stbt.match(almost_black_reference, almost_black_frame,
                          sqdiff_normed)
    assert stbt.match(black_reference, black_frame, sqdiff)
    assert stbt.match(almost_black_reference, black_frame, sqdiff)
    assert stbt.match(almost_black_reference, almost_black_frame, sqdiff)
