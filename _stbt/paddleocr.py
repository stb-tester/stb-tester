"""The PaddleOCR engine for `stbt.ocr` and `stbt.match_text`.

This is a separate module so that it can be replaced with a custom GPU
implementation of `PaddleOcrIface`.
"""

import functools
import os

import numpy

from . import imgproc_cache
from .types import PaddleOcrIface


class PaddleOcr(PaddleOcrIface):
    def __init__(self) -> None:
        super().__init__()
        _pipeline()

    def predict(self, img, *, char_whitelist=None):
        if char_whitelist is not None:
            raise ValueError(
                "char_whitelist isn't supported by the paddleocr package")
        r = _predict(img, use_cache=True)  # pylint:disable=unexpected-keyword-arg
        return dict(r, rec_polys=[numpy.array(q) for q in r["rec_polys"]])


@functools.cache
def _pipeline():
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
def _predict(img):
    """`PaddleOcr.predict`, but JSON serialisable (lists instead of numpy
    arrays), so that `imgproc_cache` can store it."""
    r = _pipeline().predict(img, return_word_box=True)[0]
    return {
        "rec_texts": list(r["rec_texts"]),
        "rec_scores": [float(s) for s in r["rec_scores"]],
        "rec_polys": [numpy.asarray(q).tolist() for q in r["rec_polys"]],
        "text_word": [list(w) for w in r["text_word"]],
        "text_word_region": [[numpy.asarray(c).tolist() for c in line]
                             for line in r["text_word_region"]],
    }
