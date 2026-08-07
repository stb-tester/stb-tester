# Copyright 2016-2018 Stb-tester.com Ltd.

from __future__ import division

import math
import StringIO
from collections import namedtuple

import cv2
import numpy
from _stbt.imgproc_cache import memoize
from _stbt.logging import get_debug_level, ImageLogger
from _stbt.types import Region
from enum import IntEnum


TOP = 0
BOTTOM = 1


class CornerType(IntEnum):
    TOP_LEFT = 0
    BOTTOM_LEFT = 1
    BOTTOM_RIGHT = 2
    TOP_RIGHT = 3

_COLOURS = [(255, 128, 128), (128, 255, 128), (128, 128, 255), (0, 255, 255)]


class _Corner(namedtuple("_Corner", "corner_type x y")):
    @property
    def is_right(self):
        return self.corner_type in [
            CornerType.TOP_RIGHT, CornerType.BOTTOM_RIGHT]

    @property
    def is_left(self):
        return self.corner_type in [
            CornerType.TOP_LEFT, CornerType.BOTTOM_LEFT]


def _pair_up_left_and_right_corners(lefts, rights):
    coords = sorted(lefts + rights, key=lambda c: (c.y, c.x, -c.corner_type))

    if not coords:
        return []
    lines = []
    for a, b in zip(coords[:-1], coords[1:]):
        if a.is_left and b.is_right and a.y == b.y:
            region = Region(x=a.x, y=a.y, right=b.x, height=1)
            lines.append(region)
    return lines


def _pair_up_top_and_bottom_lines(tops, bottoms):
    lines = [(0, l) for l in tops] + [(1, l) for l in bottoms]
    lines.sort(key=lambda l: (l[1].x, l[1].y, -l[0]))
    if not lines:
        return []
    boxes = []
    for t, b in zip(lines[:-1], lines[1:]):
        if (t[0] == TOP and b[0] == BOTTOM and
                t[1].x == b[1].x and t[1].right == b[1].right):
            boxes.append(Region(x=t[1].x, y=t[1].y,
                                right=t[1].right, bottom=b[1].y + 1))
    return boxes


def hash_self_py():
    import hashlib
    with open(__file__) as f:
        h = hashlib.sha256()
        h.update(f.read())
        return h.hexdigest()


def shift(img, pos):
    """
    >>> p = numpy.zeros((5, 5))
    >>> p[2, 2] = 1
    >>> p
    array([[ 0.,  0.,  0.,  0.,  0.],
           [ 0.,  0.,  0.,  0.,  0.],
           [ 0.,  0.,  1.,  0.,  0.],
           [ 0.,  0.,  0.,  0.,  0.],
           [ 0.,  0.,  0.,  0.,  0.]])
    >>> shift(p, (1, 0))
    array([[ 0.,  0.,  0.,  0.,  0.],
           [ 0.,  0.,  0.,  0.,  0.],
           [ 0.,  0.,  0.,  1.,  0.],
           [ 0.,  0.,  0.,  0.,  0.],
           [ 0.,  0.,  0.,  0.,  0.]])
    >>> shift(p, (0, -1))
    array([[ 0.,  0.,  0.,  0.,  0.],
           [ 0.,  0.,  1.,  0.,  0.],
           [ 0.,  0.,  0.,  0.,  0.],
           [ 0.,  0.,  0.,  0.,  0.],
           [ 0.,  0.,  0.,  0.,  0.]])
    """
    if pos[0] != 0:
        img = numpy.roll(img, pos[0], axis=1)
    if pos[1] != 0:
        img = numpy.roll(img, pos[1], axis=0)

    return img


VERT = 0
HORIZ = 1


