import itertools
import os
import subprocess
from textwrap import dedent

import stbt_core as stbt
from _stbt.logging import ImageLogger, scoped_debug_level
from _stbt.utils import scoped_curdir
from stbt_core import MatchParameters as mp


def test_match_debug():
    # So that the output directory name doesn't depend on how many tests
    # were run before this one.
    ImageLogger._frame_number = itertools.count(1)

    with scoped_curdir(), scoped_debug_level(2):
        # First pass gives no matches:
        matches = list(stbt.match_all(
            "videotestsrc-redblue-flipped.png",
            frame=stbt.load_image("videotestsrc-full-frame.png")))
        print(matches)
        assert len(matches) == 0

        # Multiple matches; first pass stops with a non-match:
        matches = list(stbt.match_all(
            "button.png", frame=stbt.load_image("buttons.png"),
            match_parameters=mp(match_threshold=0.995)))
        print(matches)
        assert len(matches) == 6

        # Multiple matches; second pass stops with a non-match:
        matches = list(stbt.match_all(
            "button.png", frame=stbt.load_image("buttons.png")))
        print(matches)
        assert len(matches) == 6

        # With absdiff:
        matches = list(stbt.match_all(
            "button.png", frame=stbt.load_image("buttons.png"),
            match_parameters=mp(confirm_method="absdiff",
                                confirm_threshold=0.84)))
        print(matches)
        assert len(matches) == 6

        files = subprocess.check_output("find stbt-debug | sort", shell=True) \
                          .decode("utf-8")
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
            stbt-debug/00004/template.png
            """)

        assert_expected("stbt-debug-expected-output/match")


def test_motion_debug():
    # So that the output directory name doesn't depend on how many tests
    # were run before this one.
    ImageLogger._frame_number = itertools.count(1)

    def fake_frames():
        for i, f in enumerate(["box-00001.png",
                               "box-00002.png",
                               "box-00003.png"]):
            yield stbt.Frame(stbt.load_image(f), time=i)

    with scoped_curdir(), scoped_debug_level(2):

        for _ in stbt.detect_motion(frames=fake_frames()):
            pass
        for _ in stbt.detect_motion(frames=fake_frames(), mask="box-00000.png"):
            pass
        for _ in stbt.detect_motion(frames=fake_frames(),
                                    region=stbt.Region(0, 0, 320, 400)):
            pass

        files = subprocess.check_output("find stbt-debug | sort", shell=True) \
                          .decode("utf-8")
        assert files == dedent("""\
            stbt-debug
            stbt-debug/00001
            stbt-debug/00001/eroded.png
            stbt-debug/00001/index.html
            stbt-debug/00001/previous_frame.png
            stbt-debug/00001/source.png
            stbt-debug/00001/sqd.png
            stbt-debug/00001/thresholded.png
            stbt-debug/00002
            stbt-debug/00002/eroded.png
            stbt-debug/00002/index.html
            stbt-debug/00002/previous_frame.png
            stbt-debug/00002/source.png
            stbt-debug/00002/sqd.png
            stbt-debug/00002/thresholded.png
            stbt-debug/00003
            stbt-debug/00003/eroded.png
            stbt-debug/00003/index.html
            stbt-debug/00003/mask.png
            stbt-debug/00003/previous_frame.png
            stbt-debug/00003/source.png
            stbt-debug/00003/sqd.png
            stbt-debug/00003/thresholded.png
            stbt-debug/00004
            stbt-debug/00004/eroded.png
            stbt-debug/00004/index.html
            stbt-debug/00004/mask.png
            stbt-debug/00004/previous_frame.png
            stbt-debug/00004/source.png
            stbt-debug/00004/sqd.png
            stbt-debug/00004/thresholded.png
            stbt-debug/00005
            stbt-debug/00005/eroded.png
            stbt-debug/00005/index.html
            stbt-debug/00005/previous_frame.png
            stbt-debug/00005/source.png
            stbt-debug/00005/sqd.png
            stbt-debug/00005/thresholded.png
            stbt-debug/00006
            stbt-debug/00006/eroded.png
            stbt-debug/00006/index.html
            stbt-debug/00006/previous_frame.png
            stbt-debug/00006/source.png
            stbt-debug/00006/sqd.png
            stbt-debug/00006/thresholded.png
        """)

        assert_expected("stbt-debug-expected-output/motion")


def test_ocr_debug():
    # So that the output directory name doesn't depend on how many tests
    # were run before this one.
    ImageLogger._frame_number = itertools.count(1)

    f = stbt.load_image("action-panel.png")
    r = stbt.Region(0, 370, right=1280, bottom=410)
    c = (235, 235, 235)

    with scoped_curdir(), scoped_debug_level(2):

        stbt.ocr(f)
        stbt.ocr(f, region=r)
        stbt.ocr(f, region=r, text_color=c)

        stbt.match_text("Summary", f)  # no match
        stbt.match_text("Summary", f, region=r)  # no match
        stbt.match_text("Summary", f, region=r, text_color=c)

        files = subprocess.check_output("find stbt-debug | sort", shell=True) \
                          .decode("utf-8")
        assert files == dedent("""\
            stbt-debug
            stbt-debug/00001
            stbt-debug/00001/index.html
            stbt-debug/00001/source.png
            stbt-debug/00001/tessinput.png
            stbt-debug/00001/upsampled.png
            stbt-debug/00002
            stbt-debug/00002/index.html
            stbt-debug/00002/source.png
            stbt-debug/00002/tessinput.png
            stbt-debug/00002/upsampled.png
            stbt-debug/00003
            stbt-debug/00003/binarized.png
            stbt-debug/00003/diff.png
            stbt-debug/00003/index.html
            stbt-debug/00003/source.png
            stbt-debug/00003/tessinput.png
            stbt-debug/00003/upsampled.png
            stbt-debug/00004
            stbt-debug/00004/index.html
            stbt-debug/00004/source.png
            stbt-debug/00004/tessinput.png
            stbt-debug/00004/upsampled.png
            stbt-debug/00005
            stbt-debug/00005/index.html
            stbt-debug/00005/source.png
            stbt-debug/00005/tessinput.png
            stbt-debug/00005/upsampled.png
            stbt-debug/00006
            stbt-debug/00006/binarized.png
            stbt-debug/00006/diff.png
            stbt-debug/00006/index.html
            stbt-debug/00006/source.png
            stbt-debug/00006/tessinput.png
            stbt-debug/00006/upsampled.png
            """)

        # To see the generated files in tests/dave-debug/:
        # import shutil
        # shutil.move("stbt-debug", _find_file("dave-debug"))


def test_is_screen_black_debug():
    # So that the output directory name doesn't depend on how many tests
    # were run before this one.
    ImageLogger._frame_number = itertools.count(1)

    f = stbt.load_image("videotestsrc-full-frame.png")

    with scoped_curdir(), scoped_debug_level(2):

        stbt.is_screen_black(f)
        stbt.is_screen_black(f, mask="videotestsrc-mask-non-black.png")
        stbt.is_screen_black(f, mask="videotestsrc-mask-no-video.png")
        stbt.is_screen_black(f, region=stbt.Region(0, 0, 160, 120))

        files = subprocess.check_output("find stbt-debug | sort", shell=True) \
                          .decode("utf-8")
        assert files == dedent("""\
            stbt-debug
            stbt-debug/00001
            stbt-debug/00001/gray.png
            stbt-debug/00001/index.html
            stbt-debug/00001/non_black.png
            stbt-debug/00001/source.png
            stbt-debug/00002
            stbt-debug/00002/gray.png
            stbt-debug/00002/index.html
            stbt-debug/00002/mask.png
            stbt-debug/00002/non_black.png
            stbt-debug/00002/source.png
            stbt-debug/00003
            stbt-debug/00003/gray.png
            stbt-debug/00003/index.html
            stbt-debug/00003/mask.png
            stbt-debug/00003/non_black.png
            stbt-debug/00003/source.png
            stbt-debug/00004
            stbt-debug/00004/gray.png
            stbt-debug/00004/index.html
            stbt-debug/00004/non_black.png
            stbt-debug/00004/source.png
            """)

        assert_expected("stbt-debug-expected-output/is_screen_black")


def assert_expected(expected):
    expected = _find_file(expected)

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
