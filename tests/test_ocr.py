# coding: utf-8

import distutils
import re
import time
from textwrap import dedent

import cv2
from nose.plugins.skip import SkipTest
from nose.tools import eq_, raises

import _stbt.core
import stbt


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
    eq_(u'UJJM2LGE', stbt.ocr(
        frame=cv2.imread('tests/ocr/UJJM2LGE.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        tesseract_user_patterns=[r'\n\n\n\n\n\n\n\n']))


@raises(RuntimeError)
def test_that_with_old_tesseract_ocr_raises_an_exception_with_patterns():
    # pylint: disable=W0212
    if (_stbt.core._tesseract_version()
            >= distutils.version.LooseVersion('3.03')):
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


def test_that_match_text_gives_tesseract_a_hint():
    frame = cv2.imread("tests/ocr/itv-player.png")
    if "ITV Player" in stbt.ocr(frame=frame):
        raise SkipTest("Tesseract doesn't need a hint")
    if "ITV Player" not in stbt.ocr(frame=frame, tesseract_user_words=["ITV"]):
        raise SkipTest("Giving tesseract a hint doesn't help")
    assert stbt.match_text("ITV Player", frame=frame)


def test_that_ocr_and_match_text_are_memoised():
    def timeit(f, filename, region=stbt.Region.ALL,
               expect_already_memoized=False):
        frame1 = cv2.imread(filename)
        start1 = time.time()
        result1 = f(frame=frame1, region=region)
        end1 = time.time()

        frame2 = cv2.imread(filename)  # Same image, but different python object
        start2 = time.time()
        result2 = f(frame=frame2, region=region)
        end2 = time.time()

        assert result1 == result2
        elapsed1 = end1 - start1
        elapsed2 = end2 - start2
        print "Filename: %s; expect already memoized: %s" % (
            filename, expect_already_memoized)
        print "  first time: %fs; second time: %fs" % (elapsed1, elapsed2)
        if expect_already_memoized:
            assert elapsed1 < 10 * elapsed2
        else:
            assert elapsed1 > 10 * elapsed2

        return result1

    def test(f):
        timeit(f, "tests/ocr/dialog-great--world-peace.png")

        # Change the frame, but using a region where both frames have identical
        # content. This region contains the dialog (which says "This set-top
        # box is great" in both frames) but it doesn't contain the background
        # (which varies: "BREAKING NEWS: World Peace" vs "BREAKING NEWS: Free
        # bunnies").
        r1 = stbt.Region(x=350, y=190, right=950, bottom=510)
        text1 = timeit(f, "tests/ocr/dialog-great--world-peace.png", r1)
        text2 = timeit(f, "tests/ocr/dialog-great--free-bunnies.png", r1, True)
        assert text1 == text2

        # Change the frame
        text3 = timeit(f, "tests/ocr/dialog-fabulous--world-peace.png", r1)
        assert text3 != text1

        # Change the region
        r2 = stbt.Region(x=0, y=640, right=1280, bottom=720)
        timeit(f, "tests/ocr/dialog-fabulous--world-peace.png", r2)

    def match_text(**kwargs):
        return stbt.match_text("fabulous", **kwargs).match

    yield test, stbt.ocr
    yield test, match_text
