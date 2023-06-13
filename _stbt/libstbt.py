from __future__ import annotations

import ctypes
import os
import platform

import numpy


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)


try:
    _libstbt = ctypes.CDLL(_find_file(f"libstbt.{platform.machine()}.so"))
except OSError:
    raise ImportError("Failed to load libstbt.so")


class _SqdiffResult(ctypes.Structure):
    _fields_ = [("total", ctypes.c_uint64),
                ("count", ctypes.c_uint32)]


# SqdiffResult sqdiff(const uint8_t *t, uint16_t t_stride,
#                     const uint8_t *f, uint16_t f_stride,
#                     uint16_t width_px, uint16_t height_px,
#                     int color_depth)

_libstbt.sqdiff.restype = _SqdiffResult
_libstbt.sqdiff.argtypes = [
    ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16,
    ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16,
    ctypes.c_uint16, ctypes.c_uint16,
    ctypes.c_int
]

# void threshold_diff_bgr(
#     uint8_t *out,
#     const uint8_t* a, uint16_t line_stride_a,
#     uint8_t* b, uint16_t line_stride_b,
#     uint32_t threshold_sq,
#     uint16_t width_px, uint16_t height_px
# )
_libstbt.threshold_diff_bgr.argtypes = [
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16,
    ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16,
    ctypes.c_uint32,
    ctypes.c_uint16, ctypes.c_uint16
]

PIXEL_DEPTH_BGR = 1
PIXEL_DEPTH_BGRx = 2
PIXEL_DEPTH_BGRA = 3

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

    t = template.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
    f = frame.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))

    out = _libstbt.sqdiff(t, template.strides[0],
                          f, frame.strides[0],
                          template.shape[1], template.shape[0], color_depth)
    return out.total, out.count


def threshold_diff_bgr(
        a: numpy.ndarray[numpy.uint8], b: numpy.ndarray[numpy.uint8],
        threshold: int) -> numpy.ndarray[numpy.uint8]:
    if a.dtype != numpy.uint8 or b.dtype != numpy.uint8:
        raise NotImplementedError("dtype must be uint8")

    if b.strides[2] != 1 or a.strides[2] != 1 or \
            b.strides[1] != 3 or a.strides[1] != 3:
        raise NotImplementedError("Pixel data must be contiguous")

    out = numpy.empty(a.shape[:2], dtype=numpy.uint8)

    a_array = a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
    b_array = b.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
    out_array = out.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))

    _libstbt.threshold_diff_bgr(
        out_array, a_array, a.strides[0], b_array, b.strides[0],
        threshold, a.shape[1], a.shape[0])
    return out
