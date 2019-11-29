# coding: utf-8

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order
import os
import re
from contextlib import contextmanager
from distutils.version import LooseVersion
from textwrap import dedent
from unittest import SkipTest

import cv2
import pytest

import _stbt.config
import stbt
from _stbt.ocr import _tesseract_version
from _stbt.utils import named_temporary_directory, text_type
from stbt import load_image


def requires_tesseract(func):
    """Decorator for tests that require Tesseract to be installed."""
    try:
        _tesseract_version()
    except:
        raise SkipTest("tesseract isn't installed")
    return func


@requires_tesseract
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
    text = stbt.ocr(load_image("ocr/" + image), **kwargs)
    assert text == expected_text

    # Don't leak python future newtypes
    assert type(text).__name__ in ["unicode", "str"]


# Remove when region=None doesn't raise -- see #433
@requires_tesseract
def test_that_ocr_region_none_isnt_allowed():
    with pytest.raises(TypeError):
        stbt.ocr(frame=load_image("ocr/small.png"), region=None)


@requires_tesseract
def test_that_ocr_reads_unicode():
    text = stbt.ocr(frame=load_image('ocr/unicode.png'), lang='eng+deu')
    assert isinstance(text, str)
    assert u'£500\nDavid Röthlisberger' == text


@requires_tesseract
def test_that_ocr_can_read_small_text():
    text = stbt.ocr(frame=load_image('ocr/small.png'))
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


@requires_tesseract
def test_that_ligatures_and_ambiguous_punctuation_are_normalised():
    frame = load_image('ocr/ambig.png')
    text = stbt.ocr(frame)
    for bad, good in [
            # tesseract 3.02
            ("horizonta|", "horizontal"),
            # tesseract 4.00 with tessdata 590567f
            ("siIIyness", "sillyness"),
            ("Iigatures", "ligatures"),
    ]:
        text = text.replace(bad, good)
    assert ligature_text == text
    assert stbt.match_text("em-dash,", frame)
    assert stbt.match_text(u"em\u2014dash,", frame)


@requires_tesseract
def test_that_match_text_accepts_unicode():
    f = load_image("ocr/unicode.png")
    assert stbt.match_text("David", f, lang='eng+deu')  # ascii
    assert stbt.match_text("Röthlisberger", f, lang='eng+deu')  # unicode
    assert stbt.match_text(
        "Röthlisberger".encode('utf-8'), f, lang='eng+deu')  # utf-8 bytes


@requires_tesseract
def test_that_default_language_is_configurable():
    f = load_image("ocr/unicode.png")
    assert not stbt.match_text(u"Röthlisberger", f)  # reads Réthlisberger
    with temporary_config({"ocr.lang": "deu"}):
        assert stbt.match_text(u"Röthlisberger", f)
        assert u"Röthlisberger" in stbt.ocr(f)


@contextmanager
def temporary_config(config):
    with named_temporary_directory(prefix="stbt-test-ocr") as d:
        original_env = os.environ.get("STBT_CONFIG_FILE", "")
        os.environ["STBT_CONFIG_FILE"] = "%s/stbt.conf:%s" % (d, original_env)
        for key, value in config.items():
            section, option = key.split(".")
            _stbt.config.set_config(section, option, value)
        try:
            yield
        finally:
            os.environ["STBT_CONFIG_FILE"] = original_env
            _stbt.config._config_init(force=True)  # pylint:disable=protected-access


@requires_tesseract
def test_that_setting_config_options_has_an_effect():
    # Unfortunately there are many tesseract config options and they are very
    # complicated so it's difficult to write a test that tests that a config
    # option is having the correct effect.  Due to the difficulty in determining
    # "correctness" instead here we test that setting a config option has an
    # effect at all.  This at least excercises our code which sets config
    # options.  I'm not happy about this and I hope to be able to replace this
    # once we have more experience with these settings in the real world.
    if _tesseract_version() >= LooseVersion('3.04'):
        hocr_mode_config = {
            "tessedit_create_txt": 0,
            "tessedit_create_hocr": 1}
    else:
        hocr_mode_config = {
            "tessedit_create_hocr": 1}

    assert (stbt.ocr(frame=load_image('ocr/ambig.png'),
                     tesseract_config=hocr_mode_config) !=
            stbt.ocr(frame=load_image('ocr/ambig.png')))


