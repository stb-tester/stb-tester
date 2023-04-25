import os
import random
import re
import timeit

import cv2
import numpy
import pytest

import stbt_core as stbt
from _stbt import cv2_compat
from _stbt.imgutils import _image_region
from _stbt.logging import scoped_debug_level
from _stbt.match import _merge_regions
from tests.test_core import _find_file
from tests.test_ocr import requires_tesseract


def mp(match_method=stbt.MatchMethod.SQDIFF, match_threshold=None, **kwargs):
    if match_threshold is None and match_method != stbt.MatchMethod.SQDIFF:
        match_threshold = 0.8
    return stbt.MatchParameters(match_method, match_threshold, **kwargs)


def black(width=1280, height=720, value=0):
    return numpy.ones((height, width, 3), dtype=numpy.uint8) * value


def test_that_matchresult_image_matches_template_passed_to_match():
    assert stbt.match("black.png", frame=black()).image.filename == "black.png"


def test_that_matchresult_str_image_matches_template_passed_to_match(
        test_pack_root):  # pylint:disable=unused-argument
    assert re.search(r"image=<Image\(filename=u?'black.png'",
                     str(stbt.match("black.png", frame=black())))


def test_that_matchresult_str_image_matches_template_passed_to_match_custom():
    assert "image=<Image(filename=None, dimensions=30x30x3)>" in str(
        stbt.match(black(30, 30), frame=black()))


def test_matchresult_region_when_first_pyramid_level_fails_to_match():
    f = stbt.load_image("videotestsrc-full-frame.png")
    r = stbt.match("videotestsrc-redblue-flipped.png", frame=f).region
    assert r.width == 92
    assert r.height == 160


def test_match_error_message_for_too_small_frame_and_region():
    stbt.match("videotestsrc-redblue.png", frame=black(width=92, height=160))
    stbt.match("videotestsrc-redblue.png", frame=black(),
               region=stbt.Region(x=1188, y=560, width=92, height=160))

    with pytest.raises(ValueError) as excinfo:
        stbt.match("videotestsrc-redblue.png",
                   frame=black(width=91, height=160))
    assert (
        "Frame (160, 91, 3) must be larger than reference image (160, 92, 3)"
        in str(excinfo.value))

    with pytest.raises(ValueError) as excinfo:
        stbt.match("videotestsrc-redblue.png",
                   frame=black(width=92, height=159))
    assert (
        "Frame (159, 92, 3) must be larger than reference image (160, 92, 3)"
        in str(excinfo.value))

    with pytest.raises(ValueError) as excinfo:
        # Region seems large enough but actually it extends beyond the frame
        stbt.match("videotestsrc-redblue.png", frame=black(),
                   region=stbt.Region(x=1189, y=560, width=92, height=160))
    assert (
        "Region(x=1189, y=560, right=1280, bottom=720) must be larger than "
        "reference image (160, 92, 3)"
        in str(excinfo.value))

    with pytest.raises(ValueError) as excinfo:
        # Region seems large enough but actually it extends beyond the frame
        stbt.match("videotestsrc-redblue.png", frame=black(),
                   region=stbt.Region(x=1188, y=561, width=92, height=160))
    assert (
        "Region(x=1188, y=561, right=1280, bottom=720) must be larger than "
        "reference image (160, 92, 3)"
        in str(excinfo.value))


@pytest.mark.parametrize("match_method", [
    stbt.MatchMethod.SQDIFF,
    stbt.MatchMethod.SQDIFF_NORMED,
])
def test_matching_grayscale_array_with_grayscale_frame(match_method):
    img = stbt.load_image("videotestsrc-redblue.png", color_channels=1)
    assert img.shape[2] == 1
    frame = stbt.load_image("videotestsrc-full-frame.png", color_channels=1)
    assert frame.shape[2] == 1
    assert stbt.match(img, frame,
                      match_parameters=mp(match_method=match_method))


@pytest.mark.parametrize("filename", [
    "videotestsrc-grayscale.png",
    "videotestsrc-grayscale-alpha.png",
])
def test_that_match_converts_grayscale_reference_image(filename):
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
    print(matches)
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
    print(matches)
    assert overlapped_button not in matches
    assert sorted(plain_buttons + labelled_buttons + [overlapping_button]) == \
        sorted(matches)


def test_match_all_with_transparent_reference_image():
    frame = stbt.load_image("buttons-on-blue-background.png")
    matches = list(m.region for m in stbt.match_all(
        "button-transparent.png", frame=frame))
    print(matches)
    assert overlapped_button not in matches
    assert (sorted(plain_buttons + labelled_buttons + [overlapping_button]) ==
            sorted(matches))


def test_completely_transparent_reference_image():
    f = stbt.load_image("buttons-on-blue-background.png")
    assert len(list(stbt.match_all(
        "completely-transparent.png", frame=f))) == 18


