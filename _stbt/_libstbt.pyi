"""Stub interface for _libstbt."""

import numpy
from numpy.typing import NDArray 

SqdiffResult = tuple[int, int]

PIXEL_DEPTH_U8: int
PIXEL_DEPTH_BGR: int
PIXEL_DEPTH_BGRx: int
PIXEL_DEPTH_BGRA: int


def sqdiff(
    template:  NDArray[numpy.uint8],
    template_stride: int,
    frame: NDArray[numpy.uint8],
    frame_stride: int,
    width: int,
    height: int,
    color_depth: int,
) -> SqdiffResult: ...


def threshold_diff_bgr(
    out: NDArray[numpy.uint8],
    a: NDArray[numpy.uint8],
    stride_a: int,
    b: NDArray[numpy.uint8],
    stride_b: int,
    threshold: int,
    width: int,
    height: int,
) -> NDArray[numpy.uint8]: ...