@requires_tesseract
@pytest.mark.parametrize("patterns", [
    pytest.param(None, marks=pytest.mark.xfail),
    [r'\d\*.\d\*.\d\*.\d\*'],
    r'\d\*.\d\*.\d\*.\d\*',
])
def test_tesseract_user_patterns(patterns):
    # pylint:disable=protected-access
    if _tesseract_version() < LooseVersion('3.03'):
        raise SkipTest('tesseract is too old')

    # Now the real test:
    assert u'192.168.10.1' == stbt.ocr(
        frame=load_image('ocr/192.168.10.1.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        tesseract_user_patterns=patterns)


@requires_tesseract
def test_char_whitelist():
    # Without char_whitelist tesseract reads "OO" (the letter oh).
    assert u'00' == stbt.ocr(
        frame=load_image('ocr/00.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        char_whitelist="0123456789")


@requires_tesseract
@pytest.mark.parametrize("words", [
    pytest.param(None, marks=pytest.mark.xfail),
    ['192.168.10.1'],
    b'192.168.10.1',
    u'192.168.10.1',
])
def test_user_dictionary_with_non_english_language(words):
    assert u'192.168.10.1' == stbt.ocr(
        frame=load_image('ocr/192.168.10.1.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        lang="deu",
        tesseract_user_words=words)

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


@requires_tesseract
def test_that_text_location_is_recognised():
    frame = load_image("ocr/menu.png")

    def test(text, region, upsample):
        result = stbt.match_text(text, frame=frame, upsample=upsample)
        assert result
        assert region.contains(result.region)  # pylint:disable=no-member

    for text, region, multiline in iterate_menu():
        # Don't currently support multi-line comments
        if multiline:
            continue

        yield (test, text, region, True)
        yield (test, text, region, False)


@requires_tesseract
def test_match_text_stringify_result():
    frame = load_image("ocr/menu.png")
    result = stbt.match_text(u"Onion Bhaji", frame=frame)

    assert re.match(
        r"TextMatchResult\(time=None, match=True, region=Region\(.*\), "
        r"frame=<1280x720x3>, text=u?'Onion Bhaji'\)",
        text_type(result))


@requires_tesseract
def test_that_text_region_is_correct_even_with_regions_larger_than_frame():
    frame = load_image("ocr/menu.png")
    text, region, _ = list(iterate_menu())[6]
    result = stbt.match_text(
        text, frame=frame, region=region.extend(right=+12800))
    assert result
    assert region.contains(result.region)


@requires_tesseract
@pytest.mark.parametrize("region", [
    stbt.Region(1280, 0, 1280, 720),
    None,
])
def test_that_match_text_still_returns_if_region_doesnt_intersect_with_frame(
        region):
    frame = load_image("ocr/menu.png")
    result = stbt.match_text("Onion Bhaji", frame=frame, region=region)
    assert result.match is False
    assert result.region is None
    assert result.text == "Onion Bhaji"

    # Avoid future.types.newtypes in return values
    assert type(result.text).__name__ in ["str", "unicode"]


@requires_tesseract
@pytest.mark.parametrize("region", [
    stbt.Region(1280, 0, 1280, 720),
    # None,  # uncomment when region=None doesn't raise -- see #433
])
def test_that_ocr_still_returns_if_region_doesnt_intersect_with_frame(region):
    frame = load_image("ocr/menu.png")
    result = stbt.ocr(frame=frame, region=region)
    assert result == u''


@requires_tesseract
def test_that_match_text_returns_no_match_for_non_matching_text():
    frame = load_image("ocr/menu.png")
    assert not stbt.match_text(u"Noodle Soup", frame=frame)


@requires_tesseract
def test_that_match_text_gives_tesseract_a_hint():
    frame = load_image("ocr/itv-player.png")
    if "ITV Player" in stbt.ocr(frame=frame):
        raise SkipTest("Tesseract doesn't need a hint")
    if "ITV Player" not in stbt.ocr(frame=frame, tesseract_user_words=["ITV"]):
        raise SkipTest("Giving tesseract a hint doesn't help")
    assert stbt.match_text("ITV Player", frame=frame)


@requires_tesseract
def test_match_text_on_single_channel_image():
    frame = load_image("ocr/menu.png", cv2.IMREAD_GRAYSCALE)
    assert stbt.match_text("Onion Bhaji", frame)


@requires_tesseract
def test_match_text_case_sensitivity():
    frame = load_image("ocr/menu.png", cv2.IMREAD_GRAYSCALE)
    assert stbt.match_text("ONION BHAJI", frame)
    assert stbt.match_text("ONION BHAJI", frame, case_sensitive=False)
    assert not stbt.match_text("ONION BHAJI", frame, case_sensitive=True)


@requires_tesseract
def test_ocr_on_text_next_to_image_match():
    frame = load_image("action-panel.png")
    m = stbt.match("action-panel-blue-button.png", frame)
    assert "YOUVIEW MENU" == stbt.ocr(frame,
                                      region=m.region.right_of(width=150))


@requires_tesseract
@pytest.mark.parametrize("image,color,expected,region", [
    # This region has a selected "Summary" button (white on light blue) and
    # unselected buttons "Details" and "More Episodes" (light grey on black).
    # Without specifying text_color, OCR only sees the latter two.
    # Testing without specifying a region would also work, but with a small
    # region the test runs much faster (0.1s instead of 3s per ocr call).
    ("action-panel.png", (235, 235, 235), "Summary",
     stbt.Region(0, 370, right=1280, bottom=410)),

    # This is a light "8" on a dark background. Without the context of any
    # other surrounding text, OCR reads it as ":" or ";"! Presumably tesseract
    # is reading the *holes* in the "8" instead of the letter itself, because
    # it's assuming that it's seeing printed matter (a scanned book with black
    # text on white background). Expanding the region to include other text
    # would solve the problem, but so does specifying the text color.
    ("ocr/ch8.png", (252, 242, 255), "8", stbt.Region.ALL),
])
def test_ocr_text_color(image, color, expected, region):
    frame = load_image(image)
    mode = stbt.OcrMode.SINGLE_LINE

    assert expected not in stbt.ocr(frame, region, mode)
    assert expected == stbt.ocr(frame, region, mode, text_color=color)

    assert not stbt.match_text(expected, frame, region, mode)
    assert stbt.match_text(expected, frame, region, mode, text_color=color)


@requires_tesseract
def test_ocr_text_color_threshold():
    f = load_image("ocr/blue-search-white-guide.png")
    c = (220, 220, 220)
    assert stbt.ocr(f) != "Guide"
    # pylint:disable=fixme
    # TODO: Find an example where text_color_threshold is necessary. Since
    # tesseract 4.0.0 the default text_color_threshold actually works.
    # assert stbt.ocr(f, text_color=c) != "Guide"
    assert stbt.ocr(f, text_color=c, text_color_threshold=50) == "Guide"
    with temporary_config({'ocr.text_color_threshold': '50'}):
        assert stbt.ocr(f, text_color=c) == "Guide"


@requires_tesseract
def test_that_ocr_engine_has_an_effect():
    if _tesseract_version() < LooseVersion("4.0"):
        raise SkipTest('tesseract is too old')

    f = load_image("ocr/ambig.png")

    # This is a regression in tesseract 4.0's legacy engine, compared to 3.04:
    assert "sillyness" not in stbt.ocr(f, engine=stbt.OcrEngine.TESSERACT)
    assert "sillyness" not in stbt.ocr(f)

    # ...but the new LSTM engine does read it correctly:
    assert "sillyness" in stbt.ocr(f, engine=stbt.OcrEngine.LSTM)
    with temporary_config({'ocr.engine': 'LSTM'}):
        assert "sillyness" in stbt.ocr(f)
