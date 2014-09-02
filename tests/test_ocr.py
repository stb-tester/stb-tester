# coding: utf-8

import codecs
import distutils
import re
import sys
from textwrap import dedent

import cv2
from nose.plugins.skip import SkipTest
from nose.tools import eq_, raises

import stbt

sys.stdout = codecs.getwriter('utf8')(sys.stdout)


def test_that_ocr_returns_unicode():
    text = stbt.ocr(frame=cv2.imread('tests/ocr/unicode.png'))
    assert isinstance(text, unicode)


def test_that_ocr_reads_unicode():
    text = stbt.ocr(frame=cv2.imread('tests/ocr/unicode.png'), lang='eng+deu')
    eq_(u'£500\nRöthlisberger', text)


def test_that_ocr_can_read_small_text():
    text = stbt.ocr(frame=cv2.imread('tests/ocr/small.png'))
    eq_(u'Small anti-aliased text is hard to read\nunless you magnify', text)


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
    text = stbt.ocr(frame=cv2.imread('tests/ocr/ambig.png'))
    text = text.replace("horizonta|", "horizontal")  # for tesseract < 3.03
    eq_(ligature_text, text)


def test_that_setting_config_options_has_an_effect():
    # Unfortunately there are many tesseract config options and they are very
    # complicated so it's difficult to write a test that tests that a config
    # option is having the correct effect.  Due to the difficulty in determining
    # "correctness" instead here we test that setting a config option has an
    # effect at all.  This at least excercises our code which sets config
    # options.  I'm not happy about this and I hope to be able to replace this
    # once we have more experience with these settings in the real world.
    assert (stbt.ocr(frame=cv2.imread('tests/ocr/ambig.png'),
                     tesseract_config={"tessedit_create_hocr": 1}) !=
            stbt.ocr(frame=cv2.imread('tests/ocr/ambig.png')))


def test_that_passing_patterns_helps_reading_serial_codes():
    # Test that this test is valid (e.g. tesseract will read it wrong without
    # help):
    assert u'UJJM2LGE' != stbt.ocr(
        frame=cv2.imread('tests/ocr/UJJM2LGE.png'),
        mode=stbt.OcrMode.SINGLE_WORD)

    # pylint: disable=W0212
    if stbt.core._tesseract_version() < distutils.version.LooseVersion('3.03'):
        raise SkipTest('tesseract is too old')

    # Now the real test:
    eq_(u'UJJM2LGE', stbt.ocr(
        frame=cv2.imread('tests/ocr/UJJM2LGE.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        tesseract_user_patterns=[r'\n\n\n\n\n\n\n\n']))


@raises(RuntimeError)
def test_that_with_old_tesseract_ocr_raises_an_exception_with_patterns():
    # pylint: disable=W0212
    if stbt.core._tesseract_version() >= distutils.version.LooseVersion('3.03'):
        raise SkipTest('tesseract is too new')

    stbt.ocr(
        frame=cv2.imread('tests/ocr/UJJM2LGE.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        tesseract_user_patterns=[r'\n\n\n\n\n\n\n\n'])


def test_user_dictionary_with_non_english_language():
    eq_(u'UJJM2LGE', stbt.ocr(
        frame=cv2.imread('tests/ocr/UJJM2LGE.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        lang="deu",
        tesseract_user_words=[u'UJJM2LGE']))

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
        r"TextMatchResult\(timestamp=None, match=True, region=Region\(.*\), "
        r"frame=1280x720x3, text=u'Onion Bhaji'\)", str(result))


def test_that_text_region_is_correct_even_with_regions_larger_than_frame():
    frame = cv2.imread("tests/ocr/menu.png")
    text, region, _ = list(iterate_menu())[6]
    result = stbt.match_text(
        text, frame=frame, region=region.extend(right=+12800))
    assert result
    assert region.contains(result.region)


def test_that_match_text_still_returns_if_region_doesnt_intersect_with_frame():
    frame = cv2.imread("tests/ocr/menu.png")
    result = stbt.match_text("Onion Bhaji", frame=frame,
                             region=stbt.Region(1280, 0, 1280, 720))
    assert result.match is False
    assert result.region is None
    assert result.text == "Onion Bhaji"


def test_that_ocr_still_returns_if_region_doesnt_intersect_with_frame():
    frame = cv2.imread("tests/ocr/menu.png")
    result = stbt.ocr(frame=frame, region=stbt.Region(1280, 0, 1280, 720))
    assert result == u''


def test_that_match_text_returns_no_match_for_non_matching_text():
    frame = cv2.imread("tests/ocr/menu.png")
    assert not stbt.match_text(u"Noodle Soup", frame=frame)
