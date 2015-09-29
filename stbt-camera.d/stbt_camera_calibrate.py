#!/usr/bin/python -u
# Encoding: utf-8
# pylint: disable=W0212

import math
import re
import readline
import subprocess
import sys
import time
from contextlib import contextmanager
from os.path import abspath, dirname

import cv2
import gi
import numpy

import _stbt.camera.chessboard as chessboard
import _stbt.core
import stbt
from _stbt import tv_driver
from _stbt.config import set_config, xdg_config_dir
from _stbt.gst_hacks import run_on_stream_thread

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # isort:skip pylint: disable=E0611

COLOUR_SAMPLES = 150
videos = {}

#
# Geometric calibration
#

videos['chessboard'] = chessboard.VIDEO

arrows = list(u'←↙↓↘→↗↑↖')


def off_to_arrow(off):
    u"""
    >>> print off_to_arrow((1, 1))
    ↘
    >>> print off_to_arrow((-1, 0))
    ←
    """
    if numpy.linalg.norm(off) > 0.5:
        angle = math.atan2(off[1], -off[0])
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


def geometric_calibration(tv, device, interactive=True):
    tv.show('chessboard')

    print "Performing Geometric Calibration"

    out = chessboard_calibration()
    if interactive:
        while prompt_for_adjustment(device):
            try:
                out = chessboard_calibration()
            except chessboard.NoChessboardError:
                tv.show('chessboard')
                out = chessboard_calibration()

    return out

def chessboard_calibration(timeout=10):
    from _stbt.gst_utils import array_from_sample

    undistorted_appsink = \
        stbt._dut._display.source_pipeline.get_by_name('undistorted_appsink')

    sys.stderr.write("Searching for chessboard\n")
    endtime = time.time() + timeout
    while time.time() < endtime:
        for _ in range(10):
            # Make sure we're pulling a recent sample
            sample = undistorted_appsink.emit("pull-sample")
        try:
            input_image = array_from_sample(sample)
            params = chessboard.calculate_calibration_params(input_image)
            break
        except chessboard.NoChessboardError:
            if time.time() > endtime:
                raise

    geometriccorrection = stbt._dut._display.source_pipeline.get_by_name(
        'geometric_correction')
    assert geometriccorrection is not None
    geometriccorrection_params = {}
    geometriccorrection_params.update(undistort.describe())
    geometriccorrection_params.update(unperspect.describe())
    preset_fragment = "".join(
        "float %s = float(%.15f);" % x
        for x in geometriccorrection_params.items())

    run_on_stream_thread(
        geometriccorrection.pads[0],
        lambda: geometriccorrection.set_property("vars", preset_fragment))

    print_error_map(
        sys.stderr,
        *chessboard.find_corrected_corners(params, input_image))

    return geometriccorrection_params

#
# Colour Measurement
#


def qrc(data):
    import cStringIO
    import qrcode
    import qrcode.image.svg

    out = cStringIO.StringIO()
    qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage).save(out)
    qrsvg = out.getvalue()

    return re.search('d="(.*?)"', qrsvg).group(1)


def generate_colours_video():
    import random
    template_svg = open(dirname(__file__) + '/colours.svg', 'r').read()
    for _ in range(0, 10 * 60 * 8):
        colour = '#%06x' % random.randint(0, 256 ** 3)
        svg = template_svg.replace('#c0ffee', colour)
        svg = svg.replace("m 0,0 26,0 0,26 -26,0 z", qrc(colour))
        yield (svg, 1.0 / 8 * Gst.SECOND)

videos['colours2'] = ('image/svg', generate_colours_video)


class QRScanner(object):
    def __init__(self):
        import zbar
        self.scanner = zbar.ImageScanner()
        self.scanner.parse_config('enable')

    def read_qr_codes(self, image):
        import zbar
        zimg = zbar.Image(image.shape[1], image.shape[0], 'Y800',
                          cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).tostring())
        self.scanner.scan(zimg)
        return [s.data for s in zimg]


def analyse_colours_video(number=None):
    """RGB!"""
    errors_in_a_row = 0
    n = 0
    qrscanner = QRScanner()
    for frame, _ in stbt.frames():
        if number is not None and n >= number:
            return
        n = n + 1

        # The colour is written above and below the rectangle because we want
        # to be sure that the top of the colour box is from the same frame as
        # the bottom.
        codes = qrscanner.read_qr_codes(frame)

        if (len(codes) == 4 and re.match('#[0-9a-f]{6}', codes[0]) and
                all(c == codes[0] for c in codes)):
            colour_hex = codes[0]
            desired = numpy.array((
                int(colour_hex[1:3], 16),
                int(colour_hex[3:5], 16),
                int(colour_hex[5:7], 16)))
            colour = cv2.mean(frame[240:480, 520:760])
            colour = (colour[2], colour[1], colour[0])
            yield (n, desired, colour)
            errors_in_a_row = 0
        else:
            errors_in_a_row += 1
            if errors_in_a_row > 50:
                raise RuntimeError(
                    "Failed to find hexidecimal colour description")


