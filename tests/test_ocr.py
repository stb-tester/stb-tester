# coding: utf-8

import os
import re
import timeit
from contextlib import contextmanager
from distutils.version import LooseVersion
from textwrap import dedent
from unittest import SkipTest

import pytest

import _stbt.config
import stbt_core as stbt
from _stbt import imgproc_cache
from _stbt.imgutils import load_image
from _stbt.ocr import _tesseract_version
from _stbt.utils import named_temporary_directory


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


@requires_tesseract
@pytest.mark.parametrize("region", [
    None,
    stbt.Region(1280, 0, 1280, 720),
])
def test_that_ocr_region_none_isnt_allowed(region):
    f = load_image("ocr/small.png")
    with pytest.raises((TypeError, ValueError)):
        stbt.ocr(frame=f, region=region)
    with pytest.raises((TypeError, ValueError)):
        stbt.match_text("Small", frame=f, region=region)


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
            _stbt.config._config_init(force=True)


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


corrections_test_cases = [
    # pylint:disable=bad-whitespace
    # Default ocr output:
    (None,                                           'OO'),
    # Corrections string must match entire word:
    ({'O': '0'},                                     'OO'),
    ({'OO': '00'},                                   '00'),
    # Strings are case-sensitive, and they aren't regexes:
    ({'oo': '00', '[oO]': '0'},                      'OO'),
    # Regexes do match anywhere:
    ({re.compile('[oO]'): '0'},                      '00'),
    # Make sure it tries all the patterns:
    ({'AA': 'BB', 'OO': '00'},                       '00'),
    ({re.compile('^O'): '1', re.compile('O$'): '2'}, '12'),
]


@requires_tesseract
@pytest.mark.parametrize("corrections,expected", corrections_test_cases)
def test_corrections(corrections, expected):
    f = load_image('ocr/00.png')
    print(corrections)
    assert expected == stbt.ocr(frame=f, mode=stbt.OcrMode.SINGLE_WORD,
                                corrections=corrections)

    try:
        stbt.set_global_ocr_corrections({'OO': '11'})
        if expected == "OO":
            expected = "11"
        assert expected == stbt.ocr(frame=f, mode=stbt.OcrMode.SINGLE_WORD,
                                    corrections=corrections)
    finally:
        stbt.set_global_ocr_corrections({})


@pytest.mark.parametrize(
    "text,corrections,expected",
    # Same test-cases as `test_corrections` above:
    [('OO', c, e) for (c, e) in corrections_test_cases] +
    # Plain strings match entire words at word boundaries:
    [('itv+', {'itv+': 'Apple tv+'}, 'Apple tv+'),
     ('hitv+', {'itv+': 'Apple tv+'}, 'hitv+'),
     ('This is itv+ innit', {'itv+': 'Apple tv+'}, 'This is Apple tv+ innit'),
     # Make sure it tries all the patterns:
     ('A B C', {'A': '1', 'B': '2', 'C': '3'}, '1 2 3'),
    ])
def test_apply_ocr_corrections(text, corrections, expected):
    assert expected == stbt.apply_ocr_corrections(text, corrections)


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

        test(text, region, True)
        test(text, region, False)


@requires_tesseract
def test_match_text_stringify_result():
    stbt.TEST_PACK_ROOT = os.path.abspath(os.path.dirname(__file__))

    frame = load_image("ocr/menu.png")
    result = stbt.match_text(u"Onion Bhaji", frame=frame)

    assert re.match(
        r"TextMatchResult\(time=None, match=True, region=Region\(.*\), "
        r"frame=<Image\(filename=u?'ocr/menu.png', "
        r"dimensions=1280x720x3\)>, text=u?'Onion Bhaji'\)",
        str(result))


@requires_tesseract
def test_that_text_region_is_correct_even_with_regions_larger_than_frame():
    frame = load_image("ocr/menu.png")
    text, region, _ = list(iterate_menu())[6]
    result = stbt.match_text(
        text, frame=frame, region=region.extend(right=+12800))
    assert result
    assert region.contains(result.region)


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
    frame = load_image("ocr/menu.png", color_channels=1)
    assert stbt.match_text("Onion Bhaji", frame)


