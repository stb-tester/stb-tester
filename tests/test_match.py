import random
import timeit

import cv2
import numpy
import pytest

import stbt
from _stbt import cv2_compat
from _stbt.match import _merge_regions
from tests.test_core import _find_file


requires_opencv_3 = pytest.mark.skipif(cv2_compat.version < [3, 0, 0],
                                       reason="Requires OpenCV 3")


def mp(match_method=stbt.MatchMethod.SQDIFF, match_threshold=None, **kwargs):
    if match_threshold is None and match_method != stbt.MatchMethod.SQDIFF:
        match_threshold = 0.8
    return stbt.MatchParameters(match_method, match_threshold, **kwargs)


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
    r = stbt.match("videotestsrc-redblue-flipped.png", frame=f).region
    assert r.width == 92
    assert r.height == 160


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_that_match_rejects_greyscale_array(match_method):
    grey = cv2.cvtColor(stbt.load_image("black.png"), cv2.COLOR_BGR2GRAY)
    with pytest.raises(ValueError):
        stbt.match(grey, frame=black(),
                   match_parameters=mp(match_method=match_method))


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_matching_greyscale_array_with_greyscale_frame(match_method):
    assert stbt.match(
        cv2.cvtColor(stbt.load_image("videotestsrc-redblue.png"),
                     cv2.COLOR_BGR2GRAY),
        frame=cv2.cvtColor(stbt.load_image("videotestsrc-full-frame.png"),
                           cv2.COLOR_BGR2GRAY),
        match_parameters=mp(match_method=match_method))


@pytest.mark.parametrize("filename", [
    "videotestsrc-greyscale.png",
    "videotestsrc-greyscale-alpha.png",
])
def test_that_match_converts_greyscale_reference_image(filename):
    stbt.match(filename, frame=black())  # Doesn't raise
    stbt.match(stbt.load_image(filename), frame=black())


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_that_if_image_doesnt_match_match_all_returns_empty_array(match_method):
    assert [] == list(stbt.match_all(
        'button.png', frame=stbt.load_image('black-full-frame.png'),
        match_parameters=mp(match_method=match_method)))


plain_buttons = [stbt.Region(_x, _y, width=135, height=44) for _x, _y in [
    (28, 1), (163, 1), (177, 75), (177, 119), (177, 163), (298, 1)]]
labelled_buttons = [stbt.Region(_x, _y, width=135, height=44) for _x, _y in [
    (1, 65), (6, 137)]]
overlapping_button = stbt.Region(123, 223, width=135, height=44)
overlapped_button = stbt.Region(3, 223, width=135, height=44)


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
    stbt.MatchMethod.CCORR_NORMED,
    stbt.MatchMethod.CCOEFF_NORMED,
])
def test_that_match_all_finds_all_matches(match_method):
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
    frame = stbt.load_image('buttons.png')
    matches = list(m.region for m in stbt.match_all(
        'button.png', frame=frame,
        match_parameters=mp(match_method=match_method,
                            confirm_method=stbt.ConfirmMethod.NONE)))
    print matches
    assert overlapped_button not in matches
    assert sorted(plain_buttons + labelled_buttons + [overlapping_button]) == \
        sorted(matches)


@requires_opencv_3
def test_match_all_with_transparent_reference_image():
    frame = stbt.load_image("buttons-on-blue-background.png")
    matches = list(m.region for m in stbt.match_all(
        "button-transparent.png", frame=frame))
    print matches
    assert overlapped_button not in matches
    assert (sorted(plain_buttons + labelled_buttons + [overlapping_button]) ==
            sorted(matches))


@requires_opencv_3
def test_completely_transparent_reference_image():
    f = stbt.load_image("buttons-on-blue-background.png")
    assert len(list(stbt.match_all(
        "completely-transparent.png", frame=f))) == 18


@requires_opencv_3
def test_that_match_all_can_be_used_with_ocr_to_read_buttons():
    # Demonstrates how match_all can be used with ocr for UIs consisting of text
    # on buttons
    frame = stbt.load_image('buttons.png')

    text = [
        stbt.ocr(frame=stbt.crop(
            frame,
            m.region.extend(x=30, y=10, right=-30, bottom=-10)))
        for m in stbt.match_all('button-transparent.png', frame=frame)]
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


def test_transparent_reference_image_with_sqdiff_normed_raises_valueerror():
    f = stbt.load_image("buttons-on-blue-background.png")
    with pytest.raises(ValueError):
        stbt.match("button-transparent.png", f,
                   match_parameters=mp(stbt.MatchMethod.SQDIFF_NORMED))