def avg_colour(colours):
    n = len(colours)
    return (
        sum([c[0] for c in colours]) / n,
        sum([c[1] for c in colours]) / n,
        sum([c[2] for c in colours]) / n)


example_v4l2_ctl_output = """\
                     brightness (int)    : min=-64 max=64 step=1 default=15 value=15
                       contrast (int)    : min=0 max=95 step=1 default=30 value=30
"""


def v4l2_ctls(device, data=None):
    """
    >>> import pprint
    >>> pprint.pprint(dict(v4l2_ctls(None, example_v4l2_ctl_output)))
    {'brightness': {'default': '15',
                    'max': '64',
                    'min': '-64',
                    'step': '1',
                    'value': '15'},
     'contrast': {'default': '30',
                  'max': '95',
                  'min': '0',
                  'step': '1',
                  'value': '30'}}
    """
    if data is None:
        data = subprocess.check_output(['v4l2-ctl', '-d', device, '-l'])
    for line in data.split('\n'):
        vals = line.strip().split()
        if vals == []:
            continue
        yield (vals[0], dict([v.split('=', 2) for v in vals[3:]]))


def setup_tab_completion(completer):
    next_ = [None]
    generator = [None]

    def readline_completer(text, state):
        if state == 0:
            generator[0] = iter(completer(text))
            next_[0] = 0

        assert state == next_[0]
        next_[0] += 1

        try:
            return generator[0].next()
        except StopIteration:
            return None

    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims("")
    readline.set_completer(readline_completer)


def prompt_for_adjustment(device):
    # Allow adjustment
    print subprocess.check_output(['v4l2-ctl', '-d', device, '-L'])
    ctls = dict(v4l2_ctls(device))

    def v4l_completer(text):
        if text == '':
            return ['yes', 'no', 'set']
        if text.startswith('set '):
            return ['set ' + x + ' '
                    for x in ctls.keys() if x.startswith(text[4:])]
        if "set ".startswith(text.lower()):
            return ["set "]
        if 'yes'.startswith(text.lower()):
            return ["yes"]
        if 'no'.startswith(text.lower()):
            return ["no"]

    setup_tab_completion(v4l_completer)

    cmd = raw_input("Happy? [Y/n/set] ").strip().lower()
    if cmd.startswith('set'):
        x = cmd.split(None, 2)
        if len(x) != 3:
            print "Didn't understand command %r" % x
        else:
            _, var, val = x
            subprocess.check_call(
                ['v4l2-ctl', '-d', device, "-c", "%s=%s" % (var, val)])

    set_config('global', 'v4l2_ctls', ','.join(
        ["%s=%s" % (c, a['value'])
         for c, a in dict(v4l2_ctls(device)).items()]))

    if cmd.startswith('y') or cmd == '':
        return False  # We're done
    else:
        return True  # Continue looping


def pop_with_progress(iterator, total, width=20, stream=sys.stderr):
    stream.write('\n')
    for n, v in enumerate(iterator):
        if n == total:
            break
        progress = (n * width) // total
        stream.write(
            '[%s] %8d / %d\r' % (
                '#' * progress + ' ' * (width - progress), n, total))
        yield v
    stream.write('\r' + ' ' * (total + 28) + '\r')


def fit(expected, measurements):
    import scipy.optimize
    measurements = numpy.array(measurements, dtype=numpy.uint8)
    print measurements
    w = numpy.array(range(128) + range(128, 0, -1), dtype=numpy.double)
    
    r1 = numpy.array(range(0, 254))
    r2 = numpy.array(range(1, 255))
    r3 = numpy.array(range(2, 256))

    n_0_255 = numpy.array(range(0, 255))
    n_1_256 = numpy.array(range(1, 256))

    def fitness_fn(g):
        gr = g[:256]
        diff = w[measurements] * (g[measurements] - expected)
        s = numpy.dot(diff, diff)

        # Smoothness term
        derivative = w[r2] * (g[r1] - 2 * g[r2] + g[r3])
        smoothness = numpy.dot(derivative, derivative)

        # Single valuedness term
        inc = g[n_1_256] - g[n_0_255]
        d = inc[inc < 0]
        sv = 10 * 128 * numpy.dot(d, d)

        lambda_ = 300
        return s + sv + lambda_ * smoothness

    initial_guess = numpy.array(range(256), dtype=numpy.double)
    result = scipy.optimize.minimize(fitness_fn, initial_guess)
    #assert result.success
    return result.x


