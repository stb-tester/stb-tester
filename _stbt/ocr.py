from __future__ import annotations

import collections
import re
import typing
import unicodedata
from enum import IntEnum
from typing import Optional

import numpy

from .imgutils import (
    Color,
    ColorT,
    FrameT,
    _frame_repr,
    _validate_region,
)
from .logging import debug, draw_source_region, ImageLogger
from .types import Region

CorrectionsT = dict[re.Pattern | str, str]


# Tesseract sometimes has a hard job distinguishing certain glyphs such as
# ligatures and different forms of the same punctuation.  We strip out this
# superfluous information improving matching accuracy with minimal effect on
# meaning.  This means that stbt.ocr give much more consistent results.
_ocr_replacements = {
    # Ligatures
    'ﬀ': 'ff',
    'ﬁ': 'fi',
    'ﬂ': 'fl',
    'ﬃ': 'ffi',
    'ﬄ': 'ffl',
    'ﬅ': 'ft',
    'ﬆ': 'st',
    # Punctuation
    '“': '"',
    '”': '"',
    '‘': '\'',
    '’': '\'',
    # These are actually different glyphs!:
    '‐': '-',
    '‑': '-',
    '‒': '-',
    '–': '-',
    '—': '-',
    '―': '-',
}
_ocr_transtab = dict((ord(amb), to) for amb, to in _ocr_replacements.items())


class OcrMode(IntEnum):
    """Options to control layout analysis and assume a certain form of image.

    For a (brief) description of each option, see the `tesseract(1)
    <https://github.com/tesseract-ocr/tesseract/blob/3.04.01/doc/tesseract.1.asc#options>`__
    man page.
    """
    ORIENTATION_AND_SCRIPT_DETECTION_ONLY = 0
    PAGE_SEGMENTATION_WITH_OSD = 1
    PAGE_SEGMENTATION_WITHOUT_OSD_OR_OCR = 2
    PAGE_SEGMENTATION_WITHOUT_OSD = 3
    SINGLE_COLUMN_OF_TEXT_OF_VARIABLE_SIZES = 4
    SINGLE_UNIFORM_BLOCK_OF_VERTICALLY_ALIGNED_TEXT = 5
    SINGLE_UNIFORM_BLOCK_OF_TEXT = 6
    SINGLE_LINE = 7
    SINGLE_WORD = 8
    SINGLE_WORD_IN_A_CIRCLE = 9
    SINGLE_CHARACTER = 10
    SPARSE_TEXT = 11
    SPARSE_TEXT_WITH_OSD = 12
    RAW_LINE = 13

    # For nicer formatting of `ocr` signature in generated API documentation:
    def __repr__(self):
        return str(self)


class OcrEngine(IntEnum):

    #: Tesseract's "legacy" OCR engine (v3). Recommended.
    TESSERACT = 0

    #: Tesseract v4's "Long Short-Term Memory" neural network. Not recommended
    #: for reading menus, buttons, prices, numbers, times, etc, because it
    #: hallucinates text that isn't there when the input isn't long prose.
    LSTM = 1

    #: Combine results from Tesseract legacy & LSTM engines. Not recommended
    #: because it favours the result from the LSTM engine too heavily.
    TESSERACT_AND_LSTM = 2

    #: Default engine, based on what is installed.
    DEFAULT = 3

    def __repr__(self):
        return str(self)


class TextMatchResult():
    """The result from `match_text`.

    :ivar float time: The time at which the video-frame was captured, in
        seconds since 1970-01-01T00:00Z. This timestamp can be compared with
        system time (``time.time()``).

    :ivar bool match: True if a match was found. This is the same as evaluating
        ``MatchResult`` as a bool. That is, ``if result:`` will behave the same
        as ``if result.match:``.

    :ivar Region region: Bounding box where the text was found, or ``None`` if
        the text wasn't found.

    :ivar Frame frame: The video frame that was searched, as given to
        `match_text`.

    :ivar str text: The text that was searched for, as given to
        `match_text`.
    """
    _fields = ("time", "match", "region", "frame", "text")

    def __init__(self, time, match, region, frame, text):
        self.time: float | None = time
        self.match: bool = match
        self.region: Region = region
        self.frame: FrameT = frame
        self.text: str = text

    def __bool__(self):
        return self.match

    def __repr__(self):
        return (
            "TextMatchResult(time=%s, match=%r, region=%r, frame=%s, "
            "text=%r)" % (
                "None" if self.time is None else "%.3f" % self.time,
                self.match,
                self.region,
                _frame_repr(self.frame),
                self.text))


