from __future__ import annotations

import dataclasses
import functools
import os
import re
from typing import Optional, TypeAlias

import cv2
import numpy

from . import imgproc_cache
from .imgutils import Color, crop, FrameT
from .logging import ImageLogger
from .ocr import (
    CommonArgs,
    CorrectionsT,
    find_phrase,
    ocr_postprocess,
    TextMatchResult,
)
from .types import PositionT, Region
from .utils import to_unicode


Quad: TypeAlias = tuple[PositionT, PositionT, PositionT, PositionT]


@dataclasses.dataclass
class PaddleOcrWord:
    """One of PaddleOCR's "words" in a `PaddleOcrLine`."""
    text: str
    quad: Quad  # its corners


@dataclasses.dataclass
class PaddleOcrLine:
    """A line of text that PaddleOCR found. Like an element of
    `rec_texts`, `rec_scores`, `rec_polys`, `text_word` & `text_word_region`
    in `paddleocr.PaddleOCR.predict(img, return_word_box=True)[0]`, but
    plain Python types, not numpy arrays.

    Corners are (x, y) pixel coordinates: top-left, top-right, bottom-right,
    bottom-left.
    """
    text: str
    score: float  # the mean probability of its characters
    quad: Quad  # its corners
    words: list[PaddleOcrWord]


def ocr_paddleocr(
    common_args: CommonArgs,
    corrections: Optional[CorrectionsT],
) -> str:
    imglog = ImageLogger("ocr", result=None)
    lines = _paddleocr(common_args, imglog)
    text = ocr_postprocess(lines_to_text(lines), corrections)
    imglog.html(_PADDLEOCR_DEBUG_TEMPLATE, match_text=False, output=text,
                title="stbt.ocr")
    return text


def match_text_paddleocr(
    text: str,
    common_args: CommonArgs,
    case_sensitive: bool,
) -> TextMatchResult:
    imglog = ImageLogger("match_text")
    lines = _paddleocr(common_args, imglog)
    result = match_text_result(text, common_args.frame, lines, case_sensitive)
    imglog.html(
        _PADDLEOCR_DEBUG_TEMPLATE,
        match_text=True, text=text, case_sensitive=case_sensitive,
        result=result, output=lines_to_text(lines),
        title="stbt.match_text(%r): %s" % (
            text, "Matched" if result else "Didn't match"))
    return result


def _paddleocr(
        common_args: CommonArgs,
        imglog: ImageLogger,
) -> list[TextLine]:
    imglog.imwrite("frame", common_args.frame)
    imglog.set(region=common_args.region, common_args=common_args)

    frame = crop(common_args.frame, common_args.region)
    if (text_color := common_args.text_color) is not None:
        text_color_threshold = common_args.text_color_threshold
        assert text_color_threshold is not None
        # Unlike Tesseract, we don't binarise the image.
        d = numpy.subtract(frame, Color(text_color).array, dtype=numpy.int32)
        d = numpy.sqrt((d ** 2).sum(axis=2) / 3)
        frame = numpy.clip(d * (255 / text_color_threshold), 0, 255) \
            .astype(numpy.uint8)
        imglog.imwrite(
            "diff", frame,
            description=(
                f"The distance of each pixel from the specified text_color "
                f"({text_color!r}); white pixels are further away than "
                f"text_color_threshold ({text_color_threshold})."),
            source_region=imglog.data.get("region"))
    if frame.ndim == 2 or frame.shape[2] == 1:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    frame = numpy.ascontiguousarray(frame[:, :, :3])
    return postprocess(
        _predict(frame, common_args.char_whitelist), common_args.region,
        imglog)


def _predict(frame: FrameT, char_whitelist: str | None) -> list[PaddleOcrLine]:
    """The lines of text in `frame`, top-to-bottom & left-to-right."""
    if char_whitelist is not None:
        raise ValueError(
            "char_whitelist isn't supported by the paddleocr package")
    r = _pypi_predict(frame, use_cache=True)  # pylint:disable=unexpected-keyword-arg
    return [
        PaddleOcrLine(text, score, _quad(quad),
                      [PaddleOcrWord(w, _quad(q))
                       for w, q in zip(words, quads)])
        for text, score, quad, words, quads in zip(
            r["rec_texts"], r["rec_scores"], r["rec_polys"],
            r["text_word"], r["text_word_region"])]


def postprocess(
        predictions: list[PaddleOcrLine],
        region: Region,
        imglog: ImageLogger,
) -> list[TextLine]:
    """The lines of text that the engine read from `region`, in the frame's
    coordinates."""
    dx = max(0, region.x)
    dy = max(0, region.y)
    lines = [
        TextLine(
            line.text, line.score,
            _quad([[x + dx, y + dy] for x, y in line.quad]),
            [(w, box.translate(dx, dy))
             for w, box in _paddleocr_words(line.words, line.quad)])
        for line in predictions
        if line.text.strip()]
    if imglog.enabled:
        imglog.set(source_tsv_regions=[
            (box, "tsv-word", "%s (%.2f)" % (word, line.score))
            for line in lines for word, box in line.words])
    return lines