def test_that_build_pyramid_relaxes_mask():
    from _stbt.match import _build_pyramid

    mask = numpy.ones((20, 20, 3), dtype=numpy.uint8) * 255
    mask[3:9, 3:9] = 0  # first 0 is an even row/col, last 0 is an odd row/col
    n = mask.size - numpy.count_nonzero(mask)
    assert n == 6 * 6 * 3
    cv2.imwrite("/tmp/dave1.png", mask)

    mask_pyramid = _build_pyramid(mask, 2, is_mask=True)
    assert numpy.all(mask_pyramid[0] == mask)

    downsampled = mask_pyramid[1]
    cv2.imwrite("/tmp/dave2.png", downsampled)
    assert downsampled.shape == (10, 10, 3)
    print downsampled[:, :, 0]  # pylint:disable=unsubscriptable-object
    n = downsampled.size - numpy.count_nonzero(downsampled)
    assert 3 * 3 * 3 <= n <= 6 * 6 * 3
    expected = [
        # pylint:disable=bad-whitespace
        [255, 255, 255, 255, 255, 255, 255, 255, 255, 255],
        [255,   0,   0,   0,   0,   0, 255, 255, 255, 255],
        [255,   0,   0,   0,   0,   0, 255, 255, 255, 255],
        [255,   0,   0,   0,   0,   0, 255, 255, 255, 255],
        [255,   0,   0,   0,   0,   0, 255, 255, 255, 255],
        [255,   0,   0,   0,   0,   0, 255, 255, 255, 255],
        [255, 255, 255, 255, 255, 255, 255, 255, 255, 255],
        [255, 255, 255, 255, 255, 255, 255, 255, 255, 255],
        [255, 255, 255, 255, 255, 255, 255, 255, 255, 255],
        [255, 255, 255, 255, 255, 255, 255, 255, 255, 255]]
    assert numpy.all(downsampled[:, :, 0] == expected)  # pylint:disable=unsubscriptable-object


@requires_opencv_3
def test_png_with_16_bits_per_channel():
    assert cv2.imread(_find_file("uint16.png"), cv2.IMREAD_UNCHANGED).dtype == \
        numpy.uint16  # Sanity check (that this test is valid)

    assert stbt.match(
        "tests/uint16.png",
        frame=cv2.imread(_find_file("uint8.png")))


@requires_opencv_3
def test_match_fast_path():
    # This is just an example of typical use
    assert stbt.match("action-panel-prototype.png",
                      frame=stbt.load_image("action-panel.png"))


@requires_opencv_3
def test_that_match_fast_path_is_equivalent():
    from _stbt.match import _load_image
    black_reference = black(10, 10)
    almost_black_reference = black(10, 10, value=1)
    black_frame = black(1280, 720)
    almost_black_frame = black(1280, 720, value=2)

    images = [
        ("videotestsrc-redblue.png", "videotestsrc-full-frame.png"),
        ("action-panel.png", "action-panel.png"),
        ("videotestsrc-full-frame.png", "videotestsrc-full-frame.png"),
        ("videotestsrc-redblue-flipped.png", "videotestsrc-full-frame.png"),
        ("button.png", "black-full-frame.png"),
        ("completely-transparent.png", "buttons-on-blue-background.png"),
        ("action-panel-template.png", "action-panel.png"),
        ("button.png", "buttons.png"),
        (black_reference, black_frame),
        (almost_black_reference, black_frame),
        (almost_black_reference, almost_black_frame),
        ("repeating-pattern.png", "repeating-pattern-full-frame.png"),
        ("button-transparent.png", "buttons.png"),
    ]
    for reference, frame in images:
        if isinstance(frame, (str, unicode)):
            frame = stbt.load_image(frame, cv2.IMREAD_COLOR)
        reference = _load_image(reference)
        orig_m = stbt.match(reference, frame=frame)
        fast_m = stbt.match(reference, frame=frame, region=orig_m.region)
        assert orig_m.time == fast_m.time
        assert orig_m.match == fast_m.match
        assert orig_m.region == fast_m.region
        assert bool(orig_m) == bool(fast_m)
        assert orig_m.first_pass_result == pytest.approx(
            fast_m.first_pass_result, abs=0.0001 if orig_m else 0.05)
        assert (orig_m.frame == fast_m.frame).all()
        if isinstance(orig_m.image, numpy.ndarray):
            assert (orig_m.image == fast_m.image).all()
        else:
            assert orig_m.image == fast_m.image


def test_merge_regions():
    regions = [stbt.Region(*x) for x in [
        (153, 156, 16, 4), (121, 155, 25, 5), (14, 117, 131, 32),
        (128, 100, 19, 5), (122, 81, 22, 14), (123, 73, 5, 4),
        (0, 71, 12, 75), (146, 64, 1, 1), (111, 64, 10, 2), (22, 62, 9, 4),
        (0, 60, 17, 10), (111, 54, 2, 2), (138, 47, 5, 2), (132, 47, 3, 1),
        (130, 46, 1, 2), (55, 32, 11, 1), (52, 32, 1, 1), (0, 29, 50, 28),
        (0, 20, 57, 4), (33, 0, 233, 139)]]
    regions = _merge_regions(regions)
    assert len(regions) == 9
    assert sorted(regions) == (
        [stbt.Region(*x) for x in [
            (0, 20, 57, 4), (0, 29, 50, 28), (0, 60, 17, 10), (0, 71, 12, 75),
            (14, 117, 131, 32), (22, 62, 9, 4), (33, 0, 233, 139),
            (121, 155, 25, 5), (153, 156, 16, 4)]])


@pytest.mark.parametrize("n", [20, 200, 2000])
def test_merge_regions_performance(n):
    random.seed(1)
    regions = []
    for _ in range(n):
        x = random.randint(0, 1280)
        y = random.randint(0, 720)
        right = random.randint(0, 1280)
        bottom = random.randint(0, 720)
        x, w = min(x, right), max(x, right) - min(x, right) + 1
        y, h = min(y, bottom), max(y, bottom) - min(y, bottom) + 1
        regions.append(stbt.Region(x, y, w, h))

    times = timeit.repeat(lambda: _merge_regions(regions), number=1, repeat=100)
    print times
    print "max: %f" % max(times)
    print "avg: %f" % (sum(times) / len(times))
    print "min: %f" % min(times)
    assert min(times) < (0.001 * n / 20)
