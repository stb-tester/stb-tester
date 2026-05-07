#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <assert.h>

enum PixelDepth {
    PIXEL_DEPTH_U8 = 0,
    PIXEL_DEPTH_BGR = 1,
    PIXEL_DEPTH_BGRx = 2,
    PIXEL_DEPTH_BGRA = 3,
};

static uint32_t sqdiff_U8(
    const unsigned char* a, const unsigned char* b,
    uint16_t len_px);
static uint32_t sqdiff_BGRx(
    const unsigned char* t, const unsigned char* f,
    uint16_t len_px);
static uint32_t sqdiff_BGRA(
    uint32_t *count,
    const unsigned char* t, const unsigned char* f,
    uint16_t len_px);
static void threshold_diff_BGR_line(
    uint8_t *out, const uint8_t* a, uint8_t* b,
    uint16_t len_px, uint32_t threshold_sq
);

typedef struct _SqdiffResult {
    uint64_t total;
    uint32_t count;
} SqdiffResult;

/* Computes the square difference between template t and frame f and counts
 * the number of pixels not masked.
 *
 * color_depth indicates the layout of t in memory:
 *
 *                        template layout       frame layout
 * PIXEL_DEPTH_U8         U8                    U8
 * PIXEL_DEPTH_BGR        BGR                   BGR
 * PIXEL_DEPTH_BGRx       BGRx                  BGR
 * PIXEL_DEPTH_BGRA       BGRA                  BGR
 *
 * t_stride and f_stride are the strides between lines measured in bytes for
 * t and f respectively.
 *
 * Returns a struct with the total square difference and count of
 * non-transparent pixels.
 */
SqdiffResult sqdiff(const uint8_t *t, uint16_t t_stride,
                    const uint8_t *f, uint16_t f_stride,
                    uint16_t width_px, uint16_t height_px,
                    int color_depth)
{
    assert(width_px > 0 && height_px > 0);

    SqdiffResult out = {0, 0};

    switch (color_depth) {
    case PIXEL_DEPTH_U8:
        assert(f_stride >= width_px && t_stride >= width_px);
        out.count = width_px * height_px;
        for (uint16_t y = 0; y < height_px; y++)
            out.total += sqdiff_U8(
                t + y * t_stride, f + y * f_stride, width_px);
        break;
    case PIXEL_DEPTH_BGR:
        assert(f_stride >= width_px * 3 && t_stride >= width_px * 3);
        out.count = width_px * height_px * 3;
        for (uint16_t y = 0; y < height_px; y++)
            out.total += sqdiff_U8(
                t + y * t_stride, f + y * f_stride, width_px * 3);
        break;
    case PIXEL_DEPTH_BGRx:
        assert(f_stride >= width_px * 3 && t_stride >= width_px * 4);
        out.count = width_px * height_px * 3;
        for (uint16_t y = 0; y < height_px; y++)
            out.total += sqdiff_BGRx(
                t + y * t_stride, f + y * f_stride, width_px);
        break;
    case PIXEL_DEPTH_BGRA:
        assert(f_stride >= width_px * 3 && t_stride >= width_px * 4);
        out.count = 0;
        for (uint16_t y = 0; y < height_px; y++)
            out.total += sqdiff_BGRA(
                &out.count, t + y * t_stride, f + y * f_stride, width_px);
        out.count *= 3;
        break;
    default:
        assert(0);
    }
    return out;
}

static uint32_t sqdiff_U8(const unsigned char* a, const unsigned char* b,
                          uint16_t len)
{
    uint32_t this_total = 0;
    for (uint16_t n = 0; n < len; n++) {
        int16_t diff = a[n] - b[n];
        uint16_t sqdiff = diff * diff;
        this_total += sqdiff;
    }
    return this_total;
}

static uint32_t sqdiff_BGRx(const unsigned char* t, const unsigned char* f,
                            uint16_t len)
{
    uint32_t this_total = 0;
    for (uint16_t n = 0; n < len; n++) {
        int16_t diff_b = t[0] - f[0];
        int16_t diff_g = t[1] - f[1];
        int16_t diff_r = t[2] - f[2];
        uint32_t sqdiff = diff_b * diff_b + diff_g * diff_g + diff_r * diff_r;
        this_total += sqdiff;
        t += 4;
        f += 3;
    }
    return this_total;
}

static uint32_t sqdiff_BGRA(uint32_t *count,
                            const unsigned char* t, const unsigned char* f,
                            uint16_t len)
{
    uint32_t this_total = 0;
    uint16_t this_count = 0;
    for (uint16_t n = 0; n < len; n++) {
        int16_t diff_b = t[0] - f[0];
        int16_t diff_g = t[1] - f[1];
        int16_t diff_r = t[2] - f[2];
        uint16_t diff_b2 = diff_b * diff_b;
        uint16_t diff_g2 = diff_g * diff_g;
        uint16_t diff_r2 = diff_r * diff_r;
        uint32_t sqdiff = diff_b2 + diff_g2 + diff_r2;
        uint8_t present = (t[3] == 255) ? 1 : 0;
        this_total += sqdiff * present;
        this_count += present;
        t += 4;
        f += 3;
    }
    *count += this_count;
    return this_total;
}

