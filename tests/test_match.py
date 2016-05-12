import os
import sys
from contextlib import contextmanager
from glob import glob

import cv2
import numpy
from nose.tools import raises

import stbt
from _stbt.core import _crop, _load_template
from _stbt.utils import scoped_curdir
from stbt import MatchParameters as mp

TESTS_DIR = os.path.dirname(__file__)


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


def test_that_if_image_doesnt_match_match_all_returns_empty_array():
    assert [] == list(stbt.match_all(
        'button.png', frame=_imread('black-full-frame.png')))


def test_that_match_all_finds_all_matches():
    plain_buttons = [stbt.Region(x, y, width=135, height=44) for x, y in [
        (28, 1), (163, 1), (177, 75), (177, 119), (177, 163), (298, 1)]]

    matches = list(m.region for m in stbt.match_all(
        'button.png', frame=_imread('buttons.png')))
    print matches
    assert plain_buttons == sorted(matches)


def test_that_match_all_can_find_labelled_matches():
    plain_buttons = [stbt.Region(x, y, width=135, height=44) for x, y in [
        (28, 1), (163, 1), (177, 75), (177, 119), (177, 163), (298, 1)]]
    labelled_buttons = [stbt.Region(x, y, width=135, height=44) for x, y in [
        (1, 65), (6, 137), (123, 223)]]
    overlapped_button = stbt.Region(3, 223, width=135, height=44)

    frame = _imread('buttons.png')

    matches = list(m.region for m in stbt.match_all(
        'button.png', frame=frame, match_parameters=mp(confirm_method='none')))
    print matches
    assert overlapped_button not in matches
    assert sorted(plain_buttons + labelled_buttons) == sorted(matches)


def test_that_match_all_can_be_used_with_ocr_to_read_buttons():
    # Demonstrates how match_all can be used with ocr for UIs consisting of text
    # on buttons
    frame = _imread('buttons.png')
    button = _imread('button.png')

    text = [
        stbt.ocr(frame=cv2.absdiff(_crop(frame, m.region), button))
        for m in stbt.match_all(
            button, frame=frame, match_parameters=mp(confirm_method='none'))]
    text = sorted([t for t in text if t not in ['', '\\s']])
    print text
    assert text == [u'Button 1', u'Button 2', u'Buttons']


def test_that_results_dont_overlap():
    # This is a regression test for a bug seen in an earlier implementation of
    # `match_all`.
    frame = _imread("action-panel.png")
    all_matches = set()
    for m in stbt.match_all(
            "action-panel-template.png", frame=frame,
            match_parameters=mp(confirm_method="normed-absdiff")):
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


def test_that_match_all_obeys_region():
    matches = sorted(m.region for m in stbt.match_all(
        "button.png", frame=_imread("buttons.png"),
        region=stbt.Region(x=160, y=60, right=340, bottom=190)))
    print matches
    assert matches == [stbt.Region(x, y, width=135, height=44) for x, y in [
        (177, 75), (177, 119)]]


# These ImageLogger tests are very basic regression tests. Possible
# improvements include opening the debug html in a browser under "stbt
# virtual-stb" and compare a screenshot; or using "stbt auto-selftest" to
# generate the tests.

def test_match_all_image_debug_when_first_pass_gives_no_matches():
    with scoped_curdir(), scoped_debug_level(2):
        matches = list(stbt.match_all(
            "videotestsrc-redblue-flipped.png",
            frame=_imread("videotestsrc-full-frame.png")))
        print matches
        assert len(matches) == 0
        _verify_stbt_debug_dir([
            'index.html',
            'level2-source.png',
            'level2-source_matchtemplate.png',
            'level2-source_with_match.png',
            'level2-source_with_rois.png',
            'level2-template.png',
            'match0-heatmap.png',
            'match0-source_with_match.png',
            'source.png',
            'template.png',
        ])


