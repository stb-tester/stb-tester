"""The PaddleOCR engine for `stbt.ocr` and `stbt.match_text`.

This is a separate module so that it can be replaced with a custom GPU
implementation of `PaddleOcrIface`.
"""

import os

from .types import PaddleOcrIface


class PaddleOcr(PaddleOcrIface):
    def __init__(self) -> None:
        super().__init__()
        # Otherwise PaddleOCR checks the connectivity to all the model hosting
        # sites every time it starts up:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PaddleOCR  # pylint:disable=import-error
        except ImportError as e:
            raise RuntimeError(
                "The PaddleOCR engine requires the paddleocr and onnxruntime "
                "Python packages: %s" % e) from e
        self._pipeline = PaddleOCR(
            engine="onnxruntime",
            text_detection_model_name="PP-OCRv6_small_det",
            text_recognition_model_name="PP-OCRv6_small_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False)

    def predict(self, img, *, char_whitelist=None):
        if char_whitelist is not None:
            raise ValueError(
                "char_whitelist isn't supported by the paddleocr package")
        return self._pipeline.predict(img, return_word_box=True)[0]