def fit_fn(ideals, measureds):
    """
    >>> f = fit_fn([120, 240, 150, 18, 200],
    ...            [120, 240, 150, 18, 200])
    >>> print f(0), f(56)
    0.0 56.0
    """
    from scipy.optimize import curve_fit  # pylint: disable=E0611
    from scipy.interpolate import interp1d  # pylint: disable=E0611
    POINTS = 5
    xs = [n * 255.0 / (POINTS + 1) for n in range(0, POINTS + 2)]

    def fn(x, ys):
        return interp1d(xs, numpy.array([0] + ys + [255]))(x)

    ys, _ = curve_fit(  # pylint:disable=W0632
        lambda x, *args: fn(x, list(args)), ideals, measureds, [0.0] * POINTS)
    return interp1d(xs, numpy.array([0] + ys.tolist() + [255]))


@contextmanager
def colour_graph():
    if not _can_show_graphs():
        sys.stderr.write("Install matplotlib and scipy for graphical "
                         "assistance with colour calibration\n")
        yield lambda: None
        return

    from matplotlib import pyplot
    sys.stderr.write('Analysing colours...\n')
    pyplot.ion()

    ideals = [[], [], []]
    measureds = [[], [], []]

    pyplot.figure()

    def update():
        pyplot.cla()
        pyplot.axis([0, 255, 0, 255])
        pyplot.ylabel("Measured colour")
        pyplot.xlabel("Ideal colour")
        pyplot.grid()

        for n, ideal, measured in pop_with_progress(
                analyse_colours_video(), COLOUR_SAMPLES):
            pyplot.draw()
            for c in [0, 1, 2]:
                ideals[c].append(ideal[c])
                measureds[c].append(measured[c])
            pyplot.plot([ideal[0]], [measured[0]], 'rx',
                        [ideal[1]], [measured[1]], 'gx',
                        [ideal[2]], [measured[2]], 'bx')

        fits = [fit(ideals[n], measureds[n]) for n in [0, 1, 2]]
        pyplot.plot(fits[0], range(0, 256), 'r-',
                    fits[1], range(0, 256), 'g-',
                    fits[2], range(0, 256), 'b-')
        pyplot.draw()
        return fits

    try:
        yield update
    finally:
        pyplot.close()


def _can_show_graphs():
    try:
        # pylint: disable=W0612
        from matplotlib import pyplot
        from scipy.optimize import curve_fit  # pylint: disable=E0611
        from scipy.interpolate import interp1d  # pylint: disable=E0611
        return True
    except ImportError:
        sys.stderr.write("Install matplotlib and scipy for graphical "
                         "assistance with colour calibration\n")
        return False


def adjust_levels(tv, device):
    tv.show("colours2")
    with colour_graph() as update_graph:
        out = update_graph()
        while prompt_for_adjustment(device):
            out = update_graph()
    return out


#
# Uniform Illumination
#

FRAME_AVERAGE_COUNT = 16

videos['blank-white'] = (
    'video/x-raw,format=BGR,width=1280,height=720',
    lambda: [(bytearray([0xff, 0xff, 0xff]) * 1280 * 720, 60 * Gst.SECOND)])
videos['blank-black'] = (
    'video/x-raw,format=BGR,width=1280,height=720',
    lambda: [(bytearray([0, 0, 0]) * 1280 * 720, 60 * Gst.SECOND)])


def _create_reference_png(filename):
    # Throw away some frames to let everything settle
    pop_with_progress(stbt.frames(), 50)

    average = None
    for frame in pop_with_progress(stbt.frames(), FRAME_AVERAGE_COUNT):
        if average is None:
            average = numpy.zeros(shape=frame[0].shape, dtype=numpy.uint16)
        average += frame[0]
    average /= FRAME_AVERAGE_COUNT
    cv2.imwrite(filename, numpy.array(average, dtype=numpy.uint8))


def await_blank(brightness):
    for frame, _ in stbt.frames(10):
        grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        min_, max_, _, _ = cv2.minMaxLoc(grayscale)
        contrast = max_ - min_
        if contrast < 100 and abs(numpy.median(frame) - brightness) < 100:
            break
    else:
        sys.stderr.write(
            "WARNING: Did not detect blank frame of brightness %i" % brightness)