def test_match_all_image_debug_when_first_pass_stops_with_a_nonmatch():
    with scoped_curdir(), scoped_debug_level(2):
        matches = list(stbt.match_all(
            "button.png", frame=_imread("buttons.png"),
            match_parameters=mp(match_threshold=0.99)))
        print matches
        assert len(matches) == 6
        _verify_stbt_debug_dir([
            'index.html',
            'level0-source.png',
            'level0-source_matchtemplate.png',
            'level0-source_matchtemplate_threshold.png',
            'level0-source_with_match.png',
            'level0-source_with_rois.png',
            'level0-template.png',
            'level1-source.png',
            'level1-source_matchtemplate.png',
            'level1-source_matchtemplate_threshold.png',
            'level1-source_with_match.png',
            'level1-source_with_rois.png',
            'level1-template.png',
            'level2-source.png',
            'level2-source_matchtemplate.png',
            'level2-source_matchtemplate_threshold.png',
            'level2-source_with_match.png',
            'level2-source_with_rois.png',
            'level2-template.png',
            'match0-confirm-absdiff.png',
            'match0-confirm-absdiff_threshold.png',
            'match0-confirm-absdiff_threshold_erode.png',
            'match0-confirm-source_roi.png',
            'match0-confirm-source_roi_gray.png',
            'match0-confirm-template_gray.png',
            'match0-heatmap.png',
            'match0-source_with_match.png',
            'match1-confirm-absdiff.png',
            'match1-confirm-absdiff_threshold.png',
            'match1-confirm-absdiff_threshold_erode.png',
            'match1-confirm-source_roi.png',
            'match1-confirm-source_roi_gray.png',
            'match1-confirm-template_gray.png',
            'match1-heatmap.png',
            'match1-source_with_match.png',
            'match2-confirm-absdiff.png',
            'match2-confirm-absdiff_threshold.png',
            'match2-confirm-absdiff_threshold_erode.png',
            'match2-confirm-source_roi.png',
            'match2-confirm-source_roi_gray.png',
            'match2-confirm-template_gray.png',
            'match2-heatmap.png',
            'match2-source_with_match.png',
            'match3-confirm-absdiff.png',
            'match3-confirm-absdiff_threshold.png',
            'match3-confirm-absdiff_threshold_erode.png',
            'match3-confirm-source_roi.png',
            'match3-confirm-source_roi_gray.png',
            'match3-confirm-template_gray.png',
            'match3-heatmap.png',
            'match3-source_with_match.png',
            'match4-confirm-absdiff.png',
            'match4-confirm-absdiff_threshold.png',
            'match4-confirm-absdiff_threshold_erode.png',
            'match4-confirm-source_roi.png',
            'match4-confirm-source_roi_gray.png',
            'match4-confirm-template_gray.png',
            'match4-heatmap.png',
            'match4-source_with_match.png',
            'match5-confirm-absdiff.png',
            'match5-confirm-absdiff_threshold.png',
            'match5-confirm-absdiff_threshold_erode.png',
            'match5-confirm-source_roi.png',
            'match5-confirm-source_roi_gray.png',
            'match5-confirm-template_gray.png',
            'match5-heatmap.png',
            'match5-source_with_match.png',
            'match6-heatmap.png',
            'match6-source_with_match.png',
            'source.png',
            'template.png',
        ])