def ocr(
    frame: Optional[FrameT] = None,
    region: Region = Region.ALL,
    mode: OcrMode = OcrMode.PAGE_SEGMENTATION_WITHOUT_OSD,
    lang: Optional[str] = None,
    tesseract_config: Optional[typing.Mapping[str, bool | str | int]] = None,
    tesseract_user_words: Optional[list[str] | str] = None,
    tesseract_user_patterns: Optional[list[str] | str] = None,
    upsample: Optional[bool] = None,
    text_color: Optional[ColorT] = None,
    text_color_threshold: Optional[float] = None,
    engine: Optional[OcrEngine] = None,
    char_whitelist: Optional[str] = None,
    corrections: Optional[CorrectionsT] = None,
):
    r"""Return the text present in the video frame as a Unicode string.

    Perform OCR (Optical Character Recognition) using the "Tesseract"
    open-source OCR engine.

    :param Frame frame:
      If this is specified it is used as the video frame to process; otherwise
      a new frame is grabbed from the device-under-test.

    :param Region region:
      Only search within the specified region of the video frame.

    :param OcrMode mode: Tesseract's layout analysis mode.

    :param str lang:
        The three-letter
        `ISO-639-3 <http://www.loc.gov/standards/iso639-2/php/code_list.php>`__
        language code of the language you are attempting to read; for example
        "eng" for English or "deu" for German. More than one language can be
        specified by joining with '+': for example "eng+deu" means that the
        text to be read may be in a mixture of English and German.

        This defaults to "eng" (English). You can change the global default
        value by setting ``lang`` in the ``[ocr]`` section of
        :ref:`.stbt.conf` or the appropriate
        :ref:`Node-specific configuration file <node-specific-config>`.

        You may need to install the tesseract language pack; see installation
        instructions
        `here <https://stb-tester.com/manual/faq#installing-language-packs>`__.

    :param dict tesseract_config:
        Allows passing configuration down to the underlying OCR engine.
        See the `tesseract documentation
        <https://github.com/tesseract-ocr/tesseract/wiki/ControlParams>`__
        for details.

    :type tesseract_user_words: unicode string, or list of unicode strings
    :param tesseract_user_words:
        List of words to be added to the tesseract dictionary. To replace the
        tesseract system dictionary altogether, also set
        ``tesseract_config={'load_system_dawg': False, 'load_freq_dawg':
        False}``.

    :type tesseract_user_patterns: unicode string, or list of unicode strings
    :param tesseract_user_patterns:
        List of patterns to add to the tesseract dictionary. The tesseract
        pattern language corresponds roughly to the following regular
        expressions::

            tesseract  regex
            =========  ===========
            \c         [a-zA-Z]
            \d         [0-9]
            \n         [a-zA-Z0-9]
            \p         [:punct:]
            \a         [a-z]
            \A         [A-Z]
            \*         *

    :param bool upsample:
        Upsample the image 3x before passing it to tesseract. This helps to
        preserve information in the text's anti-aliasing that would otherwise
        be lost when tesseract binarises the image. This defaults to ``True``;
        you can override the global default value by setting ``upsample=False``
        in the ``[ocr]`` section of :ref:`.stbt.conf`. You should set this to
        False if the text is already quite large, or if you are doing your own
        binarisation (pre-processing the image to make it black and white).

    :param Color text_color:
        Color of the text. Specifying this can improve OCR results when
        tesseract's default thresholding algorithm doesn't detect the text,
        for example white text on a light-colored background or text on a
        translucent overlay with dynamic content underneath.

    :param int text_color_threshold:
        The threshold to use with ``text_color``, between 0 and 255. Defaults
        to 25. You can override the global default value by setting
        ``text_color_threshold`` in the ``[ocr]`` section of :ref:`.stbt.conf`.

    :param OcrEngine engine:
        The OCR engine to use. Defaults to ``OcrEngine.TESSERACT``. You can
        override the global default value by setting ``engine`` in the ``[ocr]``
        section of :ref:`.stbt.conf`.

    :param str char_whitelist:
        String of characters that are allowed. Useful when you know that the
        text is only going to contain numbers or IP addresses, for example so
        that tesseract won't think that a zero is the letter o.
        Note that Tesseract 4.0's LSTM engine ignores ``char_whitelist``.

    :param dict corrections:
        Dictionary of corrections to replace known OCR mis-reads. Each key of
        the dict is the text to search for; the value is the corrected string
        to replace the matching key. If the key is a string, it is treated as
        plain text and it will only match at word boundaries (for example the
        string ``"he saw"`` won't match ``"the saw"`` nor ``"he saws"``). If
        the key is a regular expression pattern (created with `re.compile`) it
        can match anywhere, and the replacement string can contain
        backreferences such as ``"\1"`` which are replaced with the
        corresponding group in the pattern (same as Python's `re.sub`).
        Example::

            corrections={'bad': 'good',
                         re.compile(r'[oO]'): '0'}

        Plain strings are replaced first (in the order they are specified),
        followed by regular expresions (in the order they are specified).

        The default value for this parameter can be set with
        `stbt.set_global_ocr_corrections`. If global corrections have been set
        *and* this ``corrections`` parameter is specified, the corrections in
        this parameter are applied first.
    """
    if frame is None:
        from stbt_core import get_frame
        frame = get_frame()

    region = _validate_region(frame, region)

    from .ocr_tesseract import ocr_tesseract
    text = ocr_tesseract(
        frame, region, mode, lang, tesseract_config, tesseract_user_words,
        tesseract_user_patterns, upsample, text_color, text_color_threshold,
        engine, char_whitelist, corrections)

    debug("ocr(frame=%s, region=%r): %r" % (_frame_repr(frame), region, text))
    draw_source_region(frame, region)
    return text