def calibrate_illumination(tv):
    props = {
        'white-reference-image':
        xdg_config_dir('stbt/vignetting-reference-white.png'),
        'black-reference-image':
        xdg_config_dir('stbt/vignetting-reference-black.png'),
    }

    tv.show("blank-white")
    await_blank(255)
    _create_reference_png(props['white-reference-image'])
    tv.show("blank-black")
    await_blank(0)
    _create_reference_png(props['black-reference-image'])

    contraststretch = stbt._dut._display.source_pipeline.get_by_name(
        'illumination_correction')
    for k, v in reversed(props.items()):
        contraststretch.set_property(k, v)
    set_config(
        'global', 'contraststretch_params',
        ' '.join(["%s=%s" % (k, v) for k, v in props.items()]))


#
# setup
#

uvcvideosrc = (
    'v4l2src device=%(v4l2_device)s extra-controls="ctrls, %(v4l2_ctls)s" '
    '! video/x-h264,width=1920 ! h264parse')
v4l2videosrc = 'v4l2src device=%(v4l2_device)s extra-controls=%(v4l2_ctls)s'


def list_cameras():
    gi.require_version('GUdev', '1.0')
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
    if (source_pipeline == '' or
            stbt.get_config('global', 'v4l2_device', '') == ''):
        sys.stderr.write(
            'No camera configured in stbt.conf please add parameters '
            '"v4l2_device" and "source_pipeline" to section [global] of '
            'stbt.conf.\n\n')
        cameras = list(list_cameras())
        if len(cameras) == 0:
            sys.stderr.write("No Cameras Detected\n\n")
        else:
            sys.stderr.write("Detected cameras:\n\n")
        for n, (name, dev_file, source_pipeline) in enumerate(cameras):
            sys.stderr.write(
                "    %i. %s\n"
                "\n"
                "        v4l2_device = %s\n"
                "        source_pipeline = %s\n\n"
                % (n, name, dev_file, source_pipeline))
        return None
    return stbt.get_config('global', 'v4l2_device')

#
# main
#

defaults = {
    'camera_prefix': abspath(dirname(__file__)),
    'contraststretch_params': '',
    'geometriccorrection_params': 'vars="float fx = float(1.0); float fy = float(1.0); float cx = float(0.0); float cy = float(0.0); float k1 = float(0.0); float k2 = float(0.0); float p1 = float(0.0); float p2 = float(0.0); float k3 = float(0.0); float ihm11 = float(1.5); float ihm12 = float(0.0); float ihm13 = float(0.0); float ihm21 = float(0.0); float ihm22 = float(1.5); float ihm23 = float(0.0); float ihm31 = float(0.25); float ihm32 = float(0.25); float ihm33 = float(1.0);"',
    'v4l2_ctls': (
        'brightness=128,contrast=128,saturation=128,'
        'white_balance_temperature_auto=0,white_balance_temperature=6500,'
        'gain=60,backlight_compensation=0,exposure_auto=1,'
        'exposure_absolute=152,focus_auto=0,focus_absolute=0,'
        'power_line_frequency=1'),
    'transformation_pipeline': (
        'videoconvert '
        ' ! glupload '
        ' ! glshader name=geometric_correction '
        '  location=%(camera_prefix)s/geometric-correction.frag'
        '  %(geometriccorrection_params)s '
        ' ! gldownload '
        ' ! video/x-raw,width=1280,height=720 '
        ' ! videoconvert '
        ' ! stbtcontraststretch name=illumination_correction '
        '   %(contraststretch_params)s '),
}


def parse_args(argv):
    parser = _stbt.core.argparser()
    tv_driver.add_argparse_argument(parser)
    parser.add_argument(
        '--noninteractive', action="store_false", dest="interactive",
        help="Don't prompt, assume default answer to all questions")
    parser.add_argument(
        '--skip-geometric', action="store_true",
        help="Don't perform geometric calibration")
    parser.add_argument(
        '--skip-illumination', action='store_true',
        help="Don't perform uniform illumination calibration")
    return parser.parse_args(argv[1:])


def main(argv):
    args = parse_args(argv)

    device = setup(args.source_pipeline)
    if device is None:
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

    stbt.init_run(args.source_pipeline, sink_pipeline, 'none', False, False,
                  transformation_pipeline)

    tv = tv_driver.create_from_args(args, videos)

    if not args.skip_geometric:
        geometric_calibration(tv, device, interactive=args.interactive)
    if args.interactive:
        adjust_levels(tv, device)
    if not args.skip_illumination:
        calibrate_illumination(tv)

    if args.interactive:
        raw_input("Calibration complete.  Press <ENTER> to exit")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
