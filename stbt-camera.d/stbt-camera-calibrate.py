#!/usr/bin/python -u
# Encoding: utf-8
# pylint: disable=W0212

import math
import sys
import time
from collections import namedtuple
from itertools import count
from os.path import dirname

import cv2
import numpy

import stbt
from _stbt import tv_driver
from _stbt.config import set_config

videos = {}

#
# Geometric calibration
#

videos['chessboard'] = ('image/png', lambda: [(
    open('%s/chessboard-720p-40px-border-white.png' % dirname(__file__))
    .read(), 60 * Gst.SECOND)])

arrows = list(u'→↗↑↖←↙↓↘')


def off_to_arrow(off):
    u"""
    >>> print off_to_arrow((1, 1))
    ↗
    >>> print off_to_arrow((-1, 0))
    ←
    """
    if numpy.linalg.norm(off) > 0.5:
        angle = math.atan2(off[1], off[0])
        return arrows[int(angle / 2 / math.pi * len(arrows) + len(arrows) + 0.5)
                      % len(arrows)]
    else:
        return u'O'


# ANSI colour codes for printing progress.
OKGREEN = '\033[92m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'
BOLD = '\033[1m'


def rate(r):
    """How good is the match on a scale of 0-2?"""
    if r < 0.5:
        return 2
    elif r < 5:
        return 1
    else:
        return 0


def print_error_map(outstream, ideal_points, measured_points):
    oldx = 0.0
    outstream.write(
        BOLD + "Geometric Calibration Report:\n" + ENDC +
        "\n"
        "    Legend:\n"
        "        " + OKGREEN + "O" + ENDC + " - Pixel perfect\n"
        "        " + WARNING + "↗" + ENDC + " - Off by up-to 5 pixels\n"
        "        " + FAIL + "↗" + ENDC + " - Off by more than 5 pixels\n"
        "\n")
    for ideal, measured in sorted(zip(ideal_points, measured_points),
                                  key=lambda a: (-a[0][1], a[0][0])):
        if ideal[0] < oldx:
            outstream.write('\n')
        off = ideal - measured
        outstream.write(
            (u"%s%s" % ([FAIL, WARNING, OKGREEN][rate(numpy.linalg.norm(off))],
                        off_to_arrow(off)))
            .encode('utf-8'))
        oldx = ideal[0]
    outstream.write("\n" + ENDC)


def validate_transformation(measured_points, ideal_points, transformation):
    """Use the created homography matrix on the measurements to see how well
    they map"""
    print_error_map(
        sys.stderr, ideal_points,
        [z[0] for z in transformation(measured_points)])


def build_remapping(reverse_transformation_fn, res):
    a = numpy.zeros((res[1], res[0], 2), dtype=numpy.float32)
    for x in range(0, res[0]):
        for y in range(0, res[1]):
            a[y][x][0] = x
            a[y][x][1] = y
    return reverse_transformation_fn(a)


ReversibleTransformation = namedtuple(
    'ReversibleTransformation', 'do reverse describe')


def calculate_distortion(ideal, measured_points, resolution):
    ideal_3d = numpy.array([[[x, y, 0]] for x, y in ideal],
                           dtype=numpy.float32)
    _, cameraMatrix, distCoeffs, _, _ = cv2.calibrateCamera(
        [ideal_3d], [measured_points], resolution)

    def undistort(points):
        # pylint: disable=E1101
        return cv2.undistortPoints(points, cameraMatrix, distCoeffs)

    def distort(points):
        points = points.reshape((-1, 2))
        points_3d = numpy.zeros((len(points), 3))
        points_3d[:, 0:2] = points
        return cv2.projectPoints(points_3d, (0, 0, 0), (0, 0, 0),
                                 cameraMatrix, distCoeffs)[0]

    def describe():
        return [
            ('camera-matrix',
             ' '.join([' '.join([repr(v) for v in l]) for l in cameraMatrix])),
            ('distortion-coefficients',
             ' '.join([repr(x) for x in distCoeffs[0]]))]
    return ReversibleTransformation(undistort, distort, describe)


