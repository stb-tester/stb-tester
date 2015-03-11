#!/usr/bin/python -u
# coding: utf-8
from __future__ import unicode_literals

import argparse
import math
import os
import sys
from collections import namedtuple
from os.path import abspath, dirname

import numpy
from gi.repository import Gst  # pylint: disable=E0611

from _stbt import tv_driver

DATA_DIR = dirname(abspath(__file__))

STANDARD_COLOURS = {
    'letters-bw': ('#ffffff', '#000000'),
    'letters-wb': ('#000000', '#ffffff'),
    'letters-grey': ('#AAAAAA', '#555555'),
    'letters-grey-inv': ('#555555', '#AAAAAA'),
}

Coord = namedtuple('Coord', 'x y')

SQUARES = [Coord(_x, _y) for _y in range(0, 9) for _x in range(0, 16)]
GLYPHS = list(
    'ABCDEFGHIJKLMNOP' +
    'QRSTUVWXYZ012345' +
    '6789abcdefghijkm' +
    'nopqrstuvwxyzΓΔΘ' +
    'ΛΞΠΣΦΨΩαβγδεζηθι' +
    'κλμνξπρςστυφχψωб' +
    'джзйлптфцчшщъыьэ' +
    'юя@#~!£$%+-¶()?[' +
    ']¿÷«»©®℠℗™&<>^/*')


def square_to_pos(square):
    return Coord(square[0] * 80, square[1] * 80)


def distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def off_to_arrow(off):
    """
    >>> print off_to_arrow((1, 1))
    ↗
    >>> print off_to_arrow((-1, 0))
    ←
    """
    arrows = list('→↗↑↖←↙↓↘')
    if numpy.linalg.norm(off) > 0.5:
        angle = math.atan2(off[1], off[0])
        return arrows[int(angle / 2 / math.pi * len(arrows) + len(arrows) + 0.5)
                      % len(arrows)]
    else:
        return 'O'


# ANSI colour codes for printing progress.
OKGREEN = '\033[92m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'


def rate(square, result):
    """How good is the match on a scale of 0-2?"""
    r = distance(square_to_pos(square), result.position)
    if r < 0.5:
        return 2
    elif r < 20:
        return 1
    else:
        return 0


def length(vec):
    return (vec[0] ** 2 + vec[1] ** 2) ** 0.5


def svg_to_array(svg):
    from stbt import _numpy_from_sample
    pipeline = Gst.parse_launch(
        'appsrc name="src" caps="image/svg" ! rsvgdec ! '
        'videoconvert ! appsink caps="video/x-raw,format=BGR" name="sink"')
    src = pipeline.get_by_name('src')
    sink = pipeline.get_by_name('sink')
    pipeline.set_state(Gst.State.PLAYING)
    buf = Gst.Buffer.new_wrapped(svg)
    src.emit('push-buffer', buf)
    sample = sink.emit('pull-sample')
    src.emit("end-of-stream")
    pipeline.set_state(Gst.State.NULL)
    pipeline.get_state(0)
    with _numpy_from_sample(sample, readonly=True) as frame:
        return frame.copy()


def generate_letters_svg(fgcolour, bgcolour):
    from jinja2 import Template

    posns = [(x, y)
             for y in range(60, 720 + 60, 80)
             for x in range(40, 1280 + 40, 80)]
    data = [{'glyph': g, 'x': x, 'y': y} for g, (x, y) in zip(GLYPHS, posns)]

    svg = (Template(open(DATA_DIR + '/glyphs.svg.jinja2', 'r').read())
           .render(glyphs=data, fgcolour=fgcolour, bgcolour=bgcolour)
           .encode('utf-8'))
    return svg


videos = {
    name:
    ('image/svg',
     lambda bg=bg, fg=fg: [(generate_letters_svg(fg, bg), 240 * Gst.SECOND)])
    for name, (fg, bg) in STANDARD_COLOURS.items()}