/**
 * Calculate the square difference between two images, thresholded by a
 * threshold_sq value.  Writes the result to out.
 *
 * a and b are pointers to the first pixel of the first line of the images.
 * The images are assumed to be stored in packed BGR format.
 *
 * line_stride_a and line_stride_b are the number of bytes between the start
 * of one line and the start of the next for a and b respectively.
 *
 * width_px and height_px are the width and height of the images in pixels.
 *
 * threshold_sq is the square of the threshold value.  If the square difference
 * between two pixels is greater than this value, the output pixel will be 1,
 * otherwise it will be 0.
 *
 * out is a pointer to the first pixel of the first line of the output image.
 * The memory area for this image must be at least width_px * height_px bytes.
 */
void threshold_diff_bgr(
    uint8_t *out,
    const uint8_t* a, uint16_t line_stride_a,
    uint8_t* b, uint16_t line_stride_b,
    uint32_t threshold_sq,
    uint16_t width_px, uint16_t height_px
)
{
    for (uint16_t y = 0; y < height_px; y++) {
        threshold_diff_BGR_line(out, a, b, width_px, threshold_sq);
        a += line_stride_a;
        b += line_stride_b;
        out += width_px;
    }
}

static void threshold_diff_BGR_line(
    uint8_t *out,
    const uint8_t* a, uint8_t* b,
    uint16_t len_px,
    uint32_t threshold_sq
)
{
    for (uint16_t n = 0; n < len_px; n++) {
        int16_t diff_b = a[0] - b[0];
        int16_t diff_g = a[1] - b[1];
        int16_t diff_r = a[2] - b[2];
        uint32_t sqdiff = diff_b * diff_b + diff_g * diff_g + diff_r * diff_r;
        uint8_t present = (sqdiff >= threshold_sq) ? 1 : 0;
        out[0] = present;
        a += 3;
        b += 3;
        out += 1;
    }
}

/* ================= Python bindings ================= */

static PyObject *
py_sqdiff(PyObject *self, PyObject *args)
{
    PyObject *t_obj, *f_obj;
    Py_buffer t, f;
    int t_stride, f_stride, width, height, depth;

    if (!PyArg_ParseTuple(
            args, "OiOiiii",
            &t_obj, &t_stride,
            &f_obj, &f_stride,
            &width, &height,
            &depth))
        return NULL;

    if (PyObject_GetBuffer(t_obj, &t, PyBUF_STRIDES) < 0)
        return NULL;

    if (PyObject_GetBuffer(f_obj, &f, PyBUF_STRIDES) < 0)
        return NULL;

    SqdiffResult r = sqdiff(
        t.buf, t_stride,
        f.buf, f_stride,
        width, height,
        depth);

    PyBuffer_Release(&t);
    PyBuffer_Release(&f);

    return Py_BuildValue("KI", r.total, r.count);
}

static PyObject *
py_threshold_diff_bgr(PyObject *self, PyObject *args)
{
    Py_buffer out, a, b;
    PyObject *out_obj, *a_obj, *b_obj;
    int stride_a, stride_b, width, height;
    unsigned int threshold_sq;

    if (!PyArg_ParseTuple(
            args, "OOiOiIii",
            &out_obj,
            &a_obj, &stride_a,
            &b_obj, &stride_b,
            &threshold_sq,
            &width, &height))
        return NULL;

    if (PyObject_GetBuffer(out_obj, &out, PyBUF_WRITABLE | PyBUF_C_CONTIGUOUS) < 0)
        return NULL;

    if (PyObject_GetBuffer(a_obj, &a, PyBUF_STRIDES) < 0)
        return NULL;

    if (PyObject_GetBuffer(b_obj, &b, PyBUF_STRIDES) < 0)
        return NULL;

    threshold_diff_bgr(
        out.buf,
        a.buf, stride_a,
        b.buf, stride_b,
        threshold_sq,
        width, height);

    PyBuffer_Release(&out);
    PyBuffer_Release(&a);
    PyBuffer_Release(&b);

    Py_RETURN_NONE;
}

/* ================= Module definition ================= */

static PyMethodDef methods[] = {
    {"sqdiff", py_sqdiff, METH_VARARGS, "Computes the square difference between template t and frame f and counts the number of pixels not masked."},
    {"threshold_diff_bgr", py_threshold_diff_bgr, METH_VARARGS, "Calculate the square difference between two images, thresholded by a threshold_sq value. Writes the result to out."},
    {NULL, NULL, 0, NULL}
};

PyMODINIT_FUNC
PyInit__libstbt(void)
{
    static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        .m_name = "_libstbt",
        .m_doc = NULL,
        -1,
        .m_size = -1,
        .m_methods = methods,
    };

    PyObject *module = PyModule_Create(&moduledef);
    if (!module) {
        return NULL;
    }

    PyModule_AddIntConstant(module, "PIXEL_DEPTH_U8", PIXEL_DEPTH_U8);
    PyModule_AddIntConstant(module, "PIXEL_DEPTH_BGR", PIXEL_DEPTH_BGR);
    PyModule_AddIntConstant(module, "PIXEL_DEPTH_BGRx", PIXEL_DEPTH_BGRx);
    PyModule_AddIntConstant(module, "PIXEL_DEPTH_BGRA", PIXEL_DEPTH_BGRA);

    return module;
}