def calculate_perspective_transformation(ideal, measured_points):
    ideal_2d = numpy.array([[[x, y]] for x, y in ideal],
                           dtype=numpy.float32)
    mat, _ = cv2.findHomography(measured_points, ideal_2d)

    def transform_perspective(points):
        return cv2.perspectiveTransform(points, mat)

    def untransform_perspective(points):
        return cv2.perspectiveTransform(points, numpy.linalg.inv(mat))

    def describe():
        return [('homography-matrix',
                 ' '.join([' '.join([repr(x) for x in l]) for l in mat]))]
    return ReversibleTransformation(
        transform_perspective, untransform_perspective, describe)


def _find_chessboard(appsink, timeout=10):
    sys.stderr.write("Searching for chessboard\n")
    success = False
    endtime = time.time() + timeout
    while not success and time.time() < endtime:
        sample = appsink.emit("pull-sample")
        with stbt._numpy_from_sample(sample, readonly=True) as input_image:
            success, corners = cv2.findChessboardCorners(
                input_image, (29, 15), flags=cv2.cv.CV_CALIB_CB_ADAPTIVE_THRESH)

    if success:
        # Refine the corner measurements (not sure why this isn't built into
        # findChessboardCorners?
        with stbt._numpy_from_sample(sample, readonly=True) as input_image:
            grey_image = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)

        cv2.cornerSubPix(grey_image, corners, (5, 5), (-1, -1),
                         (cv2.TERM_CRITERIA_COUNT, 100, 0.1))

        # Chessboard could have been recognised either way up.  Match it.
        if corners[0][0][0] < corners[1][0][0]:
            ideal = numpy.array(
                [[x * 40 - 0.5, y * 40 - 0.5]
                 for y in range(2, 17) for x in range(2, 31)],
                dtype=numpy.float32)
        else:
            ideal = numpy.array(
                [[x * 40 - 0.5, y * 40 - 0.5]
                 for y in range(16, 1, -1) for x in range(30, 1, -1)],
                dtype=numpy.float32)

        return ideal, corners
    else:
        raise RuntimeError("Couldn't find Chessboard")


def geometric_calibration(tv, interactive=True):
    if interactive:
        raw_input("Please line up camera and press <ENTER> when ready")
    tv.show('chessboard')

    sys.stdout.write("Performing Geometric Calibration\n")

    undistorted_appsink = \
        stbt._display.source_pipeline.get_by_name('undistorted_appsink')
    ideal, corners = _find_chessboard(undistorted_appsink)

    undistort = calculate_distortion(ideal, corners, (1920, 1080))
    unperspect = calculate_perspective_transformation(
        ideal, undistort.do(corners))

    geometriccorrection = stbt._display.source_pipeline.get_by_name(
        'geometric_correction')
    geometriccorrection_params = undistort.describe() + unperspect.describe()
    for key, value in geometriccorrection_params:
        geometriccorrection.set_property(key, value)

    validate_transformation(
        corners, ideal, lambda points: unperspect.do(undistort.do(points)))

    set_config(
        'global', 'geometriccorrection_params',
        ' '.join('%s="%s"' % v for v in geometriccorrection_params))

#
# setup
#

uvcvideosrc = ('uvch264src device=%(v4l2_device)s name=src auto-start=true '
               'rate-control=vbr initial-bitrate=5000000 '
               'peak-bitrate=10000000 average-bitrate=5000000 '
               'v4l2src0::extra-controls="ctrls, %(v4l2_ctls)s" src.vidsrc ! '
               'video/x-h264,width=1920 ! h264parse')
v4l2videosrc = 'v4l2src device=%(v4l2_device)s extra-controls=%(v4l2_ctls)s'


