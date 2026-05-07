from __future__ import annotations

import numpy
from numpy.typing import NDArray

from . import _libstbt
from ._libstbt import (
    PIXEL_DEPTH_BGR,
    PIXEL_DEPTH_BGRx,
    PIXEL_DEPTH_BGRA,
)

COLOR_DEPTH_LOOKUP = {
    (3, 3): PIXEL_DEPTH_BGR,
    (4, 3): PIXEL_DEPTH_BGRx,
    (4, 4): PIXEL_DEPTH_BGRA,
}


def sqdiff(template, frame):
    if template.dtype != numpy.uint8 or frame.dtype != numpy.uint8:
        raise NotImplementedError("dtype must be uint8")

    if frame.strides[2] != 1 or template.strides[2] != 1 or \
            frame.strides[1] != 3:
        raise NotImplementedError("Pixel data must be contiguous")

    color_depth = COLOR_DEPTH_LOOKUP[(template.strides[1], template.shape[2])]
    out = _libstbt.sqdiff(template, template.strides[0],
                          frame, frame.strides[0],
                          template.shape[1], template.shape[0], color_depth)
    total, count = out
    return total, count


def threshold_diff_bgr(
        a: NDArray[numpy.uint8],
        b: NDArray[numpy.uint8],
        threshold: int,
) -> NDArray[numpy.uint8]:
    if a.dtype != numpy.uint8 or b.dtype != numpy.uint8:
        raise NotImplementedError("dtype must be uint8")

    if b.strides[2] != 1 or a.strides[2] != 1 or \
            b.strides[1] != 3 or a.strides[1] != 3:
        raise NotImplementedError("Pixel data must be contiguous")

    out = numpy.empty(a.shape[:2], dtype=numpy.uint8)
    _libstbt.threshold_diff_bgr(
        out, a, a.strides[0], b, b.strides[0],
        threshold, a.shape[1], a.shape[0])
    return out
