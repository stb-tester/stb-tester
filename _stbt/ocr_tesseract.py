from __future__ import annotations

import errno
import os
import re
import shutil
import subprocess
import typing
from typing import Optional

import cv2

from . import imgproc_cache
from .config import get_config
from .imgutils import ColorT, crop, FrameT
from .logging import ImageLogger, warn
from .ocr import (
    _ocr_transtab,
    CorrectionsT,
    ocr,
    ocr_postprocess,
    OcrEngine,
    OcrMode,
    TextMatchResult,
)
from .types import Region
from .utils import LooseVersion, named_temporary_directory, to_unicode


def ocr_tesseract(
    frame: FrameT,
    region: Region,
    mode: OcrMode,
    lang: Optional[str],
    tesseract_config: Optional[typing.Mapping[str, bool | str | int]],
    tesseract_user_words: Optional[list[str] | str],
    tesseract_user_patterns: Optional[list[str] | str],
    upsample: Optional[bool],
    text_color: Optional[ColorT],
    text_color_threshold: Optional[float],
    engine: Optional[OcrEngine],
    char_whitelist: Optional[str],
    corrections: Optional[CorrectionsT],
) -> str:
    imglog = ImageLogger("ocr", result=None)
    if isinstance(tesseract_user_words, (bytes, str)):
        tesseract_user_words = [tesseract_user_words]
    if isinstance(tesseract_user_patterns, (bytes, str)):
        tesseract_user_patterns = [tesseract_user_patterns]
    if upsample is None:
        upsample = get_config("ocr", "upsample", type_=bool)
    _config = dict(tesseract_config or {})
    _config['tessedit_create_txt'] = 1
    text, _ = _tesseract(
        frame, region, mode, lang, _config, tesseract_user_patterns,
        tesseract_user_words, upsample, text_color, text_color_threshold,
        engine, char_whitelist, imglog)
    assert text is not None
    text = ocr_postprocess(text, corrections)
    imglog.html(_TESSERACT_DEBUG_TEMPLATE, match_text=False, output=text,
                title="stbt.ocr")
    return text


def match_text_tesseract(
    text: str,
    frame: FrameT,
    region: Region,
    mode: OcrMode,
    lang: Optional[str],
    tesseract_config: Optional[typing.Mapping[str, bool | str | int]],
    case_sensitive: bool,
    upsample: Optional[bool],
    text_color: Optional[ColorT],
    text_color_threshold: Optional[float],
    engine: Optional[OcrEngine],
    char_whitelist: Optional[str],
) -> TextMatchResult:
    rts = getattr(frame, "time", None)
    imglog = ImageLogger("match_text")
    if upsample is None:
        upsample = get_config("ocr", "upsample", type_=bool)
    _config = dict(tesseract_config or {})
    _config['tessedit_create_hocr'] = 1
    _config['tessedit_create_txt'] = 0
    _, xml = _tesseract(
        frame, region, mode, lang, _config,
        None, text.split(), upsample, text_color,
        text_color_threshold, engine, char_whitelist,
        imglog)
    if xml == '':
        result = TextMatchResult(rts, False, None, frame, text)
        imglog.set(output="")
    else:
        import lxml.etree
        hocr = lxml.etree.fromstring(xml.encode('utf-8'))
        if imglog.enabled:
            imglog.set(output="".join(x for x, _ in _hocr_iterate(hocr)))
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
    imglog.html(
        _TESSERACT_DEBUG_TEMPLATE, match_text=True, text=text,
        case_sensitive=case_sensitive, result=result,
        title="stbt.match_text(%r): %s" % (
            text, "Matched" if result else "Didn't match"))
    return result


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