def test_that_partly_opaque_alpha_is_treated_as_fully_transparent():
    f = stbt.load_image("buttons-on-blue-background.png")
    m1 = stbt.match("button-partly-transparent.png", frame=f)
    m2 = stbt.match("button-transparent.png", frame=f)
    assert m1
    assert m2
    assert numpy.isclose(m1.first_pass_result, m2.first_pass_result)


@pytest.mark.parametrize("shape", [
    (268, 434, 1),
    (268, 434),
])
def test_transparent_reference_image_with_single_channel_frame(shape):
    f = stbt.load_image("buttons-on-blue-background.png", color_channels=1)
    f.shape = shape
    assert stbt.match("button-grayscale.png", frame=f)


@pytest.mark.parametrize("frame,image,expected_region", [
    # pylint:disable=bad-whitespace,line-too-long
    ("images/regression/roku-tile-frame.png", "images/regression/roku-tile-selection.png", stbt.Region(x=325, y=145, right=545, bottom=325)),
    ("images/regression/xfinity-frame.png",   "images/regression/xfinity-selection.png",   stbt.Region(x=68, y=157, right=300, bottom=473)),
])
def test_transparent_reference_image_false_negative_caused_by_pyramid(
        frame, image, expected_region):
    # This is a regression test for a bug in the pyramid optimisation when
    # the reference image has a very small number of pixels, or the only non-
    # transparent pixels are near the edges of reference image:
    # At the smaller pyramid levels, the pixels near the edge of the reference
    # image won't match exactly because the corresponding pixels in the
    # down-scaled frame have been blurred. We also blur the reference image
    # before down-scaling, but since it doesn't know what's outside its edges,
    # it won't have the  blurring near the edge.
    frame = stbt.load_image(frame)
    m = stbt.match(image, frame=frame)
    assert m
    assert expected_region.contains(m.region)


@pytest.mark.parametrize("frame,image", [
    # pylint:disable=bad-whitespace,line-too-long
    ("images/regression/badpyramid-frame.png",  "images/regression/badpyramid-reference.png"),
    ("images/regression/badpyramid-frame2.png", "images/regression/badpyramid-reference2.png"),
])
@pytest.mark.parametrize("match_method,match_threshold", [
    (stbt.MatchMethod.SQDIFF, 0.98),
    (stbt.MatchMethod.SQDIFF_NORMED, 0.8),
    (stbt.MatchMethod.CCORR_NORMED, 0.8),
    (stbt.MatchMethod.CCOEFF_NORMED, 0.8),
])
def test_pyramid_roi_too_small(frame, image, match_method, match_threshold):
    # This is a regression test for an error that was seen with a particular
    # frame from a single test-run, with SQDIFF_NORMED:
    # cv2.error: (-215) _img.size().height <= _templ.size().height &&
    # _img.size().width <= _templ.size().width in function matchTemplate
    with scoped_debug_level(2):
        stbt.match(
            image,
            frame=stbt.load_image(frame),
            match_parameters=stbt.MatchParameters(
                match_method=match_method,
                match_threshold=match_threshold))


@pytest.mark.parametrize("image,expected", [
    # pylint:disable=bad-whitespace,line-too-long
    ("red-blue-columns",             stbt.Region(x=0, y=0, width=40, height=40)),
    ("red-blue-columns-transparent", stbt.Region(x=0, y=0, width=40, height=40)),
    ("blue-red-columns",             stbt.Region(x=1240, y=680, width=40, height=40)),
    ("blue-red-columns-transparent", stbt.Region(x=1240, y=680, width=40, height=40)),
    ("red-blue-rows",                stbt.Region(x=1240, y=0, width=40, height=40)),
    ("red-blue-rows-transparent",    stbt.Region(x=1240, y=0, width=40, height=40)),
    ("blue-red-rows",                stbt.Region(x=0, y=680, width=40, height=40)),
    ("blue-red-rows-transparent",    stbt.Region(x=0, y=680, width=40, height=40)),
    ("red-dots",             stbt.Region(x=280, y=302, width=21, height=21)),
    ("red-dots-1px-border",  stbt.Region(x=279, y=301, width=23, height=23)),
    ("blue-dots",            stbt.Region(x=307, y=303, width=21, height=21)),
    ("blue-dots-1px-border", stbt.Region(x=306, y=302, width=23, height=23)),
])
def test_match_region(image, expected):
    frame = stbt.load_image("images/region/frame.png")
    m = stbt.match("images/region/%s.png" % image, frame=frame)
    assert m
    assert m.region == expected