def match_text_result(
        text: str,
        frame: FrameT,
        lines: list[TextLine],
        case_sensitive: bool,
) -> TextMatchResult:
    rts = getattr(frame, "time", None)
    p = find_phrase(
        [w for line in lines for w in line.words],
        to_unicode(text).split(), case_sensitive)
    if p:
        box = Region.bounding_box(*[r for _, r in p])
        result = TextMatchResult(rts, True, box, frame, text)
    else:
        result = TextMatchResult(rts, False, None, frame, text)
    return result


def paddleocr_lines_from_json(lines: list[dict]) -> list[PaddleOcrLine]:
    """The inverse of `[dataclasses.asdict(x) for x in lines]` after a round
    trip through JSON (which has no tuples), e.g. from `imgproc_cache`."""
    return [
        PaddleOcrLine(x["text"], x["score"], _quad(x["quad"]),
                      [PaddleOcrWord(w["text"], _quad(w["quad"]))
                       for w in x["words"]])
        for x in lines]


def _quad(corners: list[list[int]]) -> Quad:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners
    return ((x0, y0), (x1, y1), (x2, y2), (x3, y3))


@dataclasses.dataclass
class TextLine:
    """A line of text, with its whitespace-separated words."""
    text: str
    score: float  # the mean probability of its characters
    quad: Quad  # its corners
    words: list[tuple[str, Region]]


def _paddleocr_words(
        tokens: list[PaddleOcrWord], quad: Quad) -> list[tuple[str, Region]]:
    """Convert PaddleOCR's word boxes to boxes for whitespace-separated words.

    PaddleOCR's "words" are runs of letters & digits, individual CJK
    characters, or runs of other characters (including spaces). Their boxes'
    horizontal extents are good, but their vertical extents come from two
    corners of the line's `quad`, which coincide if it's rotated, so we use
    the line's.
    """
    spans = []
    end = 0
    for token in tokens:
        xs = [x for x, _ in token.quad]
        start, end = end, end + len(token.text)
        spans.append((start, end, min(xs), max(xs)))
    ys = [y for _, y in quad]
    words = []
    for m in re.finditer(r"\S+", "".join(t.text for t in tokens)):
        spans_ = [(x0, x1) for start, end, x0, x1 in spans
                  if start < m.end() and end > m.start()]
        words.append((m.group(), Region.from_extents(
            int(min(x0 for x0, _ in spans_)), int(min(ys)),
            int(max(x1 for _, x1 in spans_)), int(max(ys)))))
    return words


def lines_to_text(lines: list[TextLine]) -> str:
    """Join the lines that are side-by-side with a space."""
    rows: list[tuple[float, list[TextLine]]] = []
    for line in lines:
        ys = [y for _, y in line.quad]
        y, h = (min(ys) + max(ys)) / 2, max(ys) - min(ys)
        if rows and abs(y - rows[-1][0]) < h / 2:
            rows[-1][1].append(line)
        else:
            rows.append((y, [line]))
    return "\n".join(
        " ".join(line.text
                 for line in sorted(row, key=lambda line: line.quad[0][0]))
        for _, row in rows)


_PADDLEOCR_DEBUG_TEMPLATE = """\
    <style>
        .tsv-word { outline: 1px solid blue; }
    </style>
    <h4>{{title}}</h4>

    {{ annotated_image([result] + source_tsv_regions) }}

    {% if match_text %}
    <h5>Result:</h5>
    <pre><code>{{ result | escape }}</code></pre>
    {% endif %}

    <h5>PaddleOCR output:</h5>
    <pre><code>{{ output | escape }}</code></pre>

    <h5>Parameters:</h5>
    <ul>
      {% if match_text %}
      <li>case_sensitive={{case_sensitive}}
      {% endif %}
      <li>char_whitelist={{common_args.char_whitelist}}
      <li>engine={{common_args.engine}}
      {% if match_text %}
      <li>text={{text}}
      {% endif %}
      <li>text_color={{common_args.text_color}}
      <li>text_color_threshold={{common_args.text_color_threshold}}
    </ul>

    {% if "diff" in images %}
    <h5>Color difference {{ common_args.text_color }}:</h5>
    {{ img("diff") }}
    {% endif %}
"""


@functools.cache
def _pypi_pipeline():
    # Otherwise PaddleOCR checks the connectivity to all the model hosting
    # sites every time it starts up:
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        from paddleocr import PaddleOCR  # pylint:disable=import-error
    except ImportError as e:
        raise RuntimeError(
            "The PaddleOCR engine requires the paddleocr and onnxruntime "
            "Python packages: %s" % e) from e
    return PaddleOCR(
        engine="onnxruntime",
        text_detection_model_name="PP-OCRv6_small_det",
        text_recognition_model_name="PP-OCRv6_small_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False)


@imgproc_cache.memoize(
    {"version": "34", "det": "PP-OCRv6_small", "rec": "PP-OCRv6_small"})
def _pypi_predict(img):
    """`paddleocr.PaddleOCR.predict`, but JSON serialisable (lists instead of
    numpy arrays), so that `imgproc_cache` can store it."""
    r = _pypi_pipeline().predict(img, return_word_box=True)[0]
    return {
        "rec_texts": list(r["rec_texts"]),
        "rec_scores": [float(s) for s in r["rec_scores"]],
        "rec_polys": [numpy.asarray(q).tolist() for q in r["rec_polys"]],
        "text_word": [list(w) for w in r["text_word"]],
        "text_word_region": [[numpy.asarray(c).tolist() for c in line]
                             for line in r["text_word_region"]],
    }