def _tesseract(
        frame: FrameT,
        region: Region,
        mode: OcrMode,
        lang: Optional[str],
        _config: Optional[dict[str, bool | str | int]],
        user_patterns: Optional[list[str]],
        user_words: Optional[list[str]],
        upsample: bool,
        text_color: Optional[ColorT],
        text_color_threshold: Optional[float],
        engine: Optional[OcrEngine],
        char_whitelist: Optional[str],
        imglog: ImageLogger,
):

    if _config is None:
        _config = {}
    else:
        _config = dict(_config)

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

    imglog.imwrite("frame", frame)
    imglog.set(region=region, engine=engine, mode=mode, lang=lang,
               tesseract_config=_config.copy(),
               user_patterns=user_patterns, user_words=user_words,
               upsample=upsample, text_color=text_color,
               text_color_threshold=text_color_threshold,
               char_whitelist=char_whitelist,
               tesseract_version=tesseract_version)

    frame = crop(frame, region)

    upsample_arg = upsample
    if text_color is not None:
        if upsample:
            frame = _upsample(frame, imglog)
            upsample_arg = False
        frame = ocr.text_color_differ(frame, text_color, text_color_threshold,
                                      imglog)

    txt, hocr = _tesseract_subprocess(  # pylint:disable=unexpected-keyword-arg
        frame, mode, lang, _config, user_patterns, user_words, upsample_arg,
        engine, char_whitelist, imglog, tesseract_version,
        use_cache=True)

    if imglog.enabled:
        if upsample:
            scale = 3
        else:
            scale = 1
        off_x = max(0, region.x)
        off_y = max(0, region.y)
        imglog.set(
            source_tsv_regions=[
                (
                    Region.from_extents(
                        off_x + r.x // scale,
                        off_y + r.y // scale,
                        off_x + (r.right + scale - 1) // scale,
                        off_y + (r.bottom + scale - 1) // scale),
                    css_class,
                    title
                )
                for r, css_class, title in imglog.data["tsv_regions"]
            ]
        )

    assert isinstance(txt, (str, type(None)))
    assert isinstance(hocr, (str, type(None)))
    return txt, hocr


@imgproc_cache.memoize({"version": "34"})
def _tesseract_subprocess(
        frame: FrameT,
        mode: int,
        lang: str,
        _config: dict,
        user_patterns: list[str] | None,
        user_words: list[str] | None,
        upsample: int,
        engine: int,
        char_whitelist: str | None,
        imglog: ImageLogger,
        tesseract_version: list[int],
) -> tuple[Optional[str], Optional[str]]:

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
            _config['tessedit_create_tsv'] = 1

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

        try:
            with open(tmp + "/output.txt", encoding='utf-8') as f:
                txt = f.read()
        except FileNotFoundError:
            txt = None
        try:
            with open(tmp + "/output.hocr", encoding='utf-8') as f:
                hocr = f.read()
        except FileNotFoundError:
            hocr = None
        imglog.set(hocr_xml=hocr)

        if imglog.enabled:
            tsv_regions: list[tuple[Region, str, str | None]] = []
            try:
                with open(tmp + "/output.tsv", encoding='utf-8') as f:
                    import csv
                    tsv = list(csv.DictReader(
                        f, delimiter='\t', quoting=csv.QUOTE_NONE))
            except FileNotFoundError:
                pass
            else:
                for row in tsv:
                    level = int(row['level'])
                    css_class = "tsv-" + _TSV_LEVEL_TO_TYPE[level]
                    region = Region(
                        int(row['left']), int(row['top']),
                        int(row['width']), int(row['height'])
                    )
                    if level > 1:
                        title = _TSV_LEVEL_TO_TYPE[level].capitalize()
                        if row['text']:
                            title += " \"%s\"\n(confidence: %s%%)" % (
                                row['text'], row['conf'])

                        tsv_regions.append((region, css_class, title))

            imglog.set(tsv_regions=tsv_regions)

            tsv_words = [x for x in tsv_regions if x[1] == "tsv-word"]
            if not tsv_words:
                info_msg = "Note: No words were detected by Tesseract."
            else:
                info_msg = (
                    "This image should have at least a 1px white border "
                    "around every edge."
                )
                bad_borders = []
                for region, css_class, title in tsv_words:
                    touching_edge = []
                    if region.x <= 0:
                        touching_edge.append("left")
                    if region.y <= 0:
                        touching_edge.append("top")
                    if region.right >= frame.shape[1]:
                        touching_edge.append("right")
                    if region.bottom >= frame.shape[0]:
                        touching_edge.append("bottom")
                    if touching_edge:
                        bad_borders.append(
                            "* The word %s is touching the %s edge(s) of the "
                            "image.\n" % (
                                title.replace("\n", " "),
                                and_join(touching_edge)))
                if bad_borders:
                    info_msg += (
                        "  Note:\n\n" + "".join(bad_borders) +
                        "\nLack of a border can indicate that:\n"
                        "\n"
                        "* The region is too big and it's including some "
                        "surrounding text that should not be there.\n"
                        "* The region is too small and the text overlaps "
                        "the edge of the image, indicating that some of "
                        "the text might be outside the image\n"
                        "* There is some non-text background that is "
                        "surviving thresholding\n"
                        "\n"
                        "IMPORTANT: Look at the image to see which of the "
                        "above issues is the case, and adjust your region "
                        "or thresholding accordingly."
                    )

            tessinput = os.path.join(tmp, "tessinput.tif")
            if os.path.exists(tessinput):
                imglog.imwrite(
                    "tessinput", cv2.imread(tessinput),
                    description=(
                        "The image as binarized internally by Tesseract.  "
                        "This shows exactly what Tesseract is analysing after "
                        "its own preprocessing.  Text is black, background is "
                        "white\n"
                        "\n" + info_msg
                    ),
                    source_region=imglog.data.get("region"),
                )

        return txt, hocr


def and_join(elems: list[str]) -> str:
    match elems:
        case []:
            return ""
        case [x]:
            return x
        case [*x, y]:
            return "%s and %s" % (", ".join(x), y)


_TSV_LEVEL_TO_TYPE = [None, 'page', 'block', 'paragraph', 'line', 'word']


def _upsample(frame, imglog: ImageLogger):
    # We scale image up 3x before feeding it to tesseract as this
    # significantly reduces the error rate by more than 6x in tests.  This
    # uses bilinear interpolation which produces the best results.  See
    # http://stb-tester.com/blog/2014/04/14/improving-ocr-accuracy.html
    outsize = (frame.shape[1] * 3, frame.shape[0] * 3)
    frame = cv2.resize(frame, outsize, interpolation=cv2.INTER_LINEAR)
    imglog.imwrite(
        "upsampled", frame,
        description=(
            "The region of interest scaled up 3x using bilinear "
            "interpolation, as fed to Tesseract.  Upsampling improves OCR "
            "accuracy on small or low-resolution text."
        ),
        source_region=imglog.data.get("region"),
    )
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


_TESSERACT_DEBUG_TEMPLATE = """\
    <style>
        .tsv-block { outline: 4px solid orange; }
        .tsv-paragraph { outline: 3px solid yellow; }
        .tsv-line { outline: 2px solid green; }
        .tsv-word { outline: 1px solid blue; }
        img.img-tessinput { outline: 2px solid #8080ff; }
    </style>
    <h4>{{title}}</h4>

    {{ annotated_image([result] + source_tsv_regions) }}

    {% if match_text %}
    <h5>Result:</h5>
    <pre><code>{{ result | escape }}</code></pre>
    {% endif %}

    <h5>Tesseract output:</h5>
    <pre><code>{{ output | escape }}</code></pre>

    {% if hocr_xml %}
    <h5>HOCR XML:</h5>
    <pre><code>{{ hocr_xml | escape }}</code></pre>
    {% endif %}

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
    {{ img("upsampled") }}
    {% endif %}

    {% if "diff" in images %}
    <h5>Color difference {{ text_color }}:</h5>
    {{ img("diff") }}
    {% endif %}

    {% if "binarized" in images %}
    <h5>
      Color difference – binarised
      (threshold={{ text_color_threshold }}):
    </h5>
    {{ img("binarized") }}
    {% endif %}

    {% if "tessinput" in images %}
    <h5>Tesseract's binarisation:</h5>
    {{ annotated_image(tsv_regions, source_name="tessinput") }}
    {% endif %}
"""


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
