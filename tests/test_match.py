import itertools
import os
import subprocess
from textwrap import dedent

import cv2
import numpy
import pytest

import stbt
from _stbt.logging import ImageLogger, scoped_debug_level
from _stbt.utils import scoped_curdir
from stbt import MatchParameters as mp


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
    f = stbt.load_image("videotestsrc-full-frame.png")
    assert stbt.Region(184, 0, width=92, height=160) == stbt.match(
        "videotestsrc-redblue-flipped.png", frame=f).region


def test_that_match_rejects_greyscale_template():
    grey = cv2.cvtColor(stbt.load_image("black.png"), cv2.COLOR_BGR2GRAY)
    with pytest.raises(ValueError):
        stbt.match(grey, frame=black())


def test_matching_greyscale_template():
    assert stbt.match(
        cv2.cvtColor(stbt.load_image("videotestsrc-redblue.png"),
                     cv2.COLOR_BGR2GRAY),
        frame=cv2.cvtColor(stbt.load_image("videotestsrc-full-frame.png"),
                           cv2.COLOR_BGR2GRAY))


def test_that_if_image_doesnt_match_match_all_returns_empty_array():
    assert [] == list(stbt.match_all(
        'button.png', frame=stbt.load_image('black-full-frame.png')))


def test_that_match_all_finds_all_matches():
    plain_buttons = [stbt.Region(x, y, width=135, height=44) for x, y in [
        (28, 1), (163, 1), (177, 75), (177, 119), (177, 163), (298, 1)]]

    matches = list(m.region for m in stbt.match_all(
        'button.png', frame=stbt.load_image('buttons.png')))
    print matches
    assert plain_buttons == sorted(matches)


def test_that_match_all_can_find_labelled_matches():
    plain_buttons = [stbt.Region(x, y, width=135, height=44) for x, y in [
        (28, 1), (163, 1), (177, 75), (177, 119), (177, 163), (298, 1)]]
    labelled_buttons = [stbt.Region(x, y, width=135, height=44) for x, y in [
        (1, 65), (6, 137), (123, 223)]]
    overlapped_button = stbt.Region(3, 223, width=135, height=44)

    frame = stbt.load_image('buttons.png')

    matches = list(m.region for m in stbt.match_all(
        'button.png', frame=frame, match_parameters=mp(confirm_method='none')))
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


def test_that_results_dont_overlap():
    # This is a regression test for a bug seen in an earlier implementation of
    # `match_all`.
    frame = stbt.load_image("action-panel.png")
    all_matches = set()
    for m in stbt.match_all("action-panel-template.png", frame=frame):
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
        "button.png", frame=stbt.load_image("buttons.png"),
        region=stbt.Region(x=160, y=60, right=340, bottom=190)))
    print matches
    assert matches == [stbt.Region(x, y, width=135, height=44) for x, y in [
        (177, 75), (177, 119)]]


def test_match_all_with_an_image_that_matches_everywhere():
    matches = sorted(m.region for m in stbt.match_all(
        "repeating-pattern.png",
        frame=stbt.load_image("repeating-pattern-full-frame.png")))

    expected_matches = sorted([stbt.Region(x, y, width=16, height=16)
                               for x in range(0, 320, 16)
                               for y in range(0, 240, 16)])

    print matches
    assert matches == expected_matches