def test_match_all_image_debug_when_second_pass_stops_with_a_nonmatch():
    with scoped_curdir(), scoped_debug_level(2):
        matches = list(stbt.match_all(
            "button.png", frame=_imread("buttons.png")))
        print matches
        assert len(matches) == 6
        _verify_stbt_debug_dir([
            'index.html',
            'level0-source.png',
            'level0-source_matchtemplate.png',
            'level0-source_matchtemplate_threshold.png',
            'level0-source_with_match.png',
            'level0-source_with_rois.png',
            'level0-template.png',
            'level1-source.png',
            'level1-source_matchtemplate.png',
            'level1-source_matchtemplate_threshold.png',
            'level1-source_with_match.png',
            'level1-source_with_rois.png',
            'level1-template.png',
            'level2-source.png',
            'level2-source_matchtemplate.png',
            'level2-source_matchtemplate_threshold.png',
            'level2-source_with_match.png',
            'level2-source_with_rois.png',
            'level2-template.png',
            'match0-confirm-absdiff.png',
            'match0-confirm-absdiff_threshold.png',
            'match0-confirm-absdiff_threshold_erode.png',
            'match0-confirm-source_roi.png',
            'match0-confirm-source_roi_gray.png',
            'match0-confirm-template_gray.png',
            'match0-heatmap.png',
            'match0-source_with_match.png',
            'match1-confirm-absdiff.png',
            'match1-confirm-absdiff_threshold.png',
            'match1-confirm-absdiff_threshold_erode.png',
            'match1-confirm-source_roi.png',
            'match1-confirm-source_roi_gray.png',
            'match1-confirm-template_gray.png',
            'match1-heatmap.png',
            'match1-source_with_match.png',
            'match2-confirm-absdiff.png',
            'match2-confirm-absdiff_threshold.png',
            'match2-confirm-absdiff_threshold_erode.png',
            'match2-confirm-source_roi.png',
            'match2-confirm-source_roi_gray.png',
            'match2-confirm-template_gray.png',
            'match2-heatmap.png',
            'match2-source_with_match.png',
            'match3-confirm-absdiff.png',
            'match3-confirm-absdiff_threshold.png',
            'match3-confirm-absdiff_threshold_erode.png',
            'match3-confirm-source_roi.png',
            'match3-confirm-source_roi_gray.png',
            'match3-confirm-template_gray.png',
            'match3-heatmap.png',
            'match3-source_with_match.png',
            'match4-confirm-absdiff.png',
            'match4-confirm-absdiff_threshold.png',
            'match4-confirm-absdiff_threshold_erode.png',
            'match4-confirm-source_roi.png',
            'match4-confirm-source_roi_gray.png',
            'match4-confirm-template_gray.png',
            'match4-heatmap.png',
            'match4-source_with_match.png',
            'match5-confirm-absdiff.png',
            'match5-confirm-absdiff_threshold.png',
            'match5-confirm-absdiff_threshold_erode.png',
            'match5-confirm-source_roi.png',
            'match5-confirm-source_roi_gray.png',
            'match5-confirm-template_gray.png',
            'match5-heatmap.png',
            'match5-source_with_match.png',
            'match6-confirm-absdiff.png',
            'match6-confirm-absdiff_threshold.png',
            'match6-confirm-absdiff_threshold_erode.png',
            'match6-confirm-source_roi.png',
            'match6-confirm-source_roi_gray.png',
            'match6-confirm-template_gray.png',
            'match6-heatmap.png',
            'match6-source_with_match.png',
            'source.png',
            'template.png',
        ])