def ocr_postprocess(text: str, corrections: Optional[CorrectionsT]) -> str:
    text = text.strip().translate(_ocr_transtab)
    return apply_ocr_corrections(text, corrections)


def match_text(
    text: str,
    frame: Optional[FrameT] = None,
    region: Region = Region.ALL,
    mode: OcrMode = OcrMode.PAGE_SEGMENTATION_WITHOUT_OSD,
    lang: Optional[str] = None,
    tesseract_config: Optional[typing.Mapping[str, bool | str | int]] = None,
    case_sensitive: bool = False,
    upsample: Optional[bool] = None,
    text_color: Optional[ColorT] = None,
    text_color_threshold: Optional[float] = None,
    engine: Optional[OcrEngine] = None,
    char_whitelist: Optional[str] = None,
) -> TextMatchResult:
    """Search for the specified text in a single video frame.

    This can be used as an alternative to `match`, searching for text instead
    of an image.

    :param str text: The text to search for.
    :param frame: See `ocr`.
    :param region: See `ocr`.
    :param mode: See `ocr`.
    :param lang: See `ocr`.
    :param tesseract_config: See `ocr`.
    :param upsample: See `ocr`.
    :param text_color: See `ocr`.
    :param text_color_threshold: See `ocr`.
    :param engine: See `ocr`.
    :param char_whitelist: See `ocr`.
    :param bool case_sensitive: Ignore case if False (the default).

    :returns:
      A `TextMatchResult`, which will evaluate to True if the text was found,
      false otherwise.

    For example, to select a button in a vertical menu by name (in this case
    "TV Guide")::

        m = stbt.match_text("TV Guide")
        assert m.match
        while not stbt.match('selected-button.png').region.contains(m.region):
            stbt.press('KEY_DOWN')
    """
    if frame is None:
        from stbt_core import get_frame
        frame = get_frame()

    region = _validate_region(frame, region)

    from .ocr_tesseract import match_text_tesseract
    result = match_text_tesseract(
        text, frame, region, mode, lang, tesseract_config, case_sensitive,
        upsample, text_color, text_color_threshold, engine, char_whitelist)

    if result.match:
        debug("match_text: Match found: %s" % str(result))
    else:
        debug("match_text: No match found: %s" % str(result))

    draw_source_region(frame, region)
    return result


# Python 2.7 & 3.6 have `re._pattern_type` but that will be removed in Python
# 3.7 where they introduce `re.Pattern`.
PatternType = type(re.compile(""))


def apply_ocr_corrections(
        text: str,
        corrections: Optional[CorrectionsT] = None) -> str:
    """Applies the same corrections as `stbt.ocr`'s ``corrections`` parameter.

    This is available as a separate function so that you can use it to
    post-process old test artifacts using new corrections.

    :param str text: The text to correct.
    :param dict corrections: See `stbt.ocr`.
    """
    if corrections:
        text = _apply_ocr_corrections(text, corrections)
    if global_ocr_corrections:
        text = _apply_ocr_corrections(text, global_ocr_corrections)
    return text


def _apply_ocr_corrections(text, corrections):

    def replace_string(matchobj):
        old = matchobj.group(2)
        new = corrections[old]
        debug("ocr corrections: %r -> %r" % (old, new))
        return matchobj.group(1) + new + matchobj.group(3)

    def replace_regex(matchobj):
        new = corrections[matchobj.re]
        debug("ocr corrections: /%s/ -> %r" % (matchobj.re.pattern, new))
        return new

    for k in corrections:
        if isinstance(k, str):
            # Match plain strings at word boundaries
            text = re.sub(r"(^|\W)(" + re.escape(k) + r")(\W|$)",
                          replace_string, text, re.UNICODE)
        elif isinstance(k, PatternType):
            text = re.sub(k, replace_regex, text)
    return text


global_ocr_corrections = {}


