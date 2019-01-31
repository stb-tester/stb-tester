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
 * total and count are out arguments.  This is the total square difference and
 * count of non-transparent pixels.
 */
void sqdiff(uint64_t *total, uint32_t *count,
            const uint8_t *t, uint16_t t_stride,
            const uint8_t *f, uint16_t f_stride,
            uint16_t width_px, uint16_t height_px,
            int color_depth)
{
    assert(width_px > 0 && height_px > 0);
    assert(total && count);

    uint64_t this_total = 0;
    uint32_t this_count;

    switch (color_depth) {
    case PIXEL_DEPTH_U8:
        assert(f_stride >= width_px && t_stride >= width_px);
        this_count = width_px * height_px;
        for (uint16_t y = 0; y < height_px; y++)
            this_total += sqdiff_U8(
                t + y * t_stride, f + y * f_stride, width_px);
        break;
    case PIXEL_DEPTH_BGR:
        assert(f_stride >= width_px * 3 && t_stride >= width_px * 3);
        this_count = width_px * height_px * 3;
        for (uint16_t y = 0; y < height_px; y++)
            this_total += sqdiff_U8(
                t + y * t_stride, f + y * f_stride, width_px * 3);
        break;
    case PIXEL_DEPTH_BGRx:
        assert(f_stride >= width_px * 3 && t_stride >= width_px * 4);
        this_count = width_px * height_px * 3;
        for (uint16_t y = 0; y < height_px; y++)
            this_total += sqdiff_BGRx(
                t + y * t_stride, f + y * f_stride, width_px);
        break;
    case PIXEL_DEPTH_BGRA:
        assert(f_stride >= width_px * 3 && t_stride >= width_px * 4);
        this_count = 0;
        for (uint16_t y = 0; y < height_px; y++)
            this_total += sqdiff_BGRA(
                &this_count, t + y * t_stride, f + y * f_stride, width_px);
        this_count *= 3;
        break;
    default:
        assert(0);
    }
    *total = this_total;
    *count = this_count;
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
