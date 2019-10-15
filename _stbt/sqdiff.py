from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
from builtins import (ascii, chr, filter, hex, input, map, next, oct, open, pow,  # pylint:disable=redefined-builtin,unused-import,wildcard-import,wrong-import-order
                      range, round, super, zip)
import ctypes
import os

import numpy

from .logging import debug


def _find_file(path, root=os.path.dirname(os.path.abspath(__file__))):
    return os.path.join(root, path)


_libstbt = ctypes.CDLL(_find_file("libstbt.so"))


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


PIXEL_DEPTH_BGR = 1
PIXEL_DEPTH_BGRx = 2
PIXEL_DEPTH_BGRA = 3

COLOR_DEPTH_LOOKUP = {
    (3, 3): PIXEL_DEPTH_BGR,
    (4, 3): PIXEL_DEPTH_BGRx,
    (4, 4): PIXEL_DEPTH_BGRA,
}


def sqdiff(template, frame):
    if template.shape[:2] != frame.shape[:2]:
        raise ValueError("Template and frame must be the same size")
    try:
        return _sqdiff_c(template, frame)
    except NotImplementedError as e:
        debug("sqdiff Missed fast-path: %s" % e)
        return _sqdiff_numpy(template, frame)


def _sqdiff_c(template, frame):
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


def _sqdiff_numpy(template, frame):
    template = template.astype(numpy.int64)
    frame = frame.astype(numpy.int64)
    if template.shape[2] == 4:
        # Masked
        x = ((template[:, :, :3] - frame) ** 2)[template[:, :, 3] == 255]
    else:
        x = (template - frame) ** 2
    return numpy.sum(x), x.size


def _random_template(size=(1280, 720)):
    tsize = (numpy.random.randint(1, size[0] + 1),
             numpy.random.randint(1, size[1] + 1))
    toff = (numpy.random.randint(size[0] - tsize[0] + 1),
            numpy.random.randint(size[1] - tsize[1] + 1))

    f = numpy.random.randint(0, 256, (size[1], size[0], 3),
                             dtype=numpy.uint8)
    t = numpy.random.randint(0, 256, (tsize[1], tsize[0], 3),
                             dtype=numpy.uint8)
    tt = numpy.random.randint(0, 256, (tsize[1], tsize[0], 4),
                              dtype=numpy.uint8)
    mask = tt[:, :, 3]
    mask[mask & 1 == 1] = 255
    mask[mask < 255] = 0

    f_cropped = f[toff[1]:toff[1] + tsize[1], toff[0]:toff[0] + tsize[0], :]
    return f_cropped, t, tt


def test_sqdiff():
    f = numpy.array(range(1280 * 720 * 3), dtype=numpy.uint8)
    f.shape = (720, 1280, 3)
    t = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    tt = numpy.zeros((720, 1280, 4), dtype=numpy.uint8)
    t[:, :, :] = f
    tt[:, :, :3] = f
    tt[:, :, 3] = 255

    assert (0, 1280 * 720 * 3) == _sqdiff_c(t, f)
    assert (0, 1280 * 720 * 3) == _sqdiff_c(tt, f)
    assert (0, 1280 * 720 * 3) == _sqdiff_c(tt[:, :, :3], f)

    f = numpy.ones((720, 1280, 3), dtype=numpy.uint8) * 255
    t = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    tt = numpy.zeros((720, 1280, 4), dtype=numpy.uint8)

    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == _sqdiff_c(t, f)
    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == _sqdiff_c(t, f)
    assert (0, 0) == _sqdiff_c(tt, f)

    tt[:, :, 3] = 255
    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == _sqdiff_c(t, f)
    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == _sqdiff_c(t, f)
    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == _sqdiff_c(tt, f)


def test_sqdiff_c_numpy_equivalence():
    for _ in range(100):
        frame_cropped, template, template_transparent = _random_template()

        for t in (template, template_transparent,
                  template_transparent[:, :, :3]):
            assert (_sqdiff_numpy(t, frame_cropped) ==
                    _sqdiff_c(t, frame_cropped))


def _make_sqdiff_numba():
    # numba implementation included for the purposes of comparison.
    try:
        import numba
    except ImportError:
        return None

    def _sqdiff_numba(template, frame):
        if template.shape[2] == 3:
            return _sqdiff_numba_nomask(template, frame)
        else:
            return _sqdiff_numba_masked(template, frame)

    @numba.jit(nopython=True, nogil=True)
    def _sqdiff_numba_nomask(template, frame):
        cum = 0
        s = template.shape
        for i in range(s[0]):
            for j in range(s[1]):
                for k in range(s[2]):
                    cum += (template[i, j, k] - frame[i, j, k]) ** 2
        return cum, frame.size

    @numba.jit(nopython=True, nogil=True)
    def _sqdiff_numba_masked(template, frame):
        # mask is either 0 or 255
        cum = 0
        maskcount = 0
        s = template.shape
        for i in range(s[0]):
            for j in range(s[1]):
                if template[i, j, 3] == 255:
                    for k in range(s[2]):
                        cum += (template[i, j, k] - frame[i, j, k]) ** 2
                    maskcount += 1
        return cum, maskcount * 3

    return _sqdiff_numba


def _measure_performance():
    import timeit

    _sqdiff_numba = _make_sqdiff_numba()

    print("All times in ms                         numpy\tnumba")
    print("type    \tnumpy\tnumba\tC\tspeedup\tspeedup\tsize\talignment")
    for _ in range(100):
        frame_cropped, template, template_transparent = _random_template()

        for l, t in [("template ", template),
                     ("with mask", template_transparent),
                     ("unmasked ", template_transparent[:, :, :3])]:
            # pylint: disable=cell-var-from-loop

            np_time = min(timeit.repeat(
                lambda: _sqdiff_numpy(t, frame_cropped),
                repeat=3, number=10)) / 10
            c_time = min(timeit.repeat(
                lambda: _sqdiff_c(t, frame_cropped),
                repeat=3, number=10)) / 10
            if _sqdiff_numba:
                numba_time = min(timeit.repeat(
                    lambda: _sqdiff_numba(t, frame_cropped),
                    repeat=3, number=10)) / 10
            else:
                numba_time = float('nan')
            print("%s\t%.2f\t%.2f\t%.2f\t%.2f\t%.2f\t%i x %i \t%s" % (
                l, np_time * 1000, numba_time * 1000, c_time * 1000,
                np_time / c_time, numba_time / c_time,
                frame_cropped.shape[1], frame_cropped.shape[0],
                frame_cropped.ctypes.data % 8))