@requires_tesseract
def test_match_text_case_sensitivity():
    frame = load_image("ocr/menu.png", color_channels=1)
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
@pytest.mark.parametrize("image,color,threshold,expected", [
    # This region has a selected "Summary" button (white on light blue) and
    # unselected buttons "Details" and "More Episodes" (light grey on black).
    # Without specifying text_color, OCR only sees the latter two.
    ("ocr/Summary.png", (235, 235, 235), 25, "Summary"),

    # This is a light "8" on a dark background. Without the context of any
    # other surrounding text, OCR reads it as ":" or ";"! Presumably tesseract
    # is reading the *holes* in the "8" instead of the letter itself, because
    # it's assuming that it's seeing printed matter (a scanned book with black
    # text on white background). Expanding the region to include other text
    # would solve the problem, but so does specifying the text color.
    ("ocr/ch8.png", (252, 242, 255), 25, "8"),

    # This has some very faint pixels around the letters, and Tesseract's
    # binarisation algorithm thinks they are foreground pixels. Without
    # text_color tesseract reads "3115051495 HD".
    ("ocr/Buy 14.99 HD.png", (195, 125, 0), None, "Buy $14.99 HD"),
])
def test_ocr_text_color(image, color, threshold, expected):
    frame = load_image(image)
    mode = stbt.OcrMode.SINGLE_LINE

    assert expected not in stbt.ocr(frame, mode=mode)
    assert expected == stbt.ocr(frame, mode=mode, text_color=color,
                                text_color_threshold=threshold)

    assert not stbt.match_text(expected, frame, mode=mode)
    assert stbt.match_text(expected, frame, mode=mode, text_color=color,
                           text_color_threshold=threshold)


@requires_tesseract
def test_ocr_text_color_threshold():
    f = load_image("ocr/Explore Apple Originals.png")
    c = (255, 255, 255)
    expected = "Explore Apple Originals"
    assert stbt.ocr(f, text_color=c, text_color_threshold=25) == \
        "Explore Apple Originalg"
    with temporary_config({'ocr.text_color_threshold': '25'}):
        assert stbt.ocr(f, text_color=c) == "Explore Apple Originalg"
    assert stbt.ocr(f, text_color=c, text_color_threshold=None) == expected
    assert stbt.ocr(f, text_color=c) == expected


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


@requires_tesseract
def test_that_cache_speeds_up_ocr():
    with named_temporary_directory() as tmpdir, \
            imgproc_cache.setup_cache(tmpdir):
        _test_that_cache_speeds_up_ocr()


# This one is also run from integration tests:
def _test_that_cache_speeds_up_ocr():
    frame = load_image('red-black.png')

    def ocr():
        return stbt.ocr(frame=frame)

    _cache = imgproc_cache._cache
    imgproc_cache._cache = None
    uncached_result = ocr()
    uncached_time = min(timeit.repeat(ocr, repeat=10, number=1))
    imgproc_cache._cache = _cache

    cached_result = ocr()  # prime the cache
    cached_time = min(timeit.repeat(ocr, repeat=10, number=1))

    print("ocr with cache: %s" % (cached_time,))
    print("ocr without cache: %s" % (uncached_time,))
    assert uncached_time > (cached_time * 10)
    assert type(cached_result) == type(uncached_result)  # pylint:disable=unidiomatic-typecheck
    assert cached_result == uncached_result

    r = stbt.Region(x=0, y=32, right=91, bottom=59)
    frame2 = load_image("red-black-2.png")

    def cached_ocr1():
        return stbt.ocr(frame=frame, region=r)

    def cached_ocr2():
        return stbt.ocr(frame=frame2, region=r)

    cached_ocr1()  # prime the cache
    time1 = timeit.timeit(cached_ocr1, number=1)
    time2 = timeit.timeit(cached_ocr2, number=1)

    print("ocr with cache (frame 1): %s" % (time1,))
    print("ocr with cache (frame 2): %s" % (time2,))
    assert time2 < (time1 * 10)
    assert cached_ocr1() == cached_ocr2()