@memoize({"version": hash_self_py()})
def _find_boxes(frame, min_size, curvature, threshold, connectedness, _debug):
    if _debug >= 2:
        debug_drawing = frame.copy()
        img_logger = ImageLogger("boxes")
        log_html = open(img_logger.outdir + '/index.html', 'w')
        log_html.write("<html><head><title>find_boxes %i</title></head><body>" %
                       img_logger.frame_number)
        log_html.write("""
            <h1>find_boxes</h1>
            <table width="100%%"><tr>
                <td align="left"><a href='../%05di/index.html'>&lt; Prev</a></td>
                <td align="right"><a href='../%05di/index.html'>Next &gt;</a></td>
            </tr></table>
            """ % (img_logger.frame_number - 1, img_logger.frame_number + 1))
    else:
        debug_drawing = None
        img_logger = None
        log_html = StringIO.StringIO()

    dedges = [numpy.ndarray([]), numpy.ndarray([])]
    for direction in [VERT, HORIZ]:
        f16 = frame.astype(numpy.int16)
        tedges = numpy.empty(dtype=numpy.int16, shape=f16.shape)
        if direction == VERT:
            # Fast way to filter with kernel:
            # [ -1 0 1 ]
            tedges[:, 1:-1] = f16[:, 2:] - f16[:, :-2]
            tedges[:, 0] = 255
            tedges[:, -1] = 255
        else:
            # Fast way to filter with kernel:
            #   -1
            # [  0 ]
            #    1
            tedges[1:-1, :] = f16[2:, :] - f16[:-2, :]
            tedges[0, :] = 255
            tedges[-1, :] = 255

        numpy.abs(tedges, out=tedges)
        numpy.clip(tedges, 0, 255, out=tedges)
        tedges = tedges.astype(numpy.uint8)

        if len(tedges.shape) == 3 and tedges.shape[2] == 3:
            tedges = cv2.cvtColor(tedges, cv2.COLOR_BGR2GRAY)

        tedges = cv2.threshold(tedges, threshold / 2. * 255, 255,
                               cv2.THRESH_BINARY)[1]
        tedges = tedges.astype(numpy.float) / 255.
        dedges[direction] = tedges

    # Clean up output removing diagonal edges:
    dedges[VERT], dedges[HORIZ] = (
        dedges[VERT] - dedges[HORIZ],
        dedges[HORIZ] - dedges[VERT])

    # Ugly hack to make matching at the edges work.  Instead we should work out
    # how to pass a "borderValue" argument to filter2d:
    dedges[HORIZ][1, :] = 1
    dedges[HORIZ][-1, :] = 1
    dedges[VERT][:, 1] = 1
    dedges[VERT][:, -1] = 1

    if _debug >= 2:
        dbg = numpy.zeros(frame.shape[:2] + (3,), dtype=numpy.uint8)
        dbg[:, :, 1] = dedges[HORIZ]
        dbg[:, :, 2] = dedges[VERT]
        img_logger.imwrite("edges", dbg * 255)
        log_html.write("<h2>Edges</h2>\n<img src='edges.png'>\n")

    lines_filter = [None, None]
    lines_filter[VERT] = numpy.ones((min_size[1] - curvature, 1)) / (
        min_size[1] - curvature)
    lines_filter[HORIZ] = numpy.ones((1, min_size[0] - curvature)) / (
        min_size[0] - curvature)

    lines = [None, None]
    for direction in [VERT, HORIZ]:
        lines[direction] = cv2.filter2D(
            dedges[direction], ddepth=-1, kernel=lines_filter[direction],
            anchor=(0, 0))
        lines[direction] = lines[direction] > connectedness


    def find_corners(corner):
        if corner in (CornerType.TOP_LEFT, CornerType.TOP_RIGHT):
            v = shift(lines[VERT], (0, -curvature - 1))
        else:
            v = shift(lines[VERT], (0, min_size[1]))

        if corner in (CornerType.TOP_RIGHT, CornerType.BOTTOM_RIGHT):
            h = shift(lines[HORIZ], (min_size[0], 0))
        else:
            h = shift(lines[HORIZ], (-curvature - 1, 0))

        if _debug >= 2:
            print CornerType(corner)
            dbg = numpy.zeros(frame.shape[:2] + (3,), dtype=numpy.uint8)
            dbg[:, :, 0] = (dedges[HORIZ] + dedges[VERT]) * 255 / 2
            dbg[:, :, 1] = h * 255
            dbg[:, :, 2] = v * 255
            if len(frame.shape) == 3 and frame.shape[-1] == 3:
                dbgframe = frame
            else:
                dbgframe = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            dbg[dbg == 0] = dbgframe[dbg == 0] / 2
            log_html.write(
                '<td valign="top"><img width="640px" src="corners-%s.png">\n' % CornerType(corner))
            img_logger.imwrite("corners-%s" % CornerType(corner), dbg)

        nz = cv2.findNonZero((h * v).astype(numpy.uint8))
        if nz is None:
            return []

        corners = [_Corner(corner, c[0], c[1]) for c in nz[:, 0, :]]

        log_html.write('<ol>')
        for corner in corners:
            log_html.write("<li>%r</li>\n" % (corner,))
        log_html.write('</ol></td>\n')
        return corners

    corners = [[], [], [], []]
    log_html.write('<h2>Corners</h2><table width="100%">\n<tr>')
    for n in (CornerType.TOP_LEFT, CornerType.TOP_RIGHT,
              CornerType.BOTTOM_LEFT, CornerType.BOTTOM_RIGHT):
        if n == CornerType.BOTTOM_LEFT:
            log_html.write("</tr>\n<tr>")
        corners[n] = find_corners(n)
        if debug_drawing is not None:
            for c in corners[n]:
                cv2.putText(debug_drawing, "%i, %i" % (c.x, c.y), (c.x, c.y), 0,
                            0.5, _COLOURS[n])
    log_html.write('</tr>\n</table>\n')

    boxes = _pair_up_top_and_bottom_lines(
        _pair_up_left_and_right_corners(
            corners[CornerType.TOP_LEFT], corners[CornerType.TOP_RIGHT]),
        _pair_up_left_and_right_corners(
            corners[CornerType.BOTTOM_LEFT], corners[CornerType.BOTTOM_RIGHT]))

    # No point matching the whole screen:
    whole_screen = Region(
        x=1, y=1, right=frame.shape[1] - 1, bottom=frame.shape[0])
    boxes = [b for b in boxes
             if b.width >= min_size[0] and
             b.height >= min_size[1] and
             b != whole_screen]
    if debug_drawing is not None:
        log_html.write("<h2>Boxes</h2><img src='boxes.png'>")
        if boxes:
            log_html.write("<p>Found %i boxes:</p><ol>" % len(boxes))
            for r in boxes:
                log_html.write("<li>%r</li>" % (r,))
                cv2.rectangle(
                    debug_drawing, (r.x, r.y), (r.right, r.bottom),
                    (32, 0, 255),  # bgr
                    thickness=3)
            log_html.write("</ol>")
        else:
            log_html.write("<p>Found no boxes:</p>")
        img_logger.imwrite("boxes", debug_drawing)

    log_html.write("</body></html>")
    log_html.close()

    return [[int(b.x), int(b.y), int(b.right+1), int(b.bottom)] for b in boxes]