def list_cameras():
    from gi.repository import GUdev  # pylint: disable=E0611
    client = GUdev.Client.new(['video4linux/usb_device'])
    devices = client.query_by_subsystem('video4linux')
    for d in devices:
        # Prefer to refer to a device by path.  This means that you are
        # referring to a particular USB port and is stable across reboots.
        dev_files = d.get_device_file_symlinks()
        path_dev_files = [x for x in dev_files if 'by-path' in x]
        dev_file = (path_dev_files + [d.get_device_file])[0]

        name = (d.get_property('ID_VENDOR_ENC').decode('string-escape') + ' ' +
                d.get_property('ID_MODEL_ENC').decode('string-escape'))

        if d.get_property('ID_USB_DRIVER') == 'uvcvideo':
            source_pipeline = uvcvideosrc
        else:
            source_pipeline = v4l2videosrc

        yield (name, dev_file, source_pipeline)


def setup(source_pipeline):
    """If we haven't got a configured camera offer a list of cameras you might
    want to use.  In the future it could be useful to allow the user to select
    one from the list interactively."""
    if (source_pipeline == ''
            or stbt.get_config('global', 'v4l2_device', '') == ''):
        sys.stderr.write(
            'No camera configured in stbt.conf please add parameters '
            '"v4l2_device" and "source_pipeline" to section [global] of '
            'stbt.conf.\n\n')
        cameras = list(list_cameras())
        if len(cameras) == 0:
            sys.stderr.write("No Cameras Detected\n\n")
        else:
            sys.stderr.write("Detected cameras:\n\n")
        for n, (name, dev_file, source_pipeline) in zip(count(1), cameras):
            sys.stderr.write(
                "    %i. %s\n"
                "\n"
                "        v4l2_device = %s\n"
                "        source_pipeline = %s\n\n"
                % (n, name, dev_file, source_pipeline))
        return False
    return True

#
# main
#

defaults = {
    'v4l2_ctls': (
        'brightness=128,contrast=128,saturation=128,'
        'white_balance_temperature_auto=0,white_balance_temperature=6500,'
        'gain=60,backlight_compensation=0,exposure_auto=1,'
        'exposure_absolute=152,focus_auto=0,focus_absolute=0,'
        'power_line_frequency=1'),
    'transformation_pipeline': (
        'stbtgeometriccorrection name=geometric_correction '
        '   %(geometriccorrection_params)s '
}


def parse_args(argv):
    parser = stbt.argparser()
    tv_driver.add_argparse_argument(parser)
    parser.add_argument(
        '--noninteractive', action="store_false", dest="interactive",
        help="Don't prompt, assume default answer to all questions")
    parser.add_argument(
        '--skip-geometric', action="store_true",
        help="Don't perform geometric calibration")
    return parser.parse_args(argv[1:])


def main(argv):
    args = parse_args(argv)

    if not setup(args.source_pipeline):
        return 1

    if args.skip_geometric:
        set_config('global', 'geometriccorrection_params', '')

    for k, v in defaults.iteritems():
        set_config('global', k, v)

    # Need to re-parse arguments as the settings above may have affected the
    # values we get out.
    args = parse_args(argv)

    transformation_pipeline = (
        'tee name=raw_undistorted '
        'raw_undistorted. ! queue leaky=upstream ! videoconvert ! '
        '    textoverlay text="Capture from camera" ! %s '
        'raw_undistorted. ! queue ! appsink drop=true sync=false qos=false'
        '    max-buffers=1 caps="video/x-raw,format=BGR"'
        '    name=undistorted_appsink '
        'raw_undistorted. ! queue leaky=upstream max-size-buffers=1 ! %s' %
        (args.sink_pipeline,
         stbt.get_config('global', 'transformation_pipeline')))

    sink_pipeline = ('textoverlay text="After correction" ! ' +
                     args.sink_pipeline)

    stbt.init_run(args.source_pipeline, sink_pipeline, 'none', False,
                  False, transformation_pipeline)

    tv = tv_driver.create_from_args(args, videos)

    if not args.skip_geometric:
        geometric_calibration(tv, interactive=args.interactive)

    if args.interactive:
        raw_input("Calibration complete.  Press <ENTER> to exit")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
