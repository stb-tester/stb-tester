import numpy

from .logging import debug


def sqdiff(template, frame) -> "tuple[int, int]":
    if template.shape[:2] != frame.shape[:2]:
        raise ValueError("Template and frame must be the same size")
    try:
        from . import libstbt
        return libstbt.sqdiff(template, frame)
    except (ImportError, NotImplementedError) as e:
        debug("sqdiff Missed fast-path: %s" % e)
        return _sqdiff_numpy(template, frame)


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
    from .libstbt import sqdiff as sqdiff_c
    f = numpy.array(range(1280 * 720 * 3), dtype=numpy.uint8)
    f.shape = (720, 1280, 3)
    t = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    tt = numpy.zeros((720, 1280, 4), dtype=numpy.uint8)
    t[:, :, :] = f
    tt[:, :, :3] = f
    tt[:, :, 3] = 255

    assert (0, 1280 * 720 * 3) == sqdiff_c(t, f)
    assert (0, 1280 * 720 * 3) == sqdiff_c(tt, f)
    assert (0, 1280 * 720 * 3) == sqdiff_c(tt[:, :, :3], f)

    f = numpy.ones((720, 1280, 3), dtype=numpy.uint8) * 255
    t = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    tt = numpy.zeros((720, 1280, 4), dtype=numpy.uint8)

    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == sqdiff_c(t, f)
    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == sqdiff_c(t, f)
    assert (0, 0) == sqdiff_c(tt, f)

    tt[:, :, 3] = 255
    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == sqdiff_c(t, f)
    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == sqdiff_c(t, f)
    assert (1280 * 720 * 255 * 255 * 3, 1280 * 720 * 3) == sqdiff_c(tt, f)


def test_sqdiff_c_numpy_equivalence():
    from .libstbt import sqdiff as sqdiff_c
    for _ in range(100):
        frame_cropped, template, template_transparent = _random_template()

        for t in (template, template_transparent,
                  template_transparent[:, :, :3]):
            assert (_sqdiff_numpy(t, frame_cropped) ==
                    sqdiff_c(t, frame_cropped))


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
    from .libstbt import sqdiff as sqdiff_c

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
                lambda: sqdiff_c(t, frame_cropped),
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
