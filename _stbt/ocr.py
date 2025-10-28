from __future__ import annotations

import collections
import errno
import glob
import os
import re
import shutil
import subprocess
import unicodedata
from enum import IntEnum
from typing import Optional

import cv2
import numpy

from . import imgproc_cache
from .config import get_config
from .imgutils import Color, ColorT, crop, FrameT, _frame_repr, _validate_region
from .logging import debug, draw_source_region, ImageLogger, warn
from .types import Region
from .utils import LooseVersion, named_temporary_directory, to_unicode

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
    tesseract_config: Optional[dict[str, bool | str | int]] = None,
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

    if isinstance(tesseract_user_words, (bytes, str)):
        tesseract_user_words = [tesseract_user_words]

    if isinstance(tesseract_user_patterns, (bytes, str)):
        tesseract_user_patterns = [tesseract_user_patterns]

    if upsample is None:
        upsample = get_config("ocr", "upsample", type_=bool)

    draw_source_region(frame, region)
    imglog = ImageLogger("ocr", result=None)

    text = _tesseract(
        frame, region, mode, lang, tesseract_config,
        tesseract_user_patterns, tesseract_user_words, upsample, text_color,
        text_color_threshold, engine, char_whitelist, imglog)
    text = text.strip().translate(_ocr_transtab)
    text = apply_ocr_corrections(text, corrections)

    debug("ocr(frame=%s, region=%r): %r" % (_frame_repr(frame), region, text))
    _log_ocr_image_debug(imglog, text)
    return text


