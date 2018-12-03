import itertools
import os
import subprocess
from textwrap import dedent

import stbt
from _stbt.logging import ImageLogger, scoped_debug_level
from _stbt.utils import scoped_curdir
from stbt import MatchParameters as mp


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