def validate(video, driver, validate_match=True):
    import stbt

    driver.show(video)

    colours = STANDARD_COLOURS[video]
    pristine = svg_to_array(generate_letters_svg(*colours))

    # Attempt to wait until correct video is showing.
    try:
        # environment variable controls the timeout here as with the
        # fake-video-source with the parallel test runner 10s can not be enough
        timeout = int(os.environ.get('STBT_TEST_VALIDATION_WAIT_TIMEOUT', 10))
        stbt.wait_for_match(pristine[80 * 3:80 * 6, 80 * 6:80 * 10],
                            timeout_secs=timeout)
    except stbt.MatchTimeout:
        pass

    res = []
    for square, char in zip(SQUARES, GLYPHS):
        pos = square_to_pos(square)
        template = pristine[pos.y:pos.y + 80, pos.x:pos.x + 80]
        result = (stbt.detect_match(
            template,
            match_parameters=stbt.MatchParameters(match_method="ccoeff-normed"))
            .next())
        sys.stdout.write(
            "%s%s" % ([FAIL, WARNING, OKGREEN][rate(square, result)], char))
        if square.x == 15:
            sys.stdout.write('\n')
        sys.stdout.flush()
        res.append((square, char, result))
    sys.stdout.write(ENDC)

    sys.stdout.write('\n\n')
    for square, char, result in res:
        expected = square_to_pos(square)
        off = Coord(result.position[0] - expected.x,
                    result.position[1] - expected.y)
        sys.stdout.write(
            "%s%s" % ([FAIL, WARNING, OKGREEN][rate(square, result)],
                      off_to_arrow(off)))
        if square.x == 15:
            sys.stdout.write('\n')
    sys.stdout.write(ENDC)

    if validate_match:
        sys.stdout.write('\n\n')
        for square, char, result in res:
            if result.match:
                rating = 2
            else:
                rating = 1 if result.first_pass_result > 0.9 else 0
            quality = "0123456789"[int(result.first_pass_result * 10)]
            sys.stdout.write(
                "%s%s" % ([FAIL, WARNING, OKGREEN][rating], quality))
            if square.x == 15:
                sys.stdout.write('\n')
        sys.stdout.write(ENDC)

    is_bad = 0
    for square, char, result in res:
        good = rate(square, result) == 2
        if validate_match:
            good = good and result.match

        if not good:
            if is_bad == 0:
                is_bad = 1
                sys.stdout.write('\nChar\tPos\tOffset\tDist\tMatch\n' +
                                 '-' * 40 + '\n')
            expected = square_to_pos(square)
            off = Coord(result.position[0] - expected.x,
                        result.position[1] - expected.y)
            sys.stdout.write('%s%s\t(%i, %i)\t(%i, %i)\t%02f\t%s\n' %
                             ([FAIL, WARNING, OKGREEN][rate(square, result)],
                              char, square.x, square.y, off.x, off.y,
                              distance(expected, result.position),
                              "MATCH" if result.match else "NO MATCH"))
    sys.stdout.write(ENDC)
    sys.stdout.flush()
    return is_bad


def main(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--report-style", choices=['text', 'color-text', 'html'],
        help='Style of report to use',
        default='color-text')
    parser.add_argument(
        '--positions-only', action="store_true",
        help="Only validate that the letters are in their right positions.  "
             "Don't require that they match")
    parser.add_argument(
        '-o', '--output', type=argparse.FileType('w'),
        help='Filename to write the report to')
    tv_driver.add_argparse_argument(parser)

    parser.add_argument("colour", nargs='*')

    args = parser.parse_args(argv[1:])

    if len(args.colour) == 0:
        args.colour = STANDARD_COLOURS.keys()

    driver = tv_driver.create_from_args(args, videos)
    failures = 0
    for c in args.colour:
        failures += validate(c, driver, validate_match=not args.positions_only)
    return failures

if __name__ == '__main__':
    sys.exit(main(sys.argv))
