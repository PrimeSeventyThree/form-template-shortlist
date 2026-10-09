"""Portable OCR: RapidOCR on ONNX Runtime (CPU). Same code on macOS, Linux and Windows; the detection and
recognition models ship inside the pip package, so there is nothing to download or install system-wide."""
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def ocr_lines(img):
    """Text lines of a page image, top to bottom, then left to right within a ~12 px band."""
    result, _ = _engine()(np.asarray(img.convert("RGB")))
    boxes = sorted(result or [], key=lambda r: (round(r[0][0][1] / 12), r[0][0][0]))
    return [text for _box, text, _conf in boxes]