def draw_rounded_rect(img, region, curvature=0, color=(0, 0, 0)):
    for x, y in [
            (region.x + curvature, region.y + curvature),
            (region.right - curvature - 1, region.y + curvature),
            (region.x + curvature, region.bottom - curvature - 1),
            (region.right - curvature - 1, region.bottom - curvature - 1)]:
        cv2.circle(img, (x, y), radius=curvature, thickness=-1, color=color)
    for r in [region.extend(x=curvature, right=-curvature),
              region.extend(y=curvature, bottom=-curvature)]:
        cv2.rectangle(img, (r.x, r.y), (r.right - 1, r.bottom - 1),
                      color=color, thickness=-1)


def selftest_find_boxes(
        region=Region(300, 400, 120, 70), min_size=(60, 40), curvature=0):
    frame = numpy.ones((720, 1280, 3), dtype=numpy.uint8) * 255
    frame[region.y:region.bottom, region.x:region.right] = 0
    bs = find_boxes(min_size=min_size, curvature=curvature, frame=frame)
    assert len(bs) == 1
    print bs[0]
    print region
    assert bs[0] == region

    frame[region.y+5:region.bottom-5, region.x+5:region.right-5] = 255
    bs = find_boxes(frame=frame, min_size=min_size, curvature=curvature)
    assert len(bs) == 2
    print bs
    assert region.extend(x=5, y=5, right=-5, bottom=-5) in bs


def selftest_find_boxes_with_curvature(
        region=Region(300, 400, 120, 70), curvature=10):
    frame = numpy.ones((720, 1280, 3), dtype=numpy.uint8) * 255

    draw_rounded_rect(frame, region, curvature=curvature)

    bs = find_boxes(frame=frame, min_size=(80, 50), curvature=curvature)
    print bs
    assert len(bs) == 1
    assert bs[0] == region


DEFAULT_THRESHOLD = 0.04


def find_boxes(frame=None, min_size=(40, 40), curvature=0,
               threshold=DEFAULT_THRESHOLD,
               connectedness=0.99, region=Region.ALL):
    """
    curvature - For curved boxes - the number of pixels it curves over.
    threshold - Threshold for how strong an edge has to be to be considered an
                edge.  In the range 0-1
    connectedness - What fraction of points along a line have to be edge for it
                    to be considered a line.  In the range 0-1.
    """
    if frame is None:
        import stbt
        frame = stbt.get_frame()

    out = [Region.from_extents(b[0], b[1], b[2], b[3])
           for b in _find_boxes(frame=frame, min_size=min_size,
               curvature=curvature, threshold=threshold,
               connectedness=connectedness, _debug=get_debug_level())]
    return [r for r in out if region.contains(r)]


def find_solid_coloured_boxes(
    padding, min_size=(40, 40), curvature=0, color=None, frame=None,
    threshold=DEFAULT_THRESHOLD, connectedness=0.99):

    if frame is None:
        import stbt
        frame = stbt.get_frame()

    boxes = find_boxes(frame, min_size=min_size, curvature=curvature,
                       threshold=threshold, connectedness=connectedness)

    if color is not None:
        boxes = [
            b for b in boxes if 10 > _color_distance(
                color,
                frame[b[1] + padding[1] - 1, b[0] + padding[0] - 1, :])]

    return boxes


def _color_distance(color, target):
    # Euclidean distance doesn't take into account non-linearity of human
    # visual perception, but it's quick & simple.
    return math.sqrt(
        ((color[0] - target[0]) ** 2 +
         (color[1] - target[1]) ** 2 +
         (color[2] - target[2]) ** 2) / 3)