def test_match_debug():
    expected = _find_file("stbt-debug-expected-output")

    # So that the output directory name doesn't depend on how many tests
    # were run before this one.
    ImageLogger._frame_number = itertools.count(1)  # pylint:disable=protected-access

    with scoped_curdir(), scoped_debug_level(2):
        # First pass gives no matches:
        matches = list(stbt.match_all(
            "videotestsrc-redblue-flipped.png",
            frame=stbt.load_image("videotestsrc-full-frame.png")))
        print matches
        assert len(matches) == 0

        # Multiple matches; first pass stops with a non-match:
        matches = list(stbt.match_all(
            "button.png", frame=stbt.load_image("buttons.png"),
            match_parameters=mp(match_threshold=0.99)))
        print matches
        assert len(matches) == 6

        # Multiple matches; second pass stops with a non-match:
        matches = list(stbt.match_all(
            "button.png", frame=stbt.load_image("buttons.png")))
        print matches
        assert len(matches) == 6

        # With absdiff:
        matches = list(stbt.match_all(
            "button.png", frame=stbt.load_image("buttons.png"),
            match_parameters=mp(confirm_method="absdiff",
                                confirm_threshold=0.16)))
        print matches
        assert len(matches) == 6

        files = subprocess.check_output("find stbt-debug | sort", shell=True)
        assert files == dedent("""\
            stbt-debug
            stbt-debug/00001
            stbt-debug/00001/index.html
            stbt-debug/00001/level2-source_matchtemplate.png
            stbt-debug/00001/level2-source.png
            stbt-debug/00001/level2-source_with_match.png
            stbt-debug/00001/level2-source_with_rois.png
            stbt-debug/00001/level2-template.png
            stbt-debug/00001/match0-heatmap.png
            stbt-debug/00001/match0-source_with_match.png
            stbt-debug/00001/source.png
            stbt-debug/00001/source_with_matches.png
            stbt-debug/00001/template.png
            stbt-debug/00002
            stbt-debug/00002/index.html
            stbt-debug/00002/level0-source_matchtemplate.png
            stbt-debug/00002/level0-source_matchtemplate_threshold.png
            stbt-debug/00002/level0-source.png
            stbt-debug/00002/level0-source_with_match.png
            stbt-debug/00002/level0-source_with_rois.png
            stbt-debug/00002/level0-template.png
            stbt-debug/00002/level1-source_matchtemplate.png
            stbt-debug/00002/level1-source_matchtemplate_threshold.png
            stbt-debug/00002/level1-source.png
            stbt-debug/00002/level1-source_with_match.png
            stbt-debug/00002/level1-source_with_rois.png
            stbt-debug/00002/level1-template.png
            stbt-debug/00002/level2-source_matchtemplate.png
            stbt-debug/00002/level2-source_matchtemplate_threshold.png
            stbt-debug/00002/level2-source.png
            stbt-debug/00002/level2-source_with_match.png
            stbt-debug/00002/level2-source_with_rois.png
            stbt-debug/00002/level2-template.png
            stbt-debug/00002/match0-confirm-absdiff.png
            stbt-debug/00002/match0-confirm-absdiff_threshold_erode.png
            stbt-debug/00002/match0-confirm-absdiff_threshold.png
            stbt-debug/00002/match0-confirm-source_roi_gray_normalized.png
            stbt-debug/00002/match0-confirm-source_roi_gray.png
            stbt-debug/00002/match0-confirm-source_roi.png
            stbt-debug/00002/match0-confirm-template_gray_normalized.png
            stbt-debug/00002/match0-confirm-template_gray.png
            stbt-debug/00002/match0-heatmap.png
            stbt-debug/00002/match0-source_with_match.png
            stbt-debug/00002/match1-confirm-absdiff.png
            stbt-debug/00002/match1-confirm-absdiff_threshold_erode.png
            stbt-debug/00002/match1-confirm-absdiff_threshold.png
            stbt-debug/00002/match1-confirm-source_roi_gray_normalized.png
            stbt-debug/00002/match1-confirm-source_roi_gray.png
            stbt-debug/00002/match1-confirm-source_roi.png
            stbt-debug/00002/match1-confirm-template_gray_normalized.png
            stbt-debug/00002/match1-confirm-template_gray.png
            stbt-debug/00002/match1-heatmap.png
            stbt-debug/00002/match1-source_with_match.png
            stbt-debug/00002/match2-confirm-absdiff.png
            stbt-debug/00002/match2-confirm-absdiff_threshold_erode.png
            stbt-debug/00002/match2-confirm-absdiff_threshold.png
            stbt-debug/00002/match2-confirm-source_roi_gray_normalized.png
            stbt-debug/00002/match2-confirm-source_roi_gray.png
            stbt-debug/00002/match2-confirm-source_roi.png
            stbt-debug/00002/match2-confirm-template_gray_normalized.png
            stbt-debug/00002/match2-confirm-template_gray.png
            stbt-debug/00002/match2-heatmap.png
            stbt-debug/00002/match2-source_with_match.png
            stbt-debug/00002/match3-confirm-absdiff.png
            stbt-debug/00002/match3-confirm-absdiff_threshold_erode.png
            stbt-debug/00002/match3-confirm-absdiff_threshold.png
            stbt-debug/00002/match3-confirm-source_roi_gray_normalized.png
            stbt-debug/00002/match3-confirm-source_roi_gray.png
            stbt-debug/00002/match3-confirm-source_roi.png
            stbt-debug/00002/match3-confirm-template_gray_normalized.png
            stbt-debug/00002/match3-confirm-template_gray.png
            stbt-debug/00002/match3-heatmap.png
            stbt-debug/00002/match3-source_with_match.png
            stbt-debug/00002/match4-confirm-absdiff.png
            stbt-debug/00002/match4-confirm-absdiff_threshold_erode.png
            stbt-debug/00002/match4-confirm-absdiff_threshold.png
            stbt-debug/00002/match4-confirm-source_roi_gray_normalized.png
            stbt-debug/00002/match4-confirm-source_roi_gray.png
            stbt-debug/00002/match4-confirm-source_roi.png
            stbt-debug/00002/match4-confirm-template_gray_normalized.png
            stbt-debug/00002/match4-confirm-template_gray.png
            stbt-debug/00002/match4-heatmap.png
            stbt-debug/00002/match4-source_with_match.png
            stbt-debug/00002/match5-confirm-absdiff.png
            stbt-debug/00002/match5-confirm-absdiff_threshold_erode.png
            stbt-debug/00002/match5-confirm-absdiff_threshold.png
            stbt-debug/00002/match5-confirm-source_roi_gray_normalized.png
            stbt-debug/00002/match5-confirm-source_roi_gray.png
            stbt-debug/00002/match5-confirm-source_roi.png
            stbt-debug/00002/match5-confirm-template_gray_normalized.png
            stbt-debug/00002/match5-confirm-template_gray.png
            stbt-debug/00002/match5-heatmap.png
            stbt-debug/00002/match5-source_with_match.png
            stbt-debug/00002/match6-heatmap.png
            stbt-debug/00002/match6-source_with_match.png
            stbt-debug/00002/source.png
            stbt-debug/00002/source_with_matches.png
            stbt-debug/00002/template.png
            stbt-debug/00003
            stbt-debug/00003/index.html
            stbt-debug/00003/level0-source_matchtemplate.png
            stbt-debug/00003/level0-source_matchtemplate_threshold.png
            stbt-debug/00003/level0-source.png
            stbt-debug/00003/level0-source_with_match.png
            stbt-debug/00003/level0-source_with_rois.png
            stbt-debug/00003/level0-template.png
            stbt-debug/00003/level1-source_matchtemplate.png
            stbt-debug/00003/level1-source_matchtemplate_threshold.png
            stbt-debug/00003/level1-source.png
            stbt-debug/00003/level1-source_with_match.png
            stbt-debug/00003/level1-source_with_rois.png
            stbt-debug/00003/level1-template.png
            stbt-debug/00003/level2-source_matchtemplate.png
            stbt-debug/00003/level2-source_matchtemplate_threshold.png
            stbt-debug/00003/level2-source.png
            stbt-debug/00003/level2-source_with_match.png
            stbt-debug/00003/level2-source_with_rois.png
            stbt-debug/00003/level2-template.png
            stbt-debug/00003/match0-confirm-absdiff.png
            stbt-debug/00003/match0-confirm-absdiff_threshold_erode.png
            stbt-debug/00003/match0-confirm-absdiff_threshold.png
            stbt-debug/00003/match0-confirm-source_roi_gray_normalized.png
            stbt-debug/00003/match0-confirm-source_roi_gray.png
            stbt-debug/00003/match0-confirm-source_roi.png
            stbt-debug/00003/match0-confirm-template_gray_normalized.png
            stbt-debug/00003/match0-confirm-template_gray.png
            stbt-debug/00003/match0-heatmap.png
            stbt-debug/00003/match0-source_with_match.png
            stbt-debug/00003/match1-confirm-absdiff.png
            stbt-debug/00003/match1-confirm-absdiff_threshold_erode.png
            stbt-debug/00003/match1-confirm-absdiff_threshold.png
            stbt-debug/00003/match1-confirm-source_roi_gray_normalized.png
            stbt-debug/00003/match1-confirm-source_roi_gray.png
            stbt-debug/00003/match1-confirm-source_roi.png
            stbt-debug/00003/match1-confirm-template_gray_normalized.png
            stbt-debug/00003/match1-confirm-template_gray.png
            stbt-debug/00003/match1-heatmap.png
            stbt-debug/00003/match1-source_with_match.png
            stbt-debug/00003/match2-confirm-absdiff.png
            stbt-debug/00003/match2-confirm-absdiff_threshold_erode.png
            stbt-debug/00003/match2-confirm-absdiff_threshold.png
            stbt-debug/00003/match2-confirm-source_roi_gray_normalized.png
            stbt-debug/00003/match2-confirm-source_roi_gray.png
            stbt-debug/00003/match2-confirm-source_roi.png
            stbt-debug/00003/match2-confirm-template_gray_normalized.png
            stbt-debug/00003/match2-confirm-template_gray.png
            stbt-debug/00003/match2-heatmap.png
            stbt-debug/00003/match2-source_with_match.png
            stbt-debug/00003/match3-confirm-absdiff.png
            stbt-debug/00003/match3-confirm-absdiff_threshold_erode.png
            stbt-debug/00003/match3-confirm-absdiff_threshold.png
            stbt-debug/00003/match3-confirm-source_roi_gray_normalized.png
            stbt-debug/00003/match3-confirm-source_roi_gray.png
            stbt-debug/00003/match3-confirm-source_roi.png
            stbt-debug/00003/match3-confirm-template_gray_normalized.png
            stbt-debug/00003/match3-confirm-template_gray.png
            stbt-debug/00003/match3-heatmap.png
            stbt-debug/00003/match3-source_with_match.png
            stbt-debug/00003/match4-confirm-absdiff.png
            stbt-debug/00003/match4-confirm-absdiff_threshold_erode.png
            stbt-debug/00003/match4-confirm-absdiff_threshold.png
            stbt-debug/00003/match4-confirm-source_roi_gray_normalized.png
            stbt-debug/00003/match4-confirm-source_roi_gray.png
            stbt-debug/00003/match4-confirm-source_roi.png
            stbt-debug/00003/match4-confirm-template_gray_normalized.png
            stbt-debug/00003/match4-confirm-template_gray.png
            stbt-debug/00003/match4-heatmap.png
            stbt-debug/00003/match4-source_with_match.png
            stbt-debug/00003/match5-confirm-absdiff.png
            stbt-debug/00003/match5-confirm-absdiff_threshold_erode.png
            stbt-debug/00003/match5-confirm-absdiff_threshold.png
            stbt-debug/00003/match5-confirm-source_roi_gray_normalized.png
            stbt-debug/00003/match5-confirm-source_roi_gray.png
            stbt-debug/00003/match5-confirm-source_roi.png
            stbt-debug/00003/match5-confirm-template_gray_normalized.png
            stbt-debug/00003/match5-confirm-template_gray.png
            stbt-debug/00003/match5-heatmap.png
            stbt-debug/00003/match5-source_with_match.png
            stbt-debug/00003/match6-confirm-absdiff.png
            stbt-debug/00003/match6-confirm-absdiff_threshold_erode.png
            stbt-debug/00003/match6-confirm-absdiff_threshold.png
            stbt-debug/00003/match6-confirm-source_roi_gray_normalized.png
            stbt-debug/00003/match6-confirm-source_roi_gray.png
            stbt-debug/00003/match6-confirm-source_roi.png
            stbt-debug/00003/match6-confirm-template_gray_normalized.png
            stbt-debug/00003/match6-confirm-template_gray.png
            stbt-debug/00003/match6-heatmap.png
            stbt-debug/00003/match6-source_with_match.png
            stbt-debug/00003/source.png
            stbt-debug/00003/source_with_matches.png
            stbt-debug/00003/template.png
            stbt-debug/00004
            stbt-debug/00004/index.html
            stbt-debug/00004/level0-source_matchtemplate.png
            stbt-debug/00004/level0-source_matchtemplate_threshold.png
            stbt-debug/00004/level0-source.png
            stbt-debug/00004/level0-source_with_match.png
            stbt-debug/00004/level0-source_with_rois.png
            stbt-debug/00004/level0-template.png
            stbt-debug/00004/level1-source_matchtemplate.png
            stbt-debug/00004/level1-source_matchtemplate_threshold.png
            stbt-debug/00004/level1-source.png
            stbt-debug/00004/level1-source_with_match.png
            stbt-debug/00004/level1-source_with_rois.png
            stbt-debug/00004/level1-template.png
            stbt-debug/00004/level2-source_matchtemplate.png
            stbt-debug/00004/level2-source_matchtemplate_threshold.png
            stbt-debug/00004/level2-source.png
            stbt-debug/00004/level2-source_with_match.png
            stbt-debug/00004/level2-source_with_rois.png
            stbt-debug/00004/level2-template.png
            stbt-debug/00004/match0-confirm-absdiff.png
            stbt-debug/00004/match0-confirm-absdiff_threshold_erode.png
            stbt-debug/00004/match0-confirm-absdiff_threshold.png
            stbt-debug/00004/match0-confirm-source_roi_gray.png
            stbt-debug/00004/match0-confirm-source_roi.png
            stbt-debug/00004/match0-confirm-template_gray.png
            stbt-debug/00004/match0-heatmap.png
            stbt-debug/00004/match0-source_with_match.png
            stbt-debug/00004/match1-confirm-absdiff.png
            stbt-debug/00004/match1-confirm-absdiff_threshold_erode.png
            stbt-debug/00004/match1-confirm-absdiff_threshold.png
            stbt-debug/00004/match1-confirm-source_roi_gray.png
            stbt-debug/00004/match1-confirm-source_roi.png
            stbt-debug/00004/match1-confirm-template_gray.png
            stbt-debug/00004/match1-heatmap.png
            stbt-debug/00004/match1-source_with_match.png
            stbt-debug/00004/match2-confirm-absdiff.png
            stbt-debug/00004/match2-confirm-absdiff_threshold_erode.png
            stbt-debug/00004/match2-confirm-absdiff_threshold.png
            stbt-debug/00004/match2-confirm-source_roi_gray.png
            stbt-debug/00004/match2-confirm-source_roi.png
            stbt-debug/00004/match2-confirm-template_gray.png
            stbt-debug/00004/match2-heatmap.png
            stbt-debug/00004/match2-source_with_match.png
            stbt-debug/00004/match3-confirm-absdiff.png
            stbt-debug/00004/match3-confirm-absdiff_threshold_erode.png
            stbt-debug/00004/match3-confirm-absdiff_threshold.png
            stbt-debug/00004/match3-confirm-source_roi_gray.png
            stbt-debug/00004/match3-confirm-source_roi.png
            stbt-debug/00004/match3-confirm-template_gray.png
            stbt-debug/00004/match3-heatmap.png
            stbt-debug/00004/match3-source_with_match.png
            stbt-debug/00004/match4-confirm-absdiff.png
            stbt-debug/00004/match4-confirm-absdiff_threshold_erode.png
            stbt-debug/00004/match4-confirm-absdiff_threshold.png
            stbt-debug/00004/match4-confirm-source_roi_gray.png
            stbt-debug/00004/match4-confirm-source_roi.png
            stbt-debug/00004/match4-confirm-template_gray.png
            stbt-debug/00004/match4-heatmap.png
            stbt-debug/00004/match4-source_with_match.png
            stbt-debug/00004/match5-confirm-absdiff.png
            stbt-debug/00004/match5-confirm-absdiff_threshold_erode.png
            stbt-debug/00004/match5-confirm-absdiff_threshold.png
            stbt-debug/00004/match5-confirm-source_roi_gray.png
            stbt-debug/00004/match5-confirm-source_roi.png
            stbt-debug/00004/match5-confirm-template_gray.png
            stbt-debug/00004/match5-heatmap.png
            stbt-debug/00004/match5-source_with_match.png
            stbt-debug/00004/match6-confirm-absdiff.png
            stbt-debug/00004/match6-confirm-absdiff_threshold_erode.png
            stbt-debug/00004/match6-confirm-absdiff_threshold.png
            stbt-debug/00004/match6-confirm-source_roi_gray.png
            stbt-debug/00004/match6-confirm-source_roi.png
            stbt-debug/00004/match6-confirm-template_gray.png
            stbt-debug/00004/match6-heatmap.png
            stbt-debug/00004/match6-source_with_match.png
            stbt-debug/00004/source.png
            stbt-debug/00004/source_with_matches.png
            stbt-debug/00004/template.png
            """)

        subprocess.check_call([
            "diff", "-u", "--exclude=*.png",
            # The exact output of cv2.matchtemplate isn't deterministic across
            # different versions of OpenCV:
            r"--ignore-matching-lines=0\.99",
            "--ignore-matching-lines=Region",
            expected, "stbt-debug"])

        # To update expected results in source checkout:
        # import shutil
        # shutil.rmtree(expected)
        # shutil.move("stbt-debug", expected)


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)
