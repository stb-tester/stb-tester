# coding: utf-8

import distutils
import re
from textwrap import dedent
from unittest import SkipTest

import cv2
import pytest
from nose.tools import raises

import _stbt.core
import stbt


@pytest.mark.parametrize("image, expected_text, region, mode", [
    # pylint: disable=line-too-long
    ("Connection-status--white-on-dark-blue.png", "Connection status: Connected", stbt.Region.ALL, None),
    ("Connection-status--white-on-dark-blue.png", "Connected", stbt.Region(x=210, y=0, width=120, height=40), None),
    # ("Connection-status--white-on-dark-blue.png", "", None, None),  # uncomment when region=None doesn't raise -- see #433
    ("programme--white-on-black.png", "programme", stbt.Region.ALL, None),
    ("UJJM--white-text-on-grey-boxes.png", "", stbt.Region.ALL, None),
    ("UJJM--white-text-on-grey-boxes.png", "UJJM", stbt.Region.ALL, stbt.OcrMode.SINGLE_LINE),
])
def test_ocr_on_static_images(image, expected_text, region, mode):
    kwargs = {"region": region}
    if mode is not None:
        kwargs["mode"] = mode
    text = stbt.ocr(cv2.imread("tests/ocr/" + image), **kwargs)
    assert text == expected_text


# Remove when region=None doesn't raise -- see #433
@raises(TypeError)
def test_that_ocr_region_none_isnt_allowed():
    stbt.ocr(frame=cv2.imread("tests/ocr/small.png"), region=None)


def test_that_ocr_reads_unicode():
    text = stbt.ocr(frame=cv2.imread('tests/ocr/unicode.png'), lang='eng+deu')
    assert isinstance(text, unicode)
    assert u'£500\nDavid Röthlisberger' == text


def test_that_ocr_can_read_small_text():
    text = stbt.ocr(frame=cv2.imread('tests/ocr/small.png'))
    assert u'Small anti-aliased text is hard to read\nunless you magnify' == \
        text


ligature_text = dedent(u"""\
    All the similar "quotes" and "quotes",
    'quotes' and 'quotes' should be recognised.

    For the avoidance of sillyness so should the
    ligatures in stiff, filter, fluid, affirm, afflict,
    and adrift.

    normal-hyphen, non-breaking hyphen,
    figure-dash, en-dash, em-dash,
    horizontal-bar.""")


def test_that_ligatures_and_ambiguous_punctuation_are_normalised():
    frame = cv2.imread('tests/ocr/ambig.png')
    text = stbt.ocr(frame)
    text = text.replace("horizonta|", "horizontal")  # for tesseract < 3.03
    assert ligature_text == text
    assert stbt.match_text("em-dash,", frame)
    assert stbt.match_text(u"em\u2014dash,", frame)


def test_that_match_text_accepts_unicode():
    f = cv2.imread("tests/ocr/unicode.png")
    assert stbt.match_text("David", f, lang='eng+deu')  # ascii
    assert stbt.match_text(u"Röthlisberger", f, lang='eng+deu')  # unicode
    assert stbt.match_text("Röthlisberger", f, lang='eng+deu')  # utf-8 bytes


def test_that_setting_config_options_has_an_effect():
    # Unfortunately there are many tesseract config options and they are very
    # complicated so it's difficult to write a test that tests that a config
    # option is having the correct effect.  Due to the difficulty in determining
    # "correctness" instead here we test that setting a config option has an
    # effect at all.  This at least excercises our code which sets config
    # options.  I'm not happy about this and I hope to be able to replace this
    # once we have more experience with these settings in the real world.
    from _stbt.core import _tesseract_version
    if _tesseract_version() >= distutils.version.LooseVersion('3.04'):
        hocr_mode_config = {
            "tessedit_create_txt": 0,
            "tessedit_create_hocr": 1}
    else:
        hocr_mode_config = {
            "tessedit_create_hocr": 1}

    assert (stbt.ocr(frame=cv2.imread('tests/ocr/ambig.png'),
                     tesseract_config=hocr_mode_config) !=
            stbt.ocr(frame=cv2.imread('tests/ocr/ambig.png')))