def match_text(
    text: str,
    frame: Optional[FrameT] = None,
    region: Region = Region.ALL,
    mode: OcrMode = OcrMode.PAGE_SEGMENTATION_WITHOUT_OSD,
    lang: Optional[str] = None,
    tesseract_config: Optional[dict[str, bool | str | int]] = None,
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

    if upsample is None:
        upsample = get_config("ocr", "upsample", type_=bool)

    _config = dict(tesseract_config or {})
    _config['tessedit_create_hocr'] = 1

    rts = getattr(frame, "time", None)

    draw_source_region(frame, region)
    imglog = ImageLogger("match_text")

    xml = _tesseract(frame, region, mode, lang, _config,
                     None, text.split(), upsample, text_color,
                     text_color_threshold, engine, char_whitelist,
                     imglog)
    if xml == '':
        hocr = None
        result = TextMatchResult(rts, False, None, frame, text)
    else:
        import lxml.etree
        hocr = lxml.etree.fromstring(xml.encode('utf-8'))
        p = _hocr_find_phrase(hocr, to_unicode(text).split(), case_sensitive)
        if p:
            # Find bounding box
            box = Region.bounding_box(*[_hocr_elem_region(elem)
                                        for _, elem in p])
            # _tesseract crops to region and scales up by a factor of 3 so
            # we must undo this transformation here.
            n = 3 if upsample else 1
            box = Region.from_extents(
                region.x + box.x // n, region.y + box.y // n,
                region.x + box.right // n, region.y + box.bottom // n)
            result = TextMatchResult(rts, True, box, frame, text)
        else:
            result = TextMatchResult(rts, False, None, frame, text)

    if result.match:
        debug("match_text: Match found: %s" % str(result))
    else:
        debug("match_text: No match found: %s" % str(result))

    imglog.set(text=text, case_sensitive=case_sensitive,
               result=result, hocr=hocr)
    _log_ocr_image_debug(imglog)

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


_memoise_tesseract_version = None


def _tesseract_version(output=None):
    r"""Different versions of tesseract have different bugs.  This function
    allows us to tell the user if what they want isn't going to work.

    >>> (_tesseract_version('tesseract 3.03\n leptonica-1.70\n') >
    ...  _tesseract_version('tesseract 3.02\n'))
    True

    Note that LooseVersion.__cmp__ simply sorts lexicographically according
    to the "." or "-" separated components in the version string:

    >>> _tesseract_version("tesseract 4.0.0-beta.1")
    [4, 0, 0, '-', 'beta', 1]
    >>> (_tesseract_version('tesseract 4.0.0-beta.1') >
    ...  _tesseract_version('tesseract 4.0.0'))
    True

    """
    global _memoise_tesseract_version
    if output is None:
        if _memoise_tesseract_version is None:
            try:
                _memoise_tesseract_version = subprocess.check_output(
                    ['tesseract', '--version'],
                    stderr=subprocess.STDOUT).decode("utf-8")
            except OSError as e:
                if e.errno == errno.ENOENT:
                    raise RuntimeError("Tesseract OCR engine isn't installed")
                else:
                    raise
        output = _memoise_tesseract_version

    line = [x for x in output.split('\n') if x.startswith('tesseract')][0]
    return LooseVersion(line.split()[1])


def _tesseract(frame, region, mode, lang, _config, user_patterns, user_words,
               upsample, text_color, text_color_threshold, engine,
               char_whitelist, imglog):

    if _config is None:
        _config = {}

    if lang is None:
        lang = get_config("ocr", "lang", "eng")

    if text_color_threshold is None:
        text_color_threshold = get_config(
            "ocr", "text_color_threshold", type_=int)

    if engine is None:
        engine = get_config("ocr", "engine", type_=OcrEngine)

    tesseract_version = _tesseract_version()

    if tesseract_version < [4, 0]:
        if engine == OcrEngine.DEFAULT:
            engine = OcrEngine.TESSERACT
        if engine != OcrEngine.TESSERACT:
            # NB `str(engine)` looks like "OcrEngine.LSTM"
            raise ValueError("%s isn't available in tesseract %s"
                             % (engine, tesseract_version))

    if mode >= OcrMode.RAW_LINE and tesseract_version < [3, 4]:
        # NB `str(mode)` looks like "OcrMode.RAW_LINE"
        raise ValueError("%s isn't available in tesseract %s"
                         % (mode, tesseract_version))

    imglog.imwrite("source", frame)
    imglog.set(region=region, engine=engine, mode=mode, lang=lang,
               tesseract_config=_config.copy(),
               user_patterns=user_patterns, user_words=user_words,
               upsample=upsample, text_color=text_color,
               text_color_threshold=text_color_threshold,
               char_whitelist=char_whitelist,
               tesseract_version=tesseract_version)

    frame = crop(frame, region)

    if text_color is not None:
        if upsample:
            frame = _upsample(frame, imglog)
            upsample = False
        frame = ocr.text_color_differ(frame, text_color, text_color_threshold,
                                      imglog)

    return _tesseract_subprocess(frame, mode, lang, _config,  # pylint:disable=unexpected-keyword-arg
                                 user_patterns, user_words, upsample,
                                 engine, char_whitelist, imglog,
                                 tesseract_version, use_cache=True)


def bgr_diff(frame, color, threshold, imglog):
    # Calculate distance of each pixel from `text_color`, then discard
    # everything further than `text_color_threshold` distance away.
    sqd = numpy.subtract(frame, Color(color).array, dtype=numpy.int32)
    sqd = (sqd[:, :, 0] ** 2 +
           sqd[:, :, 1] ** 2 +
           sqd[:, :, 2] ** 2)

    if imglog.enabled:
        normalised = numpy.sqrt(sqd / 3)
        imglog.imwrite("diff", normalised)

    d = sqd >= (threshold ** 2) * 3
    d = d.astype(numpy.uint8) * 255
    imglog.imwrite("binarized", d)
    return d


ocr.text_color_differ = bgr_diff


@imgproc_cache.memoize({"version": "33"})
def _tesseract_subprocess(
        frame, mode, lang, _config, user_patterns, user_words, upsample,
        engine, char_whitelist, imglog, tesseract_version):

    if tesseract_version >= [4, 0]:
        engine_flags = ["--oem", str(int(engine))]
        tessdata_suffix = ''
    else:
        engine_flags = []
        tessdata_suffix = '/tessdata'

    if upsample:
        frame = _upsample(frame, imglog)

    # $XDG_RUNTIME_DIR is likely to be on tmpfs:
    tmpdir = os.environ.get("XDG_RUNTIME_DIR", None)

    with named_temporary_directory(prefix='stbt-ocr-', dir=tmpdir) as tmp:

        if tesseract_version >= [3, 5]:
            psm_flag = "--psm"
        else:
            psm_flag = "-psm"

        cmd = ["tesseract", '-l', lang,
               tmp + '/input.png',
               tmp + '/output',
               psm_flag, str(int(mode))] + engine_flags

        tessenv = os.environ.copy()

        if (_config or user_words or user_patterns or char_whitelist or
                imglog.enabled):
            tessdata_dir = tmp + '/tessdata'
            os.mkdir(tessdata_dir)
            _symlink_copy_dir(_find_tessdata_dir(tessdata_suffix), tmp)
            tessenv['TESSDATA_PREFIX'] = tmp + '/'
            if tesseract_version >= [4, 0, 0]:
                tessenv['TESSDATA_PREFIX'] += "tessdata"

        if ('tessedit_create_hocr' in _config and
                tesseract_version >= [3, 4]):
            _config['tessedit_create_txt'] = 0

        if user_words:
            if 'user_words_suffix' in _config:
                raise ValueError(
                    "You cannot specify 'user_words' and " +
                    "'tesseract_config[\"user_words_suffix\"]' " +
                    "at the same time")
            with open('%s/%s.user-words' % (tessdata_dir, lang),
                      'w', encoding='utf-8') as f:
                f.write('\n'.join(to_unicode(x) for x in user_words))
            _config['user_words_suffix'] = 'user-words'

        if user_patterns:
            if 'user_patterns_suffix' in _config:
                raise ValueError(
                    "You cannot specify 'user_patterns' and " +
                    "'tesseract_config[\"user_patterns_suffix\"]' " +
                    "at the same time")
            with open('%s/%s.user-patterns' % (tessdata_dir, lang),
                      'w', encoding='utf-8') as f:
                f.write('\n'.join(to_unicode(x) for x in user_patterns))
            _config['user_patterns_suffix'] = 'user-patterns'

        if char_whitelist:
            if 'tessedit_char_whitelist' in _config:
                raise ValueError(
                    "You cannot specify 'char_whitelist' and " +
                    "'tesseract_config[\"tessedit_char_whitelist\"]' " +
                    "at the same time")
            _config["tessedit_char_whitelist"] = char_whitelist

        if imglog.enabled:
            _config['tessedit_write_images'] = True

        if _config:
            os.makedirs(tessdata_dir + '/configs', exist_ok=True)
            with open(tessdata_dir + '/configs/stbtester',
                      'w', encoding='utf-8') as cfg:
                for k, v in _config.items():
                    if isinstance(v, bool):
                        cfg.write(('%s %s\n' % (k, 'T' if v else 'F')))
                    else:
                        cfg.write("%s %s\n" % (k, to_unicode(v)))
            cmd += ['stbtester']

        cv2.imwrite(tmp + '/input.png', frame)
        try:
            subprocess.check_output(cmd, cwd=tmp, env=tessenv,
                                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            warn("Tesseract failed: %s" % e.output.decode("utf-8", "replace"))
            raise

        if imglog.enabled:
            tessinput = os.path.join(tmp, "tessinput.tif")
            if os.path.exists(tessinput):
                imglog.imwrite("tessinput", cv2.imread(tessinput))

        for filename in glob.glob(tmp + "/output.*"):
            _, ext = os.path.splitext(filename)
            if ext in (".txt", ".hocr"):
                with open(filename, encoding='utf-8') as f:
                    return f.read()


def _upsample(frame, imglog):
    # We scale image up 3x before feeding it to tesseract as this
    # significantly reduces the error rate by more than 6x in tests.  This
    # uses bilinear interpolation which produces the best results.  See
    # http://stb-tester.com/blog/2014/04/14/improving-ocr-accuracy.html
    outsize = (frame.shape[1] * 3, frame.shape[0] * 3)
    frame = cv2.resize(frame, outsize, interpolation=cv2.INTER_LINEAR)
    imglog.imwrite("upsampled", frame)
    return frame


def _hocr_iterate(hocr):
    started = False
    need_space = False
    for elem in hocr.iterdescendants():
        if elem.tag == '{http://www.w3.org/1999/xhtml}p' and started:
            yield ('\n', elem)
            need_space = False
        if elem.tag == '{http://www.w3.org/1999/xhtml}span' and \
                'ocr_line' in elem.get('class').split() and started:
            yield ('\n', elem)
            need_space = False
        for e, t in [(elem, elem.text), (elem.getparent(), elem.tail)]:
            if t:
                if t.strip():
                    if need_space and started:
                        yield (' ', None)
                    need_space = False
                    yield (str(t).strip(), e)
                    started = True
                else:
                    need_space = True


def _hocr_find_phrase(hocr, phrase, case_sensitive):
    if case_sensitive:
        lower = lambda s: s
    else:
        lower = lambda s: s.lower()

    words_only = [(lower(w).translate(_ocr_transtab), elem)
                  for w, elem in _hocr_iterate(hocr) if w.strip() != '']
    phrase = [lower(w).translate(_ocr_transtab) for w in phrase]

    # Dumb and poor algorithmic complexity but succint and simple
    if len(phrase) <= len(words_only):
        for x in range(0, len(words_only)):
            sublist = words_only[x:x + len(phrase)]
            if all(w[0] == p for w, p in zip(sublist, phrase)):
                return sublist
    return None


def _hocr_elem_region(elem):
    while elem is not None:
        m = re.search(r'bbox (\d+) (\d+) (\d+) (\d+)', elem.get('title') or '')
        if m:
            extents = [int(x) for x in m.groups()]
            return Region.from_extents(*extents)
        elem = elem.getparent()


def _find_tessdata_dir(tessdata_suffix):
    tessdata_prefix = os.environ.get("TESSDATA_PREFIX", None)
    if tessdata_prefix:
        tessdata = tessdata_prefix + tessdata_suffix
        tessdata = os.path.normpath(tessdata)
        if os.path.exists(tessdata):
            return tessdata
        else:
            raise RuntimeError('Invalid TESSDATA_PREFIX: %s' % tessdata_prefix)

    tess_prefix_share = os.path.normpath(
        shutil.which('tesseract') + '/../../share/')
    for suffix in [
            '/tessdata', '/tesseract-ocr/tessdata', '/tesseract/tessdata',
            '/tesseract-ocr/4.00/tessdata']:
        if os.path.exists(tess_prefix_share + suffix):
            return tess_prefix_share + suffix
    raise RuntimeError('Installation error: Cannot locate tessdata directory')


def _log_ocr_image_debug(imglog, output=None):
    if not imglog.enabled:
        return

    if imglog.name == "ocr":
        title = "stbt.ocr"
        match_text = False  # pylint:disable=redefined-outer-name
    else:
        match_text = True
        title = "stbt.match_text(%r): %s" % (
            imglog.data["text"],
            "Matched" if imglog.data["result"] else "Didn't match")
        hocr = imglog.data["hocr"]
        if hocr is None:
            output = ""
        else:
            output = "".join(x for x, _ in _hocr_iterate(hocr))

    template = """\
        <h4>{{title}}</h4>

        {{ annotated_image(result) }}

        {% if match_text %}
        <h5>Result:</h5>
        <pre><code>{{ result | escape }}</code></pre>
        {% endif %}

        <h5>Tesseract output:</h5>
        <pre><code>{{ output | escape }}</code></pre>

        <h5>Parameters:</h5>
        <ul>
          {% if match_text %}
          <li>case_sensitive={{case_sensitive}}
          {% endif %}
          <li>char_whitelist={{char_whitelist}}
          <li>engine={{engine}}
          <li>lang={{lang}}
          <li>mode={{mode}}
          <li>tesseract_config={{tesseract_config}}
          <li>tesseract_user_patterns={{user_patterns}}
          <li>tesseract_user_words={{user_words}}
          <li>tesseract_version={{tesseract_version}}
          {% if match_text %}
          <li>text={{text}}
          {% endif %}
          <li>text_color={{text_color}}
          <li>text_color_threshold={{text_color_threshold}}
          <li>upsample={{upsample}}
        </ul>

        {% if "upsampled" in images %}
        <h5>ROI Scaled:</h5>
        <img src="upsampled.png" />
        {% endif %}

        {% if "diff" in images %}
        <h5>Color difference {{ text_color }}:</h5>
        <img src="diff.png" />
        {% endif %}

        {% if "binarized" in images %}
        <h5>
          Color difference – binarised
          (threshold={{ text_color_threshold }}):
        </h5>
        <img src="binarized.png" />
        {% endif %}

        {% if "tessinput" in images %}
        <h5>Tesseract's binarisation:</h5>
        <img src="tessinput.png" />
        {% endif %}
    """

    imglog.html(
        template,
        match_text=match_text,
        output=output,
        title=title,
    )


def _symlink_copy_dir(a, b):
    """Behaves like `cp -rs` with GNU cp but is portable and doesn't require
    execing another process.  Tesseract requires files in the "tessdata"
    directory to be modified to set config options.  tessdata may be on a
    read-only system directory so we use this to work around that limitation.
    """
    from os.path import basename, join, relpath
    newroot = join(b, basename(a))
    for dirpath, dirnames, filenames in os.walk(a):
        for name in dirnames:
            if name not in ['.', '..']:
                rel = relpath(join(dirpath, name), a)
                os.mkdir(join(newroot, rel))
        for name in filenames:
            rel = relpath(join(dirpath, name), a)
            os.symlink(join(a, rel), join(newroot, rel))
