import os
import re
import timeit
from contextlib import contextmanager
from textwrap import dedent
from unittest import SkipTest

import pytest

import _stbt.config
import stbt_core as stbt
from _stbt import imgproc_cache
from _stbt.imgutils import load_image
from _stbt.ocr import _tesseract_version, Replacements
from _stbt.types import Region
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
    ("UJJM--white-text-on-gray-boxes.png", "", stbt.Region.ALL, None),
    ("UJJM--white-text-on-gray-boxes.png", "UJJM", stbt.Region.ALL, stbt.OcrMode.SINGLE_LINE),
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
    assert '£500\nDavid Röthlisberger' == text


@requires_tesseract
def test_that_ocr_can_read_small_text():
    text = stbt.ocr(frame=load_image('ocr/small.png'))
    assert 'Small anti-aliased text is hard to read\nunless you magnify' == \
        text


ligature_text = dedent("""\
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
    assert stbt.match_text("em\u2014dash,", frame)


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
    assert not stbt.match_text("Röthlisberger", f)  # reads Réthlisberger
    with temporary_config({"ocr.lang": "deu"}):
        assert stbt.match_text("Röthlisberger", f)
        assert "Röthlisberger" in stbt.ocr(f)


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
    if _tesseract_version() >= [3, 4]:
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
    if _tesseract_version() < [3, 3]:
        raise SkipTest('tesseract is too old')

    # Now the real test:
    assert '192.168.10.1' == stbt.ocr(
        frame=load_image('ocr/192.168.10.1.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        tesseract_user_patterns=patterns)


@requires_tesseract
def test_char_whitelist():
    # Without char_whitelist tesseract reads "OO" (the letter oh).
    assert '00' == stbt.ocr(
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
    # Plain strings match entire words at word boundaries, regexes don't:
    [('itv+', {'itv+': 'Apple tv+'}, 'Apple tv+'),
     ('hitv+', {'itv+': 'Apple tv+'}, 'hitv+'),
     ('This is itv+ innit', {'itv+': 'Apple tv+'}, 'This is Apple tv+ innit'),
     ('the saw said he saws, he saw.',
      {'he saw': 'HE SAW', re.compile("he", re.IGNORECASE): "ħé"},
      'tħé saw said ħé saws, ħé SAW.'),
     (r'T\/ & REPLAY', {r'T\/': 'TV'}, 'TV & REPLAY'),
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
    '192.168.10.1',
])
def test_user_dictionary_with_non_english_language(words):
    assert '192.168.10.1' == stbt.ocr(
        frame=load_image('ocr/192.168.10.1.png'),
        mode=stbt.OcrMode.SINGLE_WORD,
        lang="deu",
        tesseract_user_words=words)

# Menu as listed in menu.svg:
menu = [
    [
        "Onion Bhaji",
        "Mozzarella Pasta\nBake",
        "Lamb and Date\nCasserole",
        "Jerk Chicken"
    ], [
        "Beef Wellington",
        "Kerala Prawn Curry",
        "Chocolate Fudge Cake",
        "Halloumi Stuffed\nPeppers"
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
        assert region.contains(result.region)

    for text, region, multiline in iterate_menu():
        # Don't currently support multi-line comments
        if multiline:
            continue

        test(text, region, True)
        test(text, region, False)


@requires_tesseract
def test_upsample_default_value():
    image = load_image("ocr/Operacja Napoleon.png")

    # reads "Operacio Napoleon"
    assert stbt.ocr(frame=image, lang="pol") != "Operacja Napoleon"
    assert not stbt.match_text("Operacja Napoleon", frame=image, lang="pol")

    assert stbt.ocr(frame=image, lang="pol", upsample=False) == \
        "Operacja Napoleon"
    assert stbt.match_text("Operacja Napoleon", frame=image, lang="pol",
                           upsample=False)

    with temporary_config({"ocr.upsample": "False"}):
        assert stbt.ocr(frame=image, lang="pol") == "Operacja Napoleon"
        assert stbt.match_text("Operacja Napoleon", frame=image, lang="pol")


@requires_tesseract
def test_match_text_stringify_result(test_pack_root):  # pylint:disable=unused-argument
    frame = load_image("ocr/menu.png")
    result = stbt.match_text("Onion Bhaji", frame=frame)

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
    assert not stbt.match_text("Noodle Soup", frame=frame)


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
@pytest.mark.parametrize("image,color,expected", [
    # This region has a selected "Summary" button (white on light blue) and
    # unselected buttons "Details" and "More Episodes" (light gray on black).
    # Without specifying text_color, OCR only sees the latter two.
    ("ocr/Summary.png", (235, 235, 235), "Summary"),
    ("ocr/Summary.png", "#ebebeb", "Summary"),

    # This is a light "8" on a dark background. Without the context of any
    # other surrounding text, OCR reads it as ":" or ";"! Presumably tesseract
    # is reading the *holes* in the "8" instead of the letter itself, because
    # it's assuming that it's seeing printed matter (a scanned book with black
    # text on white background). Expanding the region to include other text
    # would solve the problem, but so does specifying the text color.
    ("ocr/ch8.png", (252, 242, 255), "8"),
])
def test_ocr_text_color(image, color, expected):
    frame = load_image(image)
    mode = stbt.OcrMode.SINGLE_LINE

    assert expected not in stbt.ocr(frame, mode=mode)
    assert expected == stbt.ocr(frame, mode=mode, text_color=color)

    assert not stbt.match_text(expected, frame, mode=mode)
    assert stbt.match_text(expected, frame, mode=mode, text_color=color)


@requires_tesseract
def test_ocr_text_color_threshold():
    f = load_image("ocr/Crunchyroll.png")
    c = "#ffffff"
    m = stbt.OcrMode.SINGLE_LINE

    # Without text_color, the left & right corners of the drop-shadow are
    # read as junk (often "L ... J" but here ". Crunchyroll A").
    assert stbt.ocr(f, mode=m) != "Crunchyroll"

    # Our default threshold causes far too thin letters; tesseract reads
    # "Cerchyroll".
    assert stbt.ocr(f, mode=m, text_color=c) != "Crunchyroll"

    assert stbt.ocr(f, mode=m, text_color=c, text_color_threshold=50) \
        == "Crunchyroll"
    with temporary_config({'ocr.text_color_threshold': '50'}):
        assert stbt.ocr(f, mode=m, text_color=c) == "Crunchyroll"


@requires_tesseract
@pytest.mark.parametrize("image,region,color,threshold,expected", [
    # pylint:disable=line-too-long
    ("images/appletv/BBC iPlayer.png", Region(x=635, y=354, right=843, bottom=389), "#ffffff", 50, "BBC iPIayer"),
    ("images/appletv/BT Sport.png", Region(x=236, y=267, right=448, bottom=302), "#ffffff", 50, "BT Sport"),
    ("images/appletv/Crunchyroll.png", Region(x=835, y=441, right=1041, bottom=476), "#ffffff", 50, "Crunchyroll"),
    ("images/appletv/YouTube.png", Region(x=42, y=235, right=245, bottom=270), "#ffffff", 50, "YouTube"),
])
def test_ocr_text_color_threshold_2(image, region, color, threshold, expected):
    f = stbt.load_image(image)
    assert stbt.ocr(f, region=region, text_color=color,
                    text_color_threshold=threshold) == expected


@requires_tesseract
def test_that_ocr_engine_has_an_effect():
    if _tesseract_version() < [4, 0]:
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


@pytest.mark.parametrize("a", [
    "hello",
    "he110",
])
@pytest.mark.parametrize("b", [
    "hello",
    "he110",
    "hel 10",
])
def test_ocr_eq_should_match(a, b):
    assert stbt.ocr_eq(a, b)
    assert stbt.ocr_eq(b, a)  # pylint:disable=arguments-out-of-order


@pytest.mark.parametrize("a,b", [
    ("hello", "hell"),
    ("hello", "helloo"),
    ("hello", "HELLO"),
    ("hello", ""),
    ("hello", "goodbye"),
    ("", "hello"),
])
def test_ocr_eq_shouldnt_match(a, b):
    assert not stbt.ocr_eq(a, b)
    assert not stbt.ocr_eq(b, a)  # pylint:disable=arguments-out-of-order


def test_ocr_eq_shouldnt_match_other_entries_from_real_world_menus():
    items = {
        "Add channels",
        "Angry Birds Space",
        "App Store",
        "App version",
        "Arcade",
        "Auto-play",
        "BBC iPlayer",
        "BT Sport",
        "CBS News",
        "Channel 4",
        "Clear search history",
        "Clear watch history",
        "Computers",
        "Credits",
        "Crunchyroll",
        "DAZN",
        "Disney Plus",
        "Disney+",
        "ESPN",
        "Fitness",
        "Gaming",
        "Get YouTube Premium",
        "hayu",
        "Hello World (dev)",
        "Help",
        "Home",
        "ITVX",
        "Language",
        "Library",
        "Link with TV code",
        "Link with Wi-Fi",
        "Linked devices",
        "Location",
        "Log in",
        "Log out",
        "MLB",
        "More",
        "Movies & TV",
        "Movies",
        "MUBI",
        "Music",
        "My5",
        "NBA",
        "Netflix",
        "NOW TV",
        "NOW",
        "Photos",
        "Pluto TV - It's Free TV",
        "Pluto TV",
        "Podcasts",
        "Previews",
        "Prime Video",
        "Privacy and Terms",
        "Purchases and memberships",
        "Rakuten TV",
        "Red Bull TV",
        "Reset app",
        "Restricted mode",
        "Roku Quick Tips",
        "Search",
        "Send feedback",
        "Settings",
        "Sign in",
        "Sign out",
        "Sky News",
        "STV Player",
        "Subscriptions",
        "TV off",
        "TV Shows",
        "TV",
        "YouTube",
        "YuppTV - Live, CatchUp, Movies",
    }
    for item in items:
        others = items - {item}
        for other in others:
            assert not stbt.ocr_eq(item, other)
            assert not stbt.ocr_eq(other, item)


@contextmanager
def temporary_ocr_eq_replacements():
    orig = stbt.ocr_eq.replacements.copy()
    try:
        yield
    finally:
        stbt.ocr_eq.replacements = orig.copy()


def test_ocr_eq_replacements():
    assert stbt.ocr_eq("hello", "hel 10")
    assert stbt.ocr_eq.normalize("hel 10") == "hello"
    with temporary_ocr_eq_replacements():
        stbt.ocr_eq.replacements = {"1": "l"}
        assert stbt.ocr_eq("hello", "he11o")
        assert not stbt.ocr_eq("hello", "hel 10")
        assert stbt.ocr_eq.normalize("hel 10") == "hell0"

    with temporary_ocr_eq_replacements():
        # "I" is already normalized to "l"
        stbt.ocr_eq.replacements["İ"] = "I"
        assert stbt.ocr_eq("İ", "I")

    with temporary_ocr_eq_replacements():
        # The order we specify these replacements won't ultimately matter:
        stbt.ocr_eq.replacements = Replacements({"İ": "I"})
        stbt.ocr_eq.replacements["I"] = "l"
        assert stbt.ocr_eq("İ", "I")

    with temporary_ocr_eq_replacements():
        # Changing something that had already been changed due to earlier
        # normalisations is safe, because the `replacements` dict is iterated
        # in insertion order:
        stbt.ocr_eq.replacements["l"] = "*"
        assert stbt.ocr_eq("hello", "he11o")
        assert stbt.ocr_eq("hello", "he**o")
        assert stbt.ocr_eq("he11o", "he**o")

    assert stbt.ocr_eq("Movies & TV", "Movies 8. TV")  # YouTube menu
    assert stbt.ocr_eq("BT Sport", "8T Sport")  # Apple TV
    assert stbt.ocr_eq("Music", "Music:")  # Apple TV
    assert stbt.ocr_eq("App version", "App vefslon")  # YouTube settings menu
    assert stbt.ocr_eq("YuppTV - Live, CatchUp, Movies",
                       "YuppTV - Live, CatchUp. Movies")  # Roku