def test_that_passing_patterns_helps_reading_serial_codes():
    # Test that this test is valid (e.g. tesseract will read it wrong without
    # help):
    assert u'UJJM2LGE' != stbt.ocr(
        frame=cv2.imread('tests/ocr/UJJM2LGE.png'),
        mode=stbt.OcrMode.SINGLE_WORD)

    # pylint: disable=W0212
    if _stbt.core._tesseract_version() < distutils.version.LooseVersion('3.03'):
        raise SkipTest('tesseract is too old')

    # Now the real test:
    assert u'UJJM2LGE' == stbt.ocr(
        frame=cv2.imread('tests/ocr/UJJM2LGE.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        tesseract_user_patterns=[r'\n\n\n\n\n\n\n\n'])


@raises(RuntimeError)
def test_that_with_old_tesseract_ocr_raises_an_exception_with_patterns():
    # pylint: disable=W0212
    if (_stbt.core._tesseract_version() >=
            distutils.version.LooseVersion('3.03')):
        raise SkipTest('tesseract is too new')

    stbt.ocr(
        frame=cv2.imread('tests/ocr/UJJM2LGE.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        tesseract_user_patterns=[r'\n\n\n\n\n\n\n\n'])


def test_user_dictionary_with_non_english_language():
    assert u'UJJM2LGE' == stbt.ocr(
        frame=cv2.imread('tests/ocr/UJJM2LGE.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        lang="deu",
        tesseract_user_words=[u'UJJM2LGE'])

# Menu as listed in menu.svg:
menu = [
    [
        u"Onion Bhaji",
        u"Mozzarella Pasta\nBake",
        u"Lamb and Date\nCasserole",
        u"Jerk Chicken"
    ], [
        u"Beef Wellington",
        u"Kerala Prawn Curry",
        u"Chocolate Fudge Cake",
        u"Halloumi Stuffed\nPeppers"
    ]
]


def iterate_menu():
    for x in range(4):
        for y in range(2):
            text = menu[y][x]
            yield (
                text,
                stbt.Region((1 + 8 * x) * 40, (3 + 7 * y) * 40, 6 * 40, 2 * 40),
                '\n' in text)


def test_that_text_location_is_recognised():
    frame = cv2.imread("tests/ocr/menu.png")

    def test(text, region):
        result = stbt.match_text(text, frame=frame)
        assert result
        assert region.contains(result.region)  # pylint: disable=E1101

    for text, region, multiline in iterate_menu():
        # Don't currently support multi-line comments
        if multiline:
            continue

        yield (test, text, region)


def test_match_text_stringify_result():
    frame = cv2.imread("tests/ocr/menu.png")
    result = stbt.match_text(u"Onion Bhaji", frame=frame)

    assert re.match(
        r"TextMatchResult\(time=None, match=True, region=Region\(.*\), "
        r"frame=<1280x720x3>, text=u'Onion Bhaji'\)",
        str(result))


def test_that_text_region_is_correct_even_with_regions_larger_than_frame():
    frame = cv2.imread("tests/ocr/menu.png")
    text, region, _ = list(iterate_menu())[6]
    result = stbt.match_text(
        text, frame=frame, region=region.extend(right=+12800))
    assert result
    assert region.contains(result.region)


@pytest.mark.parametrize("region", [
    stbt.Region(1280, 0, 1280, 720),
    None,
])
def test_that_match_text_still_returns_if_region_doesnt_intersect_with_frame(
        region):
    frame = cv2.imread("tests/ocr/menu.png")
    result = stbt.match_text("Onion Bhaji", frame=frame, region=region)
    assert result.match is False
    assert result.region is None
    assert result.text == "Onion Bhaji"


@pytest.mark.parametrize("region", [
    stbt.Region(1280, 0, 1280, 720),
    # None,  # uncomment when region=None doesn't raise -- see #433
])
def test_that_ocr_still_returns_if_region_doesnt_intersect_with_frame(region):
    frame = cv2.imread("tests/ocr/menu.png")
    result = stbt.ocr(frame=frame, region=region)
    assert result == u''


def test_that_match_text_returns_no_match_for_non_matching_text():
    frame = cv2.imread("tests/ocr/menu.png")
    assert not stbt.match_text(u"Noodle Soup", frame=frame)


def test_that_match_text_gives_tesseract_a_hint():
    frame = cv2.imread("tests/ocr/itv-player.png")
    if "ITV Player" in stbt.ocr(frame=frame):
        raise SkipTest("Tesseract doesn't need a hint")
    if "ITV Player" not in stbt.ocr(frame=frame, tesseract_user_words=["ITV"]):
        raise SkipTest("Giving tesseract a hint doesn't help")
    assert stbt.match_text("ITV Player", frame=frame)


def test_match_text_on_single_channel_image():
    frame = cv2.imread("tests/ocr/menu.png", cv2.IMREAD_GRAYSCALE)
    assert stbt.match_text("Onion Bhaji", frame)


def test_match_text_case_sensitivity():
    frame = cv2.imread("tests/ocr/menu.png", cv2.IMREAD_GRAYSCALE)
    assert stbt.match_text("ONION BHAJI", frame)
    assert stbt.match_text("ONION BHAJI", frame, case_sensitive=False)
    assert not stbt.match_text("ONION BHAJI", frame, case_sensitive=True)


def test_ocr_on_text_next_to_image_match():
    frame = cv2.imread("tests/action-panel.png")
    m = stbt.match("tests/action-panel-blue-button.png", frame)
    assert "YOUVIEW MENU" == stbt.ocr(frame,
                                      region=m.region.right_of(width=150))


@pytest.mark.parametrize("image,color,expected,region", [
    # This region has a selected "Summary" button (white on light blue) and
    # unselected buttons "Details" and "More Episodes" (light grey on black).
    # Without specifying text_color, OCR only sees the latter two.
    # Testing without specifying a region would also work, but with a small
    # region the test runs much faster (0.1s instead of 3s per ocr call).
    ("tests/action-panel.png", (235, 235, 235), "Summary",
     stbt.Region(0, 370, right=1280, bottom=410)),

    # This is a light "8" on a dark background. Without the context of any
    # other surrounding text, OCR reads it as ":" or ";"! Presumably tesseract
    # is reading the *holes* in the "8" instead of the letter itself, because
    # it's assuming that it's seeing printed matter (a scanned book with black
    # text on white background). Expanding the region to include other text
    # would solve the problem, but so does specifying the text color.
    ("tests/ocr/ch8.png", (252, 242, 255), "8", stbt.Region.ALL),
])
def test_ocr_text_color(image, color, expected, region):
    frame = cv2.imread(image)
    mode = stbt.OcrMode.SINGLE_LINE

    assert expected not in stbt.ocr(frame, region, mode)
    assert expected == stbt.ocr(frame, region, mode, text_color=color)

    assert not stbt.match_text(expected, frame, region, mode)
    assert stbt.match_text(expected, frame, region, mode, text_color=color)