@pytest.mark.parametrize("x,y", [
    # "-20" means "1 image width away from the frame's right or bottom edge".
    (0, 0), (-20, 0), (0, -20), (-20, -20),  # corners
    (50, 0), (-20, 50), (50, -20), (0, 50),  # edges
])
@pytest.mark.parametrize("offset_x,offset_y", [
    # Right at the edge or corner; 1px away horizontally, or vertically, or
    # both; 2px away etc.
    (0, 0),
    (1, 0),
    (0, 1),
    (1, 1),
    (2, 0),
    (0, 2),
    (2, 2),
    (3, 3),
    (4, 4),
    (5, 5),
    # These are outside of the frame so they shouldn't match
    (-1, 0),
    (0, -1),
    (-1, -1),
    (-2, 0),
    (0, -2),
    (-2, -2),
    (-10, 0),
    (0, -10),
    (-10, -10),
])
@pytest.mark.parametrize("width,height", [
    (20, 20),
    (20, 21),
    (21, 20),
    (21, 21),
    (31, 30),
    (40, 40),
    (40, 41),
    (41, 40),
    (41, 41),
    (158, 88),
])
@pytest.mark.parametrize("frame_width,frame_height", [
    (160, 90),
    (159, 89),  # an odd-sized "frame" can happen if the user gives a region
])
def test_match_region2(x, y, offset_x, offset_y, width, height,
                       frame_width, frame_height):
    if x >= 0:
        x = x + offset_x
    else:
        x = frame_width - width - offset_x
    if y >= 0:
        y = y + offset_y
    else:
        y = frame_height - height - offset_y
    region = stbt.Region(x, y, width=width, height=height)
    image = numpy.ones((region.height, region.width, 3), numpy.uint8) * 255
    image[5:-5, 5:-5] = (255, 0, 0)
    frame = black(frame_width, frame_height)
    frame[region.to_slice()] = image[
        0 if region.y >= 0 else -region.y :
            region.height if region.bottom <= frame_height
            else frame_height - region.y,
        0 if region.x >= 0 else -region.x :
            region.width if region.right <= frame_width
            else frame_width - region.x] * .85
    # N.B. .85 is the lowest at which all the tests still passed when I
    # disabled the pyramid optimisation.

    should_match = _image_region(frame).contains(region)

    m = stbt.match(image, frame)
    if should_match != m.match or os.environ.get("STBT_DEBUG"):
        with scoped_debug_level(2):
            stbt.match(image, frame)
    assert should_match == m.match
    if should_match:
        assert m.region == region


@requires_tesseract
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
    print(text)
    assert text == ['Button 1', 'Button 2', 'Buttons']


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
        print(m)
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
    print(matches)
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

    print(matches)
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


@pytest.mark.skipif(cv2_compat.version >= [4, 4],
                    reason="sqdiff-normed has implemented mask support")
def test_transparent_reference_image_with_sqdiff_normed_raises_valueerror():
    f = stbt.load_image("buttons-on-blue-background.png")
    with pytest.raises(ValueError):
        stbt.match("button-transparent.png", f,
                   match_parameters=mp(stbt.MatchMethod.SQDIFF_NORMED))


def test_that_build_pyramid_relaxes_mask():
    from _stbt.match import _build_pyramid

    mask = numpy.ones((200, 20, 3), dtype=numpy.uint8) * 255
    mask[5:9, 5:9] = 0  # first 0 is an even row/col, last 0 is an odd row/col
    n = mask.size - numpy.count_nonzero(mask)
    assert n == 4 * 4 * 3
    cv2.imwrite("/tmp/dave1.png", mask)

    with scoped_debug_level(2):
        mask_pyramid = _build_pyramid(mask, 2, is_mask=True)
    assert numpy.all(mask_pyramid[0] == mask)

    downsampled = mask_pyramid[1]
    cv2.imwrite("/tmp/dave2.png", downsampled)
    assert downsampled.shape == (98, 8, 3)
    print(downsampled[:, :, 0])
    # pylint:disable=bad-whitespace
    expected = \
        [[255, 255, 255, 255, 255, 255, 255, 255],
         [255,   0,   0,   0,   0, 255, 255, 255],
         [255,   0,   0,   0,   0, 255, 255, 255],
         [255,   0,   0,   0,   0, 255, 255, 255],
         [255,   0,   0,   0,   0, 255, 255, 255]] + \
        [[255, 255, 255, 255, 255, 255, 255, 255]] * 93
    assert numpy.all(downsampled[:, :, 0] == expected)


def test_png_with_16_bits_per_channel():
    assert cv2.imread(_find_file("uint16.png"), cv2.IMREAD_UNCHANGED).dtype == \
        numpy.uint16  # Sanity check (that this test is valid)

    assert stbt.match(
        "tests/uint16.png",
        frame=cv2.imread(_find_file("uint8.png")))


def test_match_fast_path():
    # This is just an example of typical use
    assert stbt.match("action-panel-prototype.png",
                      frame=stbt.load_image("action-panel.png"))


def test_that_match_fast_path_is_equivalent():
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
        if isinstance(frame, str):
            frame = stbt.load_image(frame, color_channels=3)
        reference = stbt.load_image(reference)
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
    _merge_regions(regions)
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

    times = timeit.repeat(lambda: _merge_regions(regions[:]),
                          number=1, repeat=10)
    print(times)
    print(min(times))
    assert min(times) < (0.001 * n / 20)