def test_match_all_image_debug_with_normed_absdiff():
    with scoped_curdir(), scoped_debug_level(2):
        matches = list(stbt.match_all(
            "button.png", frame=_imread("buttons.png"),
            match_parameters=mp(confirm_method="normed-absdiff",
                                confirm_threshold=0.3)))
        print matches
        assert len(matches) == 6
        _verify_stbt_debug_dir([
            'index.html',
            'level0-source.png',
            'level0-source_matchtemplate.png',
            'level0-source_matchtemplate_threshold.png',
            'level0-source_with_match.png',
            'level0-source_with_rois.png',
            'level0-template.png',
            'level1-source.png',
            'level1-source_matchtemplate.png',
            'level1-source_matchtemplate_threshold.png',
            'level1-source_with_match.png',
            'level1-source_with_rois.png',
            'level1-template.png',
            'level2-source.png',
            'level2-source_matchtemplate.png',
            'level2-source_matchtemplate_threshold.png',
            'level2-source_with_match.png',
            'level2-source_with_rois.png',
            'level2-template.png',
            'match0-confirm-absdiff.png',
            'match0-confirm-absdiff_threshold.png',
            'match0-confirm-absdiff_threshold_erode.png',
            'match0-confirm-source_roi.png',
            'match0-confirm-source_roi_gray.png',
            'match0-confirm-source_roi_gray_normalized.png',
            'match0-confirm-template_gray.png',
            'match0-confirm-template_gray_normalized.png',
            'match0-heatmap.png',
            'match0-source_with_match.png',
            'match1-confirm-absdiff.png',
            'match1-confirm-absdiff_threshold.png',
            'match1-confirm-absdiff_threshold_erode.png',
            'match1-confirm-source_roi.png',
            'match1-confirm-source_roi_gray.png',
            'match1-confirm-source_roi_gray_normalized.png',
            'match1-confirm-template_gray.png',
            'match1-confirm-template_gray_normalized.png',
            'match1-heatmap.png',
            'match1-source_with_match.png',
            'match2-confirm-absdiff.png',
            'match2-confirm-absdiff_threshold.png',
            'match2-confirm-absdiff_threshold_erode.png',
            'match2-confirm-source_roi.png',
            'match2-confirm-source_roi_gray.png',
            'match2-confirm-source_roi_gray_normalized.png',
            'match2-confirm-template_gray.png',
            'match2-confirm-template_gray_normalized.png',
            'match2-heatmap.png',
            'match2-source_with_match.png',
            'match3-confirm-absdiff.png',
            'match3-confirm-absdiff_threshold.png',
            'match3-confirm-absdiff_threshold_erode.png',
            'match3-confirm-source_roi.png',
            'match3-confirm-source_roi_gray.png',
            'match3-confirm-source_roi_gray_normalized.png',
            'match3-confirm-template_gray.png',
            'match3-confirm-template_gray_normalized.png',
            'match3-heatmap.png',
            'match3-source_with_match.png',
            'match4-confirm-absdiff.png',
            'match4-confirm-absdiff_threshold.png',
            'match4-confirm-absdiff_threshold_erode.png',
            'match4-confirm-source_roi.png',
            'match4-confirm-source_roi_gray.png',
            'match4-confirm-source_roi_gray_normalized.png',
            'match4-confirm-template_gray.png',
            'match4-confirm-template_gray_normalized.png',
            'match4-heatmap.png',
            'match4-source_with_match.png',
            'match5-confirm-absdiff.png',
            'match5-confirm-absdiff_threshold.png',
            'match5-confirm-absdiff_threshold_erode.png',
            'match5-confirm-source_roi.png',
            'match5-confirm-source_roi_gray.png',
            'match5-confirm-source_roi_gray_normalized.png',
            'match5-confirm-template_gray.png',
            'match5-confirm-template_gray_normalized.png',
            'match5-heatmap.png',
            'match5-source_with_match.png',
            'match6-confirm-absdiff.png',
            'match6-confirm-absdiff_threshold.png',
            'match6-confirm-absdiff_threshold_erode.png',
            'match6-confirm-source_roi.png',
            'match6-confirm-source_roi_gray.png',
            'match6-confirm-source_roi_gray_normalized.png',
            'match6-confirm-template_gray.png',
            'match6-confirm-template_gray_normalized.png',
            'match6-heatmap.png',
            'match6-source_with_match.png',
            'source.png',
            'template.png'
        ])


def _verify_stbt_debug_dir(expected_files):
    debug_dir = glob("stbt-debug/match/*")[0]
    print debug_dir
    actual_files = sorted(os.listdir(debug_dir))
    print actual_files
    assert sorted(expected_files) == actual_files


@contextmanager
def scoped_debug_level(n):
    """Don't send debug output to stderr as it messes up "make check" output."""
    import _stbt.logging

    original_stderr = sys.stderr
    sys.stderr = sys.stdout
    try:
        with _stbt.logging.scoped_debug_level(n):
            yield
    finally:
        sys.stderr = original_stderr


def _imread(filename):
    img = cv2.imread(os.path.join(TESTS_DIR, filename))
    assert img is not None
    return img