def set_global_ocr_corrections(corrections: CorrectionsT):
    """Specify default OCR corrections that apply to all calls to `stbt.ocr`
    and `stbt.apply_ocr_corrections`.

    See the ``corrections`` parameter of `stbt.ocr` for more details.

    We recommend calling this function from ``tests/__init__.py`` to ensure it
    is called before any test script is executed.
    """
    global global_ocr_corrections
    debug("Initialising global ocr corrections to: %r" % (corrections,))
    global_ocr_corrections = corrections


def ocr_eq(a: str, b: str) -> bool:
    """Compare two strings for equality, ignoring common OCR errors.

    `stbt.ocr` sometimes mistakes some characters, such as "O" instead of "0",
    especially when reading short fragments of text without enough context.
    ``ocr_eq`` wil treat such characters as equal to each other. It also ignores
    spaces and punctuation. For example:

    >>> ocr_eq("hello", "hel 10")
    True

    The character mapping used by ``ocr_eq``'s normalization algorithm is
    available in ``ocr_eq.replacements``; you can modify it by adding or
    removing entries. The default mapping is:

    >>> ocr_eq.replacements
    {'0': 'o', 'O': 'o',
     '1': 'l', 'i': 'l', 'I': 'l', '|': 'l', '7': 'l',
     '2': 'z', 'Z': 'z',
     '4': 'A',
     '5': 's', 'S': 's',
     '6': 'g', 'G': 'g', '9': 'g', 'q': 'g',
     '8.': '&',
     '8': 'B',
     'f': 'r', 'F': 'r',
     'ł': 't',
     'm': 'rn',
     'C': 'c',
     'K': 'k',
     'P': 'p',
     'V': 'v',
     'W': 'w',
     'vv': 'w',
     'X': 'x',
     'Y': 'y'}

    If you need to normalize a single string using this same algorithm, use
    ``ocr_eq.normalize``:

    >>> ocr_eq.normalize("hel 10")
    'hello'

    Added in v34.
    """
    return ocr_eq.normalize(a) == ocr_eq.normalize(b)


def normalize(text: str):
    if not isinstance(text, str):
        raise TypeError(
            f"stbt.ocr_eq.normalize: Expected a str, got {text!r}")
    return _normalize(text, ocr_eq.replacements)


def _normalize(text: str, replacements,
               remove_whitespace=True, remove_punctuation=True) -> str:
    for a, b in replacements.items():
        text = text.replace(a, b)
    if remove_whitespace:
        text = "".join(c for c in text if not c.isspace())
    if remove_punctuation:
        text = "".join(c for c in text if unicodedata.category(c)[0] != 'P')
    return text


class Replacements(collections.UserDict):
    def __setitem__(self, key: str, value: str) -> None:
        value = _normalize(value, self, False, False)
        return super().__setitem__(key, value)

    def __delitem__(self, key):
        raise TypeError("Cannot remove items from ocr_eq.replacements")


ocr_eq.replacements = Replacements({
    '0': 'o', 'O': 'o',
    '1': 'l', 'i': 'l', 'I': 'l', '|': 'l', '7': 'l',
    '2': 'z', 'Z': 'z',
    '4': 'A',
    '5': 's', 'S': 's',
    '6': 'g', 'G': 'g', '9': 'g', 'q': 'g',
    '8.': '&',
    '8': 'B',
    'f': 'r', 'F': 'r',
    'ł': 't',
    'm': 'rn',
    'C': 'c',
    'K': 'k',
    'P': 'p',
    'V': 'v',
    'W': 'w',
    'vv': 'w',
    'X': 'x',
    'Y': 'y',
})


ocr_eq.normalize = normalize


def bgr_diff(frame, color, threshold, imglog: ImageLogger):
    # Calculate distance of each pixel from `text_color`, then discard
    # everything further than `text_color_threshold` distance away.
    sqd = numpy.subtract(frame, Color(color).array, dtype=numpy.int32)
    sqd = (sqd[:, :, 0] ** 2 +
           sqd[:, :, 1] ** 2 +
           sqd[:, :, 2] ** 2)

    if imglog.enabled:
        normalised = numpy.sqrt(sqd / 3)
        imglog.imwrite(
            "diff", normalised,
            description=(
                f"The Euclidean distance of each pixel from the specified "
                f"text_color ({color!r}), normalised to the range 0–255.  "
                "Darker pixels are closer to the text color and are more "
                "likely to be text."
            ),
            source_region=imglog.data.get("region"),
        )

    d = sqd >= (threshold ** 2) * 3
    d = d.astype(numpy.uint8) * 255
    imglog.imwrite(
        "binarized", d,
        description=(
            f"Binary image after applying text_color_threshold ({threshold}). "
            "Black pixels are within the threshold distance of text_color and "
            "will be treated as potential text; white pixels are too far from "
            "text_color and will be treated as background."
        ),
        source_region=imglog.data.get("region"),
    )
    return d


ocr.text_color_differ = bgr_diff
