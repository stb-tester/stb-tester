"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/drothlis/stb-tester/blob/master/LICENSE for details).
"""

import argparse
from collections import namedtuple, deque
import ConfigParser
import contextlib
import errno
import functools
import glob
import inspect
import os
import Queue
import re
import socket
import sys
import threading
import time
import warnings

import cv2
import numpy

import irnetbox


@contextlib.contextmanager
def hide_argv():
    """ For use with 'with' statement: Provides a context with an empty
    argument list.

    This is used because otherwise gst-python will exit if '-h', '--help', '-v'
    or '--version' command line arguments are given.
    """
    old_argv = sys.argv[:]
    sys.argv = [sys.argv[0]]
    try:
        yield
    finally:
        sys.argv = old_argv


@contextlib.contextmanager
def hide_stderr():
    """For use with 'with' statement: Hide stderr output.

    This is used because otherwise gst-python will print
    'pygobject_register_sinkfunc is deprecated'.
    """
    fd = sys.__stderr__.fileno()
    saved_fd = os.dup(fd)
    sys.__stderr__.flush()
    null_stream = open(os.devnull, 'w', 0)
    os.dup2(null_stream.fileno(), fd)
    try:
        yield
    finally:
        sys.__stderr__.flush()
        os.dup2(saved_fd, sys.__stderr__.fileno())
        null_stream.close()


import pygst  # gstreamer
pygst.require("0.10")
with hide_argv(), hide_stderr():
    import gst
import gobject
import glib


warnings.filterwarnings(
    action="always", category=DeprecationWarning, message='^noise_threshold')


_config = None


# Functions available to stbt scripts
#===========================================================================

def get_config(section, key, default=None, type_=str):
    """Read the value of `key` from `section` of the stbt config file.

    See 'CONFIGURATION' in the stbt(1) man page for the config file search
    path.

    Raises `ConfigurationError` if the specified `section` or `key` is not
    found, unless `default` is specified (in which case `default` is returned).
    """

    global _config
    if not _config:
        _config = ConfigParser.SafeConfigParser()
        _config.readfp(
            open(os.path.join(os.path.dirname(__file__), 'stbt.conf')))
        try:
            # Host-wide config, e.g. /etc/stbt/stbt.conf (see `Makefile`).
            system_config = _config.get('global', '__system_config')
        except ConfigParser.NoOptionError:
            # Running `stbt` from source (not installed) location.
            system_config = ''
        _config.read([
            system_config,
            # User config: ~/.config/stbt/stbt.conf, as per freedesktop's base
            # directory specification:
            '%s/stbt/stbt.conf' % os.environ.get(
                'XDG_CONFIG_HOME', '%s/.config' % os.environ['HOME']),
            # Config files specific to the test suite / test run:
            os.environ.get('STBT_CONFIG_FILE', ''),
        ])

    try:
        return type_(_config.get(section, key))
    except ConfigParser.Error as e:
        if default is None:
            raise ConfigurationError(e.message)
        else:
            return default
    except ValueError:
        raise ConfigurationError("'%s.%s' invalid type (must be %s)" % (
            section, key, type_.__name__))


def press(key):
    """Send the specified key-press to the system under test.

    The mechanism used to send the key-press depends on what you've configured
    with `--control`.

    `key` is a string. The allowed values depend on the control you're using:
    If that's lirc, then `key` is a key name from your lirc config file.
    """
    _control.press(key)
    draw_text(key, duration_secs=3)


def draw_text(text, duration_secs=3):
    """Write the specified `text` to the video output.

    `duration_secs` is the number of seconds that the text should be displayed.
    """
    _display.draw_text(text, duration_secs)


class MatchParameters(object):
    """Parameters to customise the image processing algorithm used by
    `wait_for_match`, `detect_match`, and `press_until_match`.

    You can change the default values for these parameters by setting
    a key (with the same name as the corresponding python parameter)
    in the `[match]` section of your stbt.conf configuration file.

    `match_method` (str) default: From stbt.conf
      The method that is used by the OpenCV `cvMatchTemplate` algorithm to find
      likely locations of the "template" image within the larger source image.

      Allowed values are ``"sqdiff-normed"``, ``"ccorr-normed"``, and
      ``"ccoeff-normed"``. For the meaning of these parameters, see the OpenCV
      `cvMatchTemplate` reference documentation and tutorial:

      * http://docs.opencv.org/modules/imgproc/doc/object_detection.html
      * http://docs.opencv.org/doc/tutorials/imgproc/histograms/
                                       template_matching/template_matching.html

    `match_threshold` (float) default: From stbt.conf
      How strong a result from `cvMatchTemplate` must be, to be considered a
      match. A value of 0 will mean that anything is considered to match,
      whilst a value of 1 means that the match has to be pixel perfect. (In
      practice, a value of 1 is useless because of the way `cvMatchTemplate`
      works, and due to limitations in the storage of floating point numbers in
      binary.)

    `confirm_method` (str) default: From stbt.conf
      The result of the previous `cvMatchTemplate` algorithm often gives false
      positives (it reports a "match" for an image that shouldn't match).
      `confirm_method` specifies an algorithm to be run just on the region of
      the source image that `cvMatchTemplate` identified as a match, to confirm
      or deny the match.

      The allowed values are:

      "``none``"
          Do not confirm the match. Assume that the potential match found is
          correct.

      "``absdiff``" (absolute difference)
          The absolute difference between template and source Region of
          Interest (ROI) is calculated; thresholded and eroded to account for
          potential noise; and if any white pixels remain then the match is
          deemed false.

      "``normed-absdiff``" (normalized absolute difference)
          As with ``absdiff`` but both template and ROI are normalized before
          the absolute difference is calculated. This has the effect of
          exaggerating small differences between images with similar, small
          ranges of pixel brightnesses (luminance).

          This method is more accurate than ``absdiff`` at reporting true and
          false matches when there is noise involved, particularly aliased
          text. However it will, in general, require a greater
          confirm_threshold than the equivalent match with absdiff.

          When matching solid regions of colour, particularly where there are
          regions of either black or white, ``absdiff`` is better than
          ``normed-absdiff`` because it does not alter the luminance range,
          which can lead to false matches. For example, an image which is half
          white and half grey, once normalised, will match a similar image
          which is half white and half black because the grey becomes
          normalised to black so that the maximum luminance range of [0..255]
          is occupied. However, if the images are dissimilar enough in
          luminance, they will have failed to match the `cvMatchTemplate`
          algorithm and won't have reached the "confirm" stage.

    `confirm_threshold` (float) default: From stbt.conf
      Increase this value to avoid false negatives, at the risk of increasing
      false positives (a value of 1.0 will report a match every time).

    `erode_passes` (int) default: From stbt.conf
      The number of erode steps in the `absdiff` and `normed-absdiff` confirm
      algorithms. Increasing the number of erode steps makes your test less
      sensitive to noise and small variances, at the cost of being more likely
      to report a false positive.

    Please let us know if you are having trouble with image matches so that we
    can further improve the matching algorithm.
    """

    def __init__(
            self,
            match_method=get_config('match', 'match_method'),
            match_threshold=get_config(
                'match', 'match_threshold', type_=float),
            confirm_method=get_config('match', 'confirm_method'),
            confirm_threshold=get_config(
                'match', 'confirm_threshold', type_=float),
            erode_passes=get_config('match', 'erode_passes', type_=int)):

        if match_method not in (
                "sqdiff-normed", "ccorr-normed", "ccoeff-normed"):
            raise ValueError("Invalid match_method '%s'" % match_method)
        if confirm_method not in ("none", "absdiff", "normed-absdiff"):
            raise ValueError("Invalid confirm_method '%s'" % confirm_method)

        self.match_method = match_method
        self.match_threshold = match_threshold
        self.confirm_method = confirm_method
        self.confirm_threshold = confirm_threshold
        self.erode_passes = erode_passes


class Position(namedtuple('Position', 'x y')):
    """
    * `x` and `y`: Integer coordinates from the top left corner of the video
      frame.
    """
    pass


class MatchResult(namedtuple(
        'MatchResult', 'timestamp match position first_pass_result')):
    """
    * `timestamp`: Video stream timestamp.
    * `match`: Boolean result.
    * `position`: `Position` of the match.
    * `first_pass_result`: Value between 0 (poor) and 1.0 (excellent match)
      from the first pass of the two-pass templatematch algorithm.
    """
    pass


def detect_match(image, timeout_secs=10, noise_threshold=None,
                 match_parameters=None):
    """Generator that yields a sequence of one `MatchResult` for each frame
    processed from the source video stream.

    Returns after `timeout_secs` seconds. (Note that the caller can also choose
    to stop iterating over this function's results at any time.)

    The templatematch parameter `noise_threshold` is marked for deprecation
    but appears in the args for backward compatibility with positional
    argument syntax. It will be removed in a future release; please use
    `match_parameters.confirm_threshold` intead.

    Specify `match_parameters` to customise the image matching algorithm. See
    the documentation for `MatchParameters` for details.
    """

    if match_parameters is None:
        match_parameters = MatchParameters()

    if noise_threshold is not None:
        warnings.warn(
            "noise_threshold is marked for deprecation. Please use "
            "match_parameters.confirm_threshold instead.",
            DeprecationWarning, stacklevel=2)
        match_parameters.confirm_threshold = noise_threshold

    template_name = _find_path(image)
    if not os.path.isfile(template_name):
        raise UITestError("No such template file: %s" % image)
    template = cv2.imread(template_name, cv2.CV_LOAD_IMAGE_COLOR)
    if template is None:
        raise UITestError("Failed to load template file: %s" % template_name)

    debug("Searching for " + template_name)

    for frame, timestamp in frames(timeout_secs):
        matched, position, first_pass_certainty = _match(
            frame, template, match_parameters, template_name)

        result = MatchResult(
            timestamp=timestamp,
            match=matched,
            position=position,
            first_pass_result=first_pass_certainty)
        debug("%s found: %s" % (
            "Match" if matched else "Weak match", str(result)))
        yield result


class MotionResult(namedtuple('MotionResult', 'timestamp motion')):
    """
    * `timestamp`: Video stream timestamp.
    * `motion`: Boolean result.
    """
    pass


def detect_motion(timeout_secs=10, noise_threshold=None, mask=None):
    """Generator that yields a sequence of one `MotionResult` for each frame
    processed from the source video stream.

    Returns after `timeout_secs` seconds. (Note that the caller can also choose
    to stop iterating over this function's results at any time.)

    `noise_threshold` (float) default: From stbt.conf
      `noise_threshold` is a parameter used by the motiondetect algorithm.
      Increase `noise_threshold` to avoid false negatives, at the risk of
      increasing false positives (a value of 0.0 will never report motion).
      This is particularly useful with noisy analogue video sources.
      The default value is read from `motion.noise_threshold` in your
      configuration file.

    `mask` (str) default: None
      A mask is a black and white image that specifies which part of the image
      to search for motion. White pixels select the area to search; black
      pixels the area to ignore.
    """

    if noise_threshold is None:
        noise_threshold = get_config('motion', 'noise_threshold', type_=float)

    debug("Searching for motion")

    mask_image = None
    if mask:
        mask_ = _find_path(mask)
        debug("Using mask %s" % mask_)
        if not os.path.isfile(mask_):
            raise UITestError("No such mask file: %s" % mask)
        mask_image = cv2.imread(mask_, cv2.CV_LOAD_IMAGE_GRAYSCALE)
        if mask_image is None:
            raise UITestError("Failed to load mask file: %s" % mask_)

    previous_frame_gray = None
    log = functools.partial(_log_image, directory="stbt-debug/detect_motion")

    for frame, timestamp in frames(timeout_secs):
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        log(frame_gray, "source")

        if previous_frame_gray is None:
            if (mask_image is not None and
                    mask_image.shape[:2] != frame.shape[:2]):
                raise UITestError(
                    "The dimensions of the mask '%s' %s don't match the video "
                    "frame %s" % (mask_, mask_image.shape, frame.shape))
            previous_frame_gray = frame_gray
            continue

        absdiff = cv2.absdiff(frame_gray, previous_frame_gray)
        previous_frame_gray = frame_gray
        log(absdiff, "absdiff")

        if mask_image is not None:
            absdiff = cv2.bitwise_and(absdiff, mask_image)
            log(mask_image, "mask")
            log(absdiff, "absdiff_masked")

        _, thresholded = cv2.threshold(
            absdiff, int((1 - noise_threshold) * 255), 255, cv2.THRESH_BINARY)
        eroded = cv2.erode(
            thresholded,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        log(thresholded, "absdiff_threshold")
        log(eroded, "absdiff_threshold_erode")

        motion = (cv2.countNonZero(eroded) > 0)

        # Visualisation: Highlight in red the areas where we detected motion
        if motion:
            cv2.add(
                frame,
                numpy.multiply(
                    numpy.ones(frame.shape, dtype=numpy.uint8),
                    (0, 0, 255),  # bgr
                    dtype=numpy.uint8),
                mask=cv2.dilate(
                    thresholded,
                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
                    iterations=1),
                dst=frame)

        result = MotionResult(timestamp, motion)
        debug("%s found: %s" % (
            "Motion" if motion else "No motion", str(result)))
        yield result


def wait_for_match(image, timeout_secs=10, consecutive_matches=1,
                   noise_threshold=None, match_parameters=None):
    """Search for `image` in the source video stream.

    Returns `MatchResult` when `image` is found.
    Raises `MatchTimeout` if no match is found after `timeout_secs` seconds.

    `consecutive_matches` forces this function to wait for several consecutive
    frames with a match found at the same x,y position. Increase
    `consecutive_matches` to avoid false positives due to noise.

    The templatematch parameter `noise_threshold` is marked for deprecation
    but appears in the args for backward compatibility with positional
    argument syntax. It will be removed in a future release; please use
    `match_parameters.confirm_threshold` instead.

    Specify `match_parameters` to customise the image matching algorithm. See
    the documentation for `MatchParameters` for details.
    """

    if match_parameters is None:
        match_parameters = MatchParameters()

    if noise_threshold is not None:
        warnings.warn(
            "noise_threshold is marked for deprecation. Please use "
            "match_parameters.confirm_threshold instead.",
            DeprecationWarning, stacklevel=2)
        match_parameters.confirm_threshold = noise_threshold

    match_count = 0
    last_pos = Position(0, 0)
    for res in detect_match(
            image, timeout_secs, match_parameters=match_parameters):
        if res.match and (match_count == 0 or res.position == last_pos):
            match_count += 1
        else:
            match_count = 0
        last_pos = res.position
        if match_count == consecutive_matches:
            debug("Matched " + image)
            return res

    screenshot = get_frame()
    raise MatchTimeout(screenshot, image, timeout_secs)


def press_until_match(
        key,
        image,
        interval_secs=get_config(
            "press_until_match", "interval_secs", type_=int),
        noise_threshold=None,
        max_presses=get_config("press_until_match", "max_presses", type_=int),
        match_parameters=None):
    """Calls `press` as many times as necessary to find the specified `image`.

    Returns `MatchResult` when `image` is found.
    Raises `MatchTimeout` if no match is found after `max_presses` times.

    `interval_secs` is the number of seconds to wait for a match before
    pressing again.

    The global defaults for `interval_secs` and `max_presses` can be set
    in the configuration file, in section `press_until_match`.

    The templatematch parameter `noise_threshold` is marked for deprecation
    but appears in the args for backward compatibility with positional
    argument syntax. It will be removed in a future release; please use
    `match_parameters.confirm_threshold` instead.

    Specify `match_parameters` to customise the image matching algorithm. See
    the documentation for `MatchParameters` for details.
    """

    if match_parameters is None:
        match_parameters = MatchParameters()

    if noise_threshold is not None:
        warnings.warn(
            "noise_threshold is marked for deprecation. Please use "
            "match_parameters.confirm_threshold instead.",
            DeprecationWarning, stacklevel=2)
        match_parameters.confirm_threshold = noise_threshold

    i = 0

    while True:
        try:
            return wait_for_match(image, timeout_secs=interval_secs,
                                  match_parameters=match_parameters)
        except MatchTimeout:
            if i < max_presses:
                press(key)
                i += 1
            else:
                raise


def wait_for_motion(
        timeout_secs=10, consecutive_frames=None,
        noise_threshold=None, mask=None):
    """Search for motion in the source video stream.

    Returns `MotionResult` when motion is detected.
    Raises `MotionTimeout` if no motion is detected after `timeout_secs`
    seconds.

    `consecutive_frames` (str) default: From stbt.conf
      Considers the video stream to have motion if there were differences
      between the specified number of `consecutive_frames`, which can be:

      * a positive integer value, or
      * a string in the form "x/y", where `x` is the number of frames with
        motion detected out of a sliding window of `y` frames.

      The default value is read from `motion.consecutive_frames` in your
      configuration file.

    `noise_threshold` (float) default: From stbt.conf
      Increase `noise_threshold` to avoid false negatives, at the risk of
      increasing false positives (a value of 0.0 will never report motion).
      This is particularly useful with noisy analogue video sources.
      The default value is read from `motion.noise_threshold` in your
      configuration file.

    `mask` (str) default: None
      A mask is a black and white image that specifies which part of the image
      to search for motion. White pixels select the area to search; black
      pixels the area to ignore.
    """

    if consecutive_frames is None:
        consecutive_frames = get_config('motion', 'consecutive_frames')

    consecutive_frames = str(consecutive_frames)
    if '/' in consecutive_frames:
        motion_frames = int(consecutive_frames.split('/')[0])
        considered_frames = int(consecutive_frames.split('/')[1])
    else:
        motion_frames = int(consecutive_frames)
        considered_frames = int(consecutive_frames)

    if motion_frames > considered_frames:
        raise ConfigurationError(
            "`motion_frames` exceeds `considered_frames`")

    debug("Waiting for %d out of %d frames with motion" % (
        motion_frames, considered_frames))

    matches = deque(maxlen=considered_frames)
    for res in detect_motion(timeout_secs, noise_threshold, mask):
        matches.append(res.motion)
        if matches.count(True) >= motion_frames:
            debug("Motion detected.")
            return res

    screenshot = get_frame()
    raise MotionTimeout(screenshot, mask, timeout_secs)


def frames(timeout_secs=None):
    """Generator that yields frames captured from the GStreamer pipeline.

    "timeout_secs" is in seconds elapsed, from the method call. Note that
    you can also simply stop iterating over the sequence yielded by this
    method.

    Returns an (image, timestamp) tuple for every frame captured, where
    "image" is in OpenCV format.
    """
    return _display.frames(timeout_secs)


def save_frame(image, filename):
    """Saves an OpenCV image to the specified file.

    Takes an image obtained from `get_frame` or from the `screenshot`
    property of `MatchTimeout` or `MotionTimeout`.
    """
    cv2.imwrite(filename, image)


def get_frame():
    """Returns an OpenCV image of the current video frame."""
    return gst_to_opencv(_display.get_frame())


def debug(msg):
    """Print the given string to stderr if stbt run `--verbose` was given."""
    if _debug_level > 0:
        sys.stderr.write(
            "%s: %s\n" % (os.path.basename(sys.argv[0]), str(msg)))


class UITestError(Exception):
    """The test script had an unrecoverable error."""
    pass


class UITestFailure(Exception):
    """The test failed because the system under test didn't behave as expected.
    """
    pass


class NoVideo(UITestFailure):
    """No video available from the source pipeline."""
    pass


class MatchTimeout(UITestFailure):
    """
    * `screenshot`: An OpenCV image from the source video when the search
      for the expected image timed out.
    * `expected`: Filename of the image that was being searched for.
    * `timeout_secs`: Number of seconds that the image was searched for.
    """
    def __init__(self, screenshot, expected, timeout_secs):
        super(MatchTimeout, self).__init__()
        self.screenshot = screenshot
        self.expected = expected
        self.timeout_secs = timeout_secs

    def __str__(self):
        return "Didn't find match for '%s' within %d seconds." % (
            self.expected, self.timeout_secs)


class MotionTimeout(UITestFailure):
    """
    * `screenshot`: An OpenCV image from the source video when the search
      for motion timed out.
    * `mask`: Filename of the mask that was used (see `wait_for_motion`).
    * `timeout_secs`: Number of seconds that motion was searched for.
    """
    def __init__(self, screenshot, mask, timeout_secs):
        super(MotionTimeout, self).__init__()
        self.screenshot = screenshot
        self.mask = mask
        self.timeout_secs = timeout_secs

    def __str__(self):
        return "Didn't find motion%s within %d seconds." % (
            " (with mask '%s')" % self.mask if self.mask else "",
            self.timeout_secs)


class ConfigurationError(UITestError):
    pass


# stbt-run initialisation and convenience functions
# (you will need these if writing your own version of stbt-run)
#===========================================================================

def argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--control',
        default=get_config('global', 'control'),
        help='The remote control to control the stb (default: %(default)s)')
    parser.add_argument(
        '--source-pipeline',
        default=get_config('global', 'source_pipeline'),
        help='A gstreamer pipeline to use for A/V input (default: '
             '%(default)s)')
    parser.add_argument(
        '--sink-pipeline',
        default=get_config('global', 'sink_pipeline'),
        help='A gstreamer pipeline to use for video output '
             '(default: %(default)s)')
    parser.add_argument(
        '--restart-source', action='store_true',
        default=(get_config('global', 'restart_source').lower() in
                 ("1", "yes", "true", "on")),
        help='Restart the GStreamer source pipeline when video loss is '
             'detected')

    class IncreaseDebugLevel(argparse.Action):
        num_calls = 0

        def __call__(self, parser, namespace, values, option_string=None):
            self.num_calls += 1
            global _debug_level
            _debug_level = self.num_calls
            setattr(namespace, self.dest, _debug_level)

    global _debug_level
    _debug_level = get_config('global', 'verbose', type_=int)
    parser.add_argument(
        '-v', '--verbose', action=IncreaseDebugLevel, nargs=0,
        default=get_config('global', 'verbose'),  # for stbt-run arguments dump
        help='Enable debug output (specify twice to enable GStreamer element '
             'dumps to ./stbt-debug directory)')

    return parser


def init_run(
        gst_source_pipeline, gst_sink_pipeline, control_uri, save_video=False,
        restart_source=False):
    global _display, _control
    _display = Display(
        gst_source_pipeline, gst_sink_pipeline, save_video, restart_source)
    _control = uri_to_remote(control_uri, _display)


def teardown_run():
    if _display:
        _display.teardown()


# Internal
#===========================================================================

_debug_level = 0
_mainloop = glib.MainLoop()

_display = None
_control = None


class Display:
    def __init__(self, user_source_pipeline, user_sink_pipeline, save_video,
                 restart_source=False):
        gobject.threads_init()

        self.novideo = False
        self.lock = threading.RLock()  # Held by whoever is consuming frames
        self.last_buffer = Queue.Queue(maxsize=1)
        self.source_pipeline = None
        self.start_timestamp = None
        self.underrun_timeout = None
        self.video_debug = []

        self.restart_source_enabled = restart_source

        appsink = (
            "appsink name=appsink max-buffers=1 drop=true sync=false "
            "emit-signals=true "
            "caps=video/x-raw-rgb,bpp=24,depth=24,endianness=4321,"
            "red_mask=0xFF,green_mask=0xFF00,blue_mask=0xFF0000")
        self.source_pipeline_description = " ! ".join([
            user_source_pipeline,
            "queue leaky=downstream name=q",
            "ffmpegcolorspace",
            appsink])
        self.create_source_pipeline()

        if save_video:
            if not save_video.endswith(".webm"):
                save_video += ".webm"
            debug("Saving video to '%s'" % save_video)
            video_pipeline = (
                "t. ! queue leaky=downstream ! ffmpegcolorspace ! "
                "vp8enc speed=7 ! webmmux ! filesink location=%s" % save_video)
        else:
            video_pipeline = ""

        sink_pipeline_description = " ".join([
            "appsrc name=appsrc !",
            "tee name=t",
            video_pipeline,
            "t. ! queue leaky=downstream ! ffmpegcolorspace !",
            user_sink_pipeline
        ])

        self.sink_pipeline = gst.parse_launch(sink_pipeline_description)
        sink_bus = self.sink_pipeline.get_bus()
        sink_bus.connect("message::error", self.on_error)
        sink_bus.connect("message::warning", self.on_warning)
        sink_bus.connect("message::eos", self.on_eos_from_sink_pipeline)
        sink_bus.add_signal_watch()
        self.appsrc = self.sink_pipeline.get_by_name("appsrc")

        debug("source pipeline: %s" % self.source_pipeline_description)
        debug("sink pipeline: %s" % sink_pipeline_description)

        self.source_pipeline.set_state(gst.STATE_PLAYING)
        self.sink_pipeline.set_state(gst.STATE_PLAYING)

        self.mainloop_thread = threading.Thread(target=_mainloop.run)
        self.mainloop_thread.daemon = True
        self.mainloop_thread.start()

    def create_source_pipeline(self):
        self.source_pipeline = gst.parse_launch(
            self.source_pipeline_description)
        source_bus = self.source_pipeline.get_bus()
        source_bus.connect("message::error", self.on_error)
        source_bus.connect("message::warning", self.on_warning)
        source_bus.connect("message::eos", self.on_eos_from_source_pipeline)
        source_bus.add_signal_watch()
        appsink = self.source_pipeline.get_by_name("appsink")
        appsink.connect("new-buffer", self.on_new_buffer)

        if self.restart_source_enabled:
            # Handle loss of video (but without end-of-stream event) from the
            # Hauppauge HDPVR capture device.
            source_queue = self.source_pipeline.get_by_name("q")
            self.start_timestamp = None
            source_queue.connect("underrun", self.on_underrun)
            source_queue.connect("running", self.on_running)

    def get_frame(self, timeout_secs=10):
        try:
            # Timeout in case no frames are received. This happens when the
            # Hauppauge HDPVR video-capture device loses video.
            gst_buffer = self.last_buffer.get(timeout=timeout_secs)
            self.novideo = False
        except Queue.Empty:
            self.novideo = True
            raise NoVideo("No video")
        if isinstance(gst_buffer, Exception):
            raise UITestError(str(gst_buffer))

        return gst_buffer

    def frames(self, timeout_secs):
        self.start_timestamp = None

        with self.lock:
            while True:
                ddebug("user thread: Getting buffer at %s" % time.time())
                buf = self.get_frame(max(10, timeout_secs))
                ddebug("user thread: Got buffer at %s" % time.time())
                timestamp = buf.timestamp

                if timeout_secs is not None:
                    if not self.start_timestamp:
                        self.start_timestamp = timestamp
                    if (timestamp - self.start_timestamp > timeout_secs * 1e9):
                        debug("timed out: %d - %d > %d" % (
                            timestamp, self.start_timestamp,
                            timeout_secs * 1e9))
                        return

                image = gst_to_opencv(buf)
                try:
                    yield (image, timestamp)
                finally:
                    self.push_buffer(buf, image)

    def on_new_buffer(self, appsink):
        buf = appsink.emit("pull-buffer")
        self.tell_user_thread(buf)
        if self.lock.acquire(False):  # non-blocking
            try:
                self.push_buffer(buf)
            finally:
                self.lock.release()

    def tell_user_thread(self, buffer_or_exception):
        # `self.last_buffer` (a synchronised Queue) is how we communicate from
        # this thread (the GLib main loop) to the main application thread
        # running the user's script. Note that only this thread writes to the
        # Queue.

        if isinstance(buffer_or_exception, Exception):
            ddebug("glib thread: reporting exception to user thread: %s" %
                   buffer_or_exception)
        else:
            ddebug("glib thread: new buffer (timestamp=%s). Queue.qsize: %d" %
                   (buffer_or_exception.timestamp, self.last_buffer.qsize()))

        # Drop old frame
        try:
            self.last_buffer.get_nowait()
        except Queue.Empty:
            pass

        self.last_buffer.put_nowait(buffer_or_exception)

    def draw_text(self, text, duration_secs):
        """Draw the specified text on the output video."""
        self.video_debug.append((text, duration_secs, None))

    def push_buffer(self, gst_buffer, opencv_image=None):
        for text, duration, timeout in list(self.video_debug):
            if timeout is None:
                timeout = gst_buffer.timestamp + (duration * 1e9)
                self.video_debug.remove((text, duration, None))
                self.video_debug.append((text, duration, timeout))
            if (gst_buffer.timestamp > timeout):
                self.video_debug.remove((text, duration, timeout))

        if opencv_image is None and len(self.video_debug) == 0:
            self.appsrc.emit("push-buffer", gst_buffer)
        else:
            if opencv_image is None:
                opencv_image = gst_to_opencv(gst_buffer)
            for i in range(len(self.video_debug)):
                text, _, _ = self.video_debug[len(self.video_debug) - i - 1]
                cv2.putText(
                    opencv_image, text, (10, (i + 1) * 30),
                    cv2.FONT_HERSHEY_TRIPLEX, fontScale=1.0,
                    color=(255, 255, 255))
            newbuf = gst.Buffer(opencv_image.data)
            newbuf.set_caps(gst_buffer.get_caps())
            newbuf.timestamp = gst_buffer.timestamp
            self.appsrc.emit("push-buffer", newbuf)

    def on_error(self, _bus, message):
        assert message.type == gst.MESSAGE_ERROR
        err, dbg = message.parse_error()
        self.tell_user_thread(
            UITestError("%s: %s\n%s\n" % (err, err.message, dbg)))
        _mainloop.quit()

    @staticmethod
    def on_warning(_bus, message):
        assert message.type == gst.MESSAGE_WARNING
        err, dbg = message.parse_warning()
        sys.stderr.write("Warning: %s: %s\n%s\n" % (err, err.message, dbg))

    def on_eos_from_source_pipeline(self, _bus, _message):
        warn("Got EOS from source pipeline")
        self.restart_source()

    def on_eos_from_sink_pipeline(self, _bus, _message):
        debug("Got EOS")
        _mainloop.quit()

    def on_underrun(self, _element):
        if self.underrun_timeout:
            ddebug("underrun: I already saw a recent underrun; ignoring")
        else:
            ddebug("underrun: scheduling 'restart_source' in 2s")
            self.underrun_timeout = GObjectTimeout(2, self.restart_source)
            self.underrun_timeout.start()

    def on_running(self, _element):
        if self.underrun_timeout:
            ddebug("running: cancelling underrun timer")
            self.underrun_timeout.cancel()
            self.underrun_timeout = None
        else:
            ddebug("running: no outstanding underrun timers; ignoring")

    def restart_source(self, *_args):
        warn("Attempting to recover from video loss: "
             "Stopping source pipeline and waiting 5s...")
        self.source_pipeline.set_state(gst.STATE_NULL)
        self.source_pipeline = None
        GObjectTimeout(5, self.start_source).start()
        return False  # stop the timeout from running again

    def start_source(self):
        warn("Restarting source pipeline...")
        self.create_source_pipeline()
        self.source_pipeline.set_state(gst.STATE_PLAYING)
        warn("Restarted source pipeline")
        if self.restart_source_enabled:
            self.underrun_timeout.start()
        return False  # stop the timeout from running again

    def teardown(self):
        if self.source_pipeline:
            self.source_pipeline.set_state(gst.STATE_NULL)
        if not self.novideo:
            debug("teardown: Sending eos")
            self.appsrc.emit("end-of-stream")
            self.mainloop_thread.join(10)
            debug("teardown: Exiting (GLib mainloop %s)" % (
                "is still alive!" if self.mainloop_thread.isAlive() else "ok"))


class GObjectTimeout:
    """Responsible for setting a timeout in the GTK main loop."""
    def __init__(self, timeout_secs, handler, *args):
        self.timeout_secs = timeout_secs
        self.handler = handler
        self.args = args
        self.timeout_id = None

    def start(self):
        self.timeout_id = gobject.timeout_add(
            self.timeout_secs * 1000, self.handler, *self.args)

    def cancel(self):
        if self.timeout_id:
            gobject.source_remove(self.timeout_id)
        self.timeout_id = None


def gst_to_opencv(gst_buffer):
    return numpy.ndarray(
        (gst_buffer.get_caps().get_structure(0)["height"],
         gst_buffer.get_caps().get_structure(0)["width"],
         3),
        buffer=gst_buffer.data,
        dtype=numpy.uint8)


def _match(image, template, match_parameters, template_name):
    if any(image.shape[x] < template.shape[x] for x in (0, 1)):
        raise ValueError("Source image must be larger than template image")

    matched, position, first_pass_certainty = _find_match(
        image, template, match_parameters)
    if matched:
        matched = _confirm_match(image, position, template, match_parameters)

    cv2.rectangle(
        image,
        (position.x, position.y),
        (position.x + template.shape[1], position.y + template.shape[0]),
        (32, 0 if matched else 255, 255),  # bgr
        thickness=3)

    if _debug_level > 1:
        _log_image(image, "source_with_roi", "stbt-debug/detect_match")
        _log_image_descriptions(
            template_name, matched, position, first_pass_certainty,
            match_parameters)

    return matched, position, first_pass_certainty


def _find_match(image, template, match_parameters):
    """Search for `template` in the entire `image`.

    This searches the entire image, so speed is more important than accuracy.
    False positives are ok; we apply a second pass (`_confirm_match`) to weed
    out false positives.

    http://docs.opencv.org/modules/imgproc/doc/object_detection.html
    http://opencv-code.com/tutorials/fast-template-matching-with-image-pyramid
    """

    log = functools.partial(_log_image, directory="stbt-debug/detect_match")
    log(image, "source")
    log(template, "template")
    ddebug("Original image %s, template %s" % (image.shape, template.shape))

    levels = get_config("match", "pyramid_levels", type_=int)
    if levels <= 0:
        raise ConfigurationError("'match.pyramid_levels' must be > 0")
    template_pyramid = _build_pyramid(template, levels)
    image_pyramid = _build_pyramid(image, len(template_pyramid))
    roi_mask = None  # Initial region of interest: The whole image.

    for level in reversed(range(len(template_pyramid))):

        matched, best_match_position, certainty, roi_mask = _match_template(
            image_pyramid[level], template_pyramid[level], match_parameters,
            roi_mask, level)

        if level == 0 or not matched:
            return matched, _upsample(best_match_position, level), certainty


def _match_template(image, template, match_parameters, roi_mask, level):

    log = functools.partial(_log_image, directory="stbt-debug/detect_match")
    log_prefix = "level%d-" % level
    ddebug("Level %d: image %s, template %s" % (
        level, image.shape, template.shape))

    method = {
        'sqdiff-normed': cv2.TM_SQDIFF_NORMED,
        'ccorr-normed': cv2.TM_CCORR_NORMED,
        'ccoeff-normed': cv2.TM_CCOEFF_NORMED,
    }[match_parameters.match_method]
    threshold = max(
        0,
        match_parameters.match_threshold - (0.2 if level > 0 else 0))

    matches_heatmap = (
        (numpy.ones if method == cv2.TM_SQDIFF_NORMED else numpy.zeros)(
            (image.shape[0] - template.shape[0] + 1,
             image.shape[1] - template.shape[1] + 1),
            dtype=numpy.float32))

    if roi_mask is None or any(x < 3 for x in roi_mask.shape):
        rois = [  # Initial region of interest: The whole image.
            _Rect(0, 0, matches_heatmap.shape[1], matches_heatmap.shape[0])]
    else:
        roi_mask = cv2.pyrUp(roi_mask)
        log(roi_mask, log_prefix + "roi_mask")
        contours, _ = cv2.findContours(
            roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        rois = [
            _Rect(*cv2.boundingRect(x))
            # findContours ignores 1-pixel border of the image
            .shift(Position(-1, -1)).expand(_Size(2, 2))
            for x in contours]

    if _debug_level > 1:
        source_with_rois = image.copy()
        for roi in rois:
            r = roi
            t = _Size(*template.shape[:2])
            s = _Size(*source_with_rois.shape[:2])
            cv2.rectangle(
                source_with_rois,
                (max(0, r.x), max(0, r.y)),
                (min(s.w - 1, r.x + r.w + t.w - 1),
                 min(s.h - 1, r.y + r.h + t.h - 1)),
                (0, 255, 255),
                thickness=1)
        log(source_with_rois, log_prefix + "source_with_rois")

    for roi in rois:
        r = roi.expand(_Size(*template.shape[:2])).shrink(_Size(1, 1))
        ddebug("Level %d: Searching in %s" % (level, roi))
        cv2.matchTemplate(
            image[r.to_slice()],
            template,
            method,
            matches_heatmap[roi.to_slice()])

    log(image, log_prefix + "source")
    log(template, log_prefix + "template")
    log(matches_heatmap, log_prefix + "source_matchtemplate")

    min_value, max_value, min_location, max_location = cv2.minMaxLoc(
        matches_heatmap)
    if method == cv2.TM_SQDIFF_NORMED:
        certainty = (1 - min_value)
        best_match_position = Position(*min_location)
    elif method in (cv2.TM_CCORR_NORMED, cv2.TM_CCOEFF_NORMED):
        certainty = max_value
        best_match_position = Position(*max_location)
    else:
        assert False, (
            "Invalid matchTemplate method '%s'" % method)

    _, new_roi_mask = cv2.threshold(
        matches_heatmap,
        ((1 - threshold) if method == cv2.TM_SQDIFF_NORMED else threshold),
        255,
        (cv2.THRESH_BINARY_INV if method == cv2.TM_SQDIFF_NORMED
         else cv2.THRESH_BINARY))
    new_roi_mask = new_roi_mask.astype(numpy.uint8)
    log(new_roi_mask, log_prefix + "source_matchtemplate_threshold")

    matched = certainty >= threshold
    ddebug("Level %d: %s at %s with certainty %s" % (
        level, "Matched" if matched else "Didn't match",
        best_match_position, certainty))
    return (matched, best_match_position, certainty, new_roi_mask)


def _build_pyramid(image, levels):
    """A "pyramid" is [an image, the same image at 1/2 the size, at 1/4, ...]

    As a performance optimisation, image processing algorithms work on a
    "pyramid" by first identifying regions of interest (ROIs) in the smallest
    image; if results are positive, they proceed to the next larger image, etc.
    See http://docs.opencv.org/doc/tutorials/imgproc/pyramids/pyramids.html

    The original-sized image is called "level 0", the next smaller image "level
    1", and so on. This numbering corresponds to the array index of the
    "pyramid" array.
    """
    pyramid = [image]
    for _ in range(levels - 1):
        if any(x < 20 for x in pyramid[-1].shape[:2]):
            break
        pyramid.append(cv2.pyrDown(pyramid[-1]))
    return pyramid


def _upsample(position, levels):
    """Convert position coordinates by the given number of pyramid levels.

    There is a loss of precision (unless ``levels`` is 0, in which case this
    function is a no-op).
    """
    return Position(position.x * 2 ** levels, position.y * 2 ** levels)


# Order of parameters consistent with ``cv2.boudingRect``.
class _Rect(namedtuple("_Rect", "x y w h")):
    def expand(self, size):
        return _Rect(self.x, self.y, self.w + size.w, self.h + size.h)

    def shrink(self, size):
        return _Rect(self.x, self.y, self.w - size.w, self.h - size.h)

    def shift(self, position):
        return _Rect(self.x + position.x, self.y + position.y, self.w, self.h)

    def to_slice(self):
        """Return a 2-dimensional slice suitable for indexing a numpy array."""
        return (slice(self.y, self.y + self.h), slice(self.x, self.x + self.w))


# Order of parameters consistent with OpenCV's ``numpy.ndarray.shape``.
class _Size(namedtuple("_Size", "h w")):
    pass


def _confirm_match(image, position, template, match_parameters):
    """Confirm that `template` matches `image` at `position`.

    This only checks `template` at a single position within `image`, so we can
    afford to do more computationally-intensive checks than `_find_match`.
    """

    if match_parameters.confirm_method == "none":
        return True

    log = functools.partial(_log_image, directory="stbt-debug/detect_match")

    # Set Region Of Interest to the "best match" location
    roi = image[
        position.y:(position.y + template.shape[0]),
        position.x:(position.x + template.shape[1])]
    image_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    log(roi, "confirm-source_roi")
    log(image_gray, "confirm-source_roi_gray")
    log(template_gray, "confirm-template_gray")

    if match_parameters.confirm_method == "normed-absdiff":
        cv2.normalize(image_gray, image_gray, 0, 255, cv2.NORM_MINMAX)
        cv2.normalize(template_gray, template_gray, 0, 255, cv2.NORM_MINMAX)
        log(image_gray, "confirm-source_roi_gray_normalized")
        log(template_gray, "confirm-template_gray_normalized")

    absdiff = cv2.absdiff(image_gray, template_gray)
    _, thresholded = cv2.threshold(
        absdiff, int(match_parameters.confirm_threshold * 255),
        255, cv2.THRESH_BINARY)
    eroded = cv2.erode(
        thresholded,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=match_parameters.erode_passes)
    log(absdiff, "confirm-absdiff")
    log(thresholded, "confirm-absdiff_threshold")
    log(eroded, "confirm-absdiff_threshold_erode")

    return (cv2.countNonZero(eroded) == 0)


_frame_number = 0


def _log_image(image, name, directory):
    if _debug_level <= 1:
        return
    global _frame_number
    if name == "source":
        _frame_number += 1
    d = os.path.join(directory, "%05d" % _frame_number)
    if not _mkdir(d):
        warn("Failed to create directory '%s'; won't save debug images." % d)
        return
    if image.dtype == numpy.float32:
        image = cv2.convertScaleAbs(image, alpha=255)
    cv2.imwrite(os.path.join(d, name) + ".png", image)


def _log_image_descriptions(
        template_name, matched, position, first_pass_certainty,
        match_parameters):
    """Create html file that describes the debug images."""

    try:
        import jinja2
    except ImportError:
        warn(
            "Not generating html guide to the image-processing debug images, "
            "because python 'jinja2' module is not installed.")
        return

    d = os.path.join("stbt-debug/detect_match", "%05d" % _frame_number)

    template = jinja2.Template("""
        <!DOCTYPE html>
        <html lang='en'>
        <head>
        <link href="http://netdna.bootstrapcdn.com/twitter-bootstrap/2.3.2/css/bootstrap-combined.min.css" rel="stylesheet">
        <style>
            img {
                vertical-align: middle; max-width: 300px; max-height: 36px;
                padding: 1px; border: 1px solid #ccc; }
            p, li { line-height: 40px; }
        </style>
        </head>
        <body>
        <div class="container">
        <h4>
            <i>{{template_name}}</i>
            {{"matched" if matched else "didn't match"}}
        </h4>

        <p>Searching for <b>template</b> {{link("template")}}
            within <b>source</b> {{link("source")}} image.

        {% for level in levels %}

            <p>At level <b>{{level}}</b>:
            <ul>
                <li>Searching for <b>template</b> {{link("template", level)}}
                    within <b>source regions of interest</b>
                    {{link("source_with_rois", level)}}.
                <li>OpenCV <b>matchTemplate result</b>
                    {{link("source_matchtemplate", level)}}
                    with method {{match_parameters.match_method}}
                    ({{"darkest" if match_parameters.match_method ==
                            "sqdiff-normed" else "lightest"}}
                    pixel indicates position of best match).
                <li>matchTemplate result <b>above match_threshold</b>
                    {{link("source_matchtemplate_threshold", level)}}
                    of {{"%.2f"|format(match_parameters.match_threshold)}}
                    (white pixels indicate positions above the threshold).

            {% if level == 0 %}
                <li>Matched at {{position}} {{link("source_with_roi")}}
                    with certainty {{"%.2f"|format(first_pass_certainty)}}.
            {% else %}
                <li>Didn't match (best match at {{position}}
                    {{link("source_with_roi")}}
                    with certainty {{"%.2f"|format(first_pass_certainty)}}).
            {% endif %}

            </ul>

        {% endfor %}

        {% if first_pass_certainty >= match_parameters.match_threshold %}
            <p><b>Second pass (confirmation):</b>
            <ul>
                <li>Comparing <b>template</b> {{link("confirm-template_gray")}}
                    against <b>source image's region of interest</b>
                    {{link("confirm-source_roi_gray")}}.

            {% if match_parameters.confirm_method == "normed-absdiff" %}
                <li>Normalised <b>template</b>
                    {{link("confirm-template_gray_normalized")}}
                    and <b>source</b>
                    {{link("confirm-source_roi_gray_normalized")}}.
            {% endif %}

                <li><b>Absolute differences</b> {{link("confirm-absdiff")}}.
                <li>Differences <b>above confirm_threshold</b>
                    {{link("confirm-absdiff_threshold")}}
                    of {{"%.2f"|format(match_parameters.confirm_threshold)}}.
                <li>After <b>eroding</b>
                    {{link("confirm-absdiff_threshold_erode")}}
                    {{match_parameters.erode_passes}}
                    {{"time" if match_parameters.erode_passes == 1
                        else "times"}}.
                    {{"No" if matched else "Some"}}
                    differences (white pixels) remain, so the template
                    {{"does" if matched else "doesn't"}} match.
            </ul>
        {% endif %}

        <p>For further help please read
            <a href="http://stb-tester.com/match-parameters.html">stb-tester
            image matching parameters</a>.

        </div>
        </body>
        </html>
    """)

    with open(os.path.join(d, "index.html"), "w") as f:
        f.write(template.render(
            first_pass_certainty=first_pass_certainty,
            levels=reversed(sorted(set(
                [int(re.search(r"level(\d+)-.*", x).group(1))
                 for x in glob.glob(os.path.join(d, "level*"))]))),
            link=lambda s, level=None: (
                "<a href='{0}{1}.png'><img src='{0}{1}.png'></a>"
                .format("" if level is None else "level%d-" % level, s)),
            match_parameters=match_parameters,
            matched=matched,
            position=position,
            template_name=template_name,
        ))


def uri_to_remote(uri, display):
    if uri.lower() == 'none':
        return NullRemote()
    if uri.lower() == 'test':
        return VideoTestSrcControl(display)
    vr = re.match(r'vr:(?P<hostname>[^:]*)(:(?P<port>\d+))?', uri)
    if vr:
        d = vr.groupdict()
        return VirtualRemote(d['hostname'], int(d['port'] or 2033))
    tcp_lirc = re.match(
        r'lirc(:(?P<hostname>[^:]*))?:(?P<port>\d+):(?P<control_name>.*)', uri)
    if tcp_lirc:
        d = tcp_lirc.groupdict()
        return new_tcp_lirc_remote(d['hostname'] or 'localhost',
                                   int(d['port']), d['control_name'])
    lirc = re.match(r'lirc:(?P<lircd_socket>[^:]*):(?P<control_name>.*)', uri)
    if lirc:
        d = lirc.groupdict()
        return new_local_lirc_remote(d['lircd_socket'] or '/var/run/lirc/lircd',
                                     d['control_name'])
    irnb = re.match(
        r'''irnetbox:
            (?P<hostname>[^:]+)
            (:(?P<port>\d+))?
            :(?P<output>\d+)
            :(?P<config>[^:]+)''',
        uri,
        re.VERBOSE)
    if irnb:
        d = irnb.groupdict()
        return IRNetBoxRemote(
            d['hostname'], int(d['port'] or 10001), d['output'], d['config'])
    raise ConfigurationError('Invalid remote control URI: "%s"' % uri)


class NullRemote:
    @staticmethod
    def press(key):
        debug('NullRemote: Ignoring request to press "%s"' % key)


class VideoTestSrcControl:
    """Remote control used by selftests.

    Changes the videotestsrc image to the specified pattern ("0" to "20").
    See `gst-inspect videotestsrc`.
    """

    def __init__(self, display):
        self.videosrc = display.source_pipeline.get_by_name("videotestsrc0")
        if not self.videosrc:
            raise ConfigurationError('The "test" control can only be used'
                                     'with source-pipeline = "videotestsrc"')

    def press(self, key):
        if key not in [
                0, "smpte",
                1, "snow",
                2, "black",
                3, "white",
                4, "red",
                5, "green",
                6, "blue",
                7, "checkers-1",
                8, "checkers-2",
                9, "checkers-4",
                10, "checkers-8",
                11, "circular",
                12, "blink",
                13, "smpte75",
                14, "zone-plate",
                15, "gamut",
                16, "chroma-zone-plate",
                17, "solid-color",
                18, "ball",
                19, "smpte100",
                20, "bar"]:
            raise UITestFailure(
                'Key "%s" not valid for the "test" control' % key)
        self.videosrc.props.pattern = key
        debug("Pressed %s" % key)


class VirtualRemote:
    """Send a key-press to a set-top box running a VirtualRemote listener.

        control = VirtualRemote("192.168.0.123")
        control.press("MENU")
    """

    def __init__(self, hostname, port):
        self.hostname = hostname
        self.port = port
        # Connect once so that the test fails immediately if STB not found
        # (instead of failing at the first `press` in the script).
        debug("VirtualRemote: Connecting to %s:%d" % (hostname, port))
        self._connect()
        debug("VirtualRemote: Connected to %s:%d" % (hostname, port))

    def press(self, key):
        self._connect().sendall(
            "D\t%s\n\x00U\t%s\n\x00" % (key, key))  # key Down, then Up
        debug("Pressed " + key)

    def _connect(self):
        return _connect_tcp_socket(self.hostname, self.port)


class LircRemote:
    """Send a key-press via a LIRC-enabled infrared blaster.

    See http://www.lirc.org/html/technical.html#applications
    """

    def __init__(self, control_name, connect_fn):
        self.control_name = control_name
        self._connect = connect_fn

    def press(self, key):
        s = self._connect()
        s.sendall("SEND_ONCE %s %s\n" % (self.control_name, key))
        _read_lircd_reply(s)
        debug("Pressed " + key)


def new_local_lirc_remote(lircd_socket, control_name):
    def _connect():
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect(lircd_socket)
            return s
        except socket.error as e:
            e.args = (("Failed to connect to Lirc socket %s: %s" % (
                lircd_socket, e)),)
            e.strerror = e.args[0]
            raise

    # Connect once so that the test fails immediately if Lirc isn't running
    # (instead of failing at the first `press` in the script).
    debug("LircRemote: Connecting to %s" % lircd_socket)
    _connect()
    debug("LircRemote: Connected to %s" % lircd_socket)

    return LircRemote(control_name, _connect)


def new_tcp_lirc_remote(hostname, port, control_name):
    """Send a key-press via a LIRC-enabled device through a LIRC TCP listener.

        control = new_tcp_lirc_remote("localhost", "8765", "humax")
        control.press("MENU")
    """
    def _connect():
        return _connect_tcp_socket(hostname, port)

    # Connect once so that the test fails immediately if Lirc isn't running
    # (instead of failing at the first `press` in the script).
    debug("TCPLircRemote: Connecting to %s:%d" % (hostname, port))
    _connect()
    debug("TCPLircRemote: Connected to %s:%d" % (hostname, port))

    return LircRemote(control_name, _connect)


class IRNetBoxRemote:
    """Send a key-press via the network-controlled RedRat IRNetBox IR emitter.

    See http://www.redrat.co.uk/products/irnetbox.html

    """

    def __init__(self, hostname, port, output, config_file):
        self.hostname = hostname
        self.port = port
        self.output = int(output)
        self.config = irnetbox.RemoteControlConfig(config_file)
        # Connect once so that the test fails immediately if irNetBox not found
        # (instead of failing at the first `press` in the script).
        debug("IRNetBoxRemote: Connecting to %s" % hostname)
        with self._connect() as irnb:
            irnb.power_on()
        time.sleep(0.5)
        debug("IRNetBoxRemote: Connected to %s" % hostname)

    def press(self, key):
        with self._connect() as irnb:
            irnb.irsend_raw(
                port=self.output, power=100, data=self.config[key])
        debug("Pressed " + key)

    def _connect(self):
        try:
            return irnetbox.IRNetBox(self.hostname, self.port)
        except socket.error as e:
            e.args = (("Failed to connect to IRNetBox %s: %s" % (
                self.hostname, e)),)
            e.strerror = e.args[0]
            raise


def uri_to_remote_recorder(uri):
    vr = re.match(r'vr:(?P<hostname>[^:]*)(:(?P<port>\d+))?', uri)
    if vr:
        d = vr.groupdict()
        return virtual_remote_listen(d['hostname'], int(d['port'] or 2033))
    tcp_lirc = re.match(
        r'lirc(:(?P<hostname>[^:]*))?:(?P<port>\d+):(?P<control_name>.*)', uri)
    if tcp_lirc:
        d = tcp_lirc.groupdict()
        return lirc_remote_listen_tcp(d['hostname'] or 'localhost',
                                      int(d['port']), d['control_name'])
    lirc = re.match(r'lirc:(?P<lircd_socket>[^:]*):(?P<control_name>.*)', uri)
    if lirc:
        d = lirc.groupdict()
        return lirc_remote_listen(d['lircd_socket'] or '/var/run/lirc/lircd',
                                  d['control_name'])
    f = re.match('file://(?P<filename>.+)', uri)
    if f:
        return file_remote_recorder(f.group('filename'))
    stbt_control = re.match(r'stbt-control(:(?P<keymap_file>.+))?', uri)
    if stbt_control:
        d = stbt_control.groupdict()
        return stbt_control_listen(d['keymap_file'])
    raise ConfigurationError('Invalid remote control recorder URI: "%s"' % uri)


def file_remote_recorder(filename):
    """ A generator that returns lines from the file given by filename.

    Unfortunately treating a file as a iterator doesn't work in the case of
    interactive input, even when we provide bufsize=1 (line buffered) to the
    call to open() so we have to have this function to work around it. """
    f = open(filename, 'r')
    if filename == '/dev/stdin':
        sys.stderr.write('Waiting for keypresses from standard input...\n')
    while True:
        line = f.readline()
        if line == '':
            f.close()
            raise StopIteration
        yield line.rstrip()


def read_records(stream, sep):
    r"""Generator that splits stream into records given a separator

    >>> import StringIO
    >>> s = StringIO.StringIO('hello\n\0This\n\0is\n\0a\n\0test\n\0')
    >>> list(read_records(FileToSocket(s), '\n\0'))
    ['hello', 'This', 'is', 'a', 'test']
    """
    buf = ""
    while True:
        s = stream.recv(4096)
        if len(s) == 0:
            break
        buf += s
        cmds = buf.split(sep)
        buf = cmds[-1]
        for i in cmds[:-1]:
            yield i


def vr_key_reader(cmd_iter):
    r"""Converts virtual remote records into list of keypresses

    >>> list(vr_key_reader(['D\tHELLO', 'U\tHELLO']))
    ['HELLO']
    >>> list(vr_key_reader(['D\tCHEESE', 'D\tHELLO', 'U\tHELLO', 'U\tCHEESE']))
    ['HELLO', 'CHEESE']
    """
    for i in cmd_iter:
        (action, key) = i.split('\t')
        if action == 'U':
            yield key


def virtual_remote_listen(address, port):
    """Waits for a VirtualRemote to connect, and returns an iterator yielding
    keypresses."""
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind((address, port))
    serversocket.listen(5)
    sys.stderr.write("Waiting for connection from virtual remote control "
                     "on %s:%d...\n" % (address, port))
    (connection, address) = serversocket.accept()
    sys.stderr.write("Accepted connection from %s\n" % str(address))
    return vr_key_reader(read_records(connection, '\n\x00'))


def lirc_remote_listen(lircd_socket, control_name):
    """Returns an iterator yielding keypresses received from a lircd file
    socket.

    See http://www.lirc.org/html/technical.html#applications
    """
    lircd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    debug("control-recorder connecting to lirc file socket '%s'..." %
          lircd_socket)
    lircd.connect(lircd_socket)
    debug("control-recorder connected to lirc file socket")
    return lirc_key_reader(lircd.makefile(), control_name)


def lirc_remote_listen_tcp(address, port, control_name):
    """Returns an iterator yielding keypresses received from a lircd TCP
    socket."""
    debug("control-recorder connecting to lirc TCP socket %s:%s..." %
          (address, port))
    lircd = _connect_tcp_socket(address, port, timeout=None)
    debug("control-recorder connected to lirc TCP socket")
    return lirc_key_reader(lircd.makefile(), control_name)


def stbt_control_listen(keymap_file):
    """Returns an iterator yielding keypresses received from `stbt control`.
    """
    import imp
    tool_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'stbt-control')
    stbt_control = imp.load_source('stbt_control', tool_path)

    global _debug_level
    _debug_level = 0  # Don't mess up printed keymap with debug messages
    return stbt_control.main_loop(
        'stbt record', keymap_file or stbt_control.default_keymap_file())


def lirc_key_reader(cmd_iter, control_name):
    r"""Convert lircd messages into list of keypresses

    >>> list(lirc_key_reader(['0000dead 00 MENU My-IR-remote',
    ...                       '0000beef 00 OK My-IR-remote',
    ...                       '0000f00b 01 OK My-IR-remote',
    ...                       'BEGIN', 'SIGHUP', 'END'],
    ...                      'My-IR-remote'))
    ['MENU', 'OK']
    """
    for s in cmd_iter:
        debug("lirc_key_reader received: %s" % s.rstrip())
        m = re.match(
            r"\w+ (?P<repeat_count>\d+) (?P<key>\w+) %s" % control_name,
            s)
        if m and int(m.group('repeat_count')) == 0:
            yield m.group('key')


def _connect_tcp_socket(address, port, timeout=3):
    """Connects to a TCP listener on 'address':'port'."""
    try:
        s = socket.socket()
        if timeout:
            s.settimeout(timeout)
        s.connect((address, port))
        return s
    except socket.error as e:
        e.args = (("Failed to connect to remote at %s:%d: %s" % (
            address, port, e)),)
        e.strerror = e.args[0]
        raise


def _read_lircd_reply(stream):
    """Waits for lircd reply and checks if a LIRC send command was successful.

    Waits for a reply message from lircd (called "reply packet" in the LIRC
    reference) for a SEND_ONCE command, raises exception if it times out or
    the reply contains an error message.

    The structure of a lircd reply message for a SEND_ONCE command is the
    following:

    BEGIN
    <command>
    (SUCCESS|ERROR)
    [DATA
    <number-of-data-lines>
    <error-message>]
    END

    See: http://www.lirc.org/html/technical.html#applications
    """
    reply = []
    try:
        for line in read_records(stream, "\n"):
            if line == "BEGIN":
                reply = []
            reply.append(line)
            if line == "END" and "SEND_ONCE" in reply[1]:
                break
    except socket.timeout:
        raise UITestError(
            "Timed out: No reply from LIRC remote control within %d seconds"
            % stream.gettimeout())
    if not "SUCCESS" in reply:
        if "ERROR" in reply and len(reply) >= 6 and reply[3] == "DATA":
            num_data_lines = int(reply[4])
            raise UITestError("LIRC remote control returned error: %s"
                              % " ".join(reply[5:5 + num_data_lines]))
        raise UITestError("LIRC remote control returned unknown error")


def _find_path(image):
    """Searches for the given filename and returns the full path.

    Searches in the directory of the script that called (for example)
    detect_match, then in the directory of that script's caller, etc.
    """

    if os.path.isabs(image):
        return image

    # stack()[0] is _find_path;
    # stack()[1] is _find_path's caller, e.g. detect_match;
    # stack()[2] is detect_match's caller (the user script).
    for caller in inspect.stack()[2:]:
        caller_image = os.path.join(
            os.path.dirname(inspect.getframeinfo(caller[0]).filename),
            image)
        if os.path.isfile(caller_image):
            return os.path.abspath(caller_image)

    # Fall back to image from cwd, for convenience of the selftests
    return os.path.abspath(image)


def _mkdir(d):
    try:
        os.makedirs(d)
    except OSError, e:
        if e.errno != errno.EEXIST:
            return False
    return os.path.isdir(d) and os.access(d, os.R_OK | os.W_OK)


def ddebug(s):
    """Extra verbose debug for stbt developers, not end users"""
    if _debug_level > 1:
        sys.stderr.write("%s: %s\n" % (os.path.basename(sys.argv[0]), str(s)))


def warn(s):
    sys.stderr.write("%s: warning: %s\n" % (
        os.path.basename(sys.argv[0]), str(s)))


# Tests
#===========================================================================

class FileToSocket:
    """Makes something File-like behave like a Socket for testing purposes

    >>> import StringIO
    >>> s = FileToSocket(StringIO.StringIO("Hello"))
    >>> s.recv(3)
    'Hel'
    >>> s.recv(3)
    'lo'
    """
    def __init__(self, f):
        self.file = f

    def recv(self, bufsize, flags=0):  # pylint: disable=W0613
        return self.file.read(bufsize)


def test_that_virtual_remote_is_symmetric_with_virtual_remote_listen():
    received = []
    keys = ['DOWN', 'DOWN', 'UP', 'GOODBYE']

    def listener():
        # "* 2" is once for VirtualRemote's __init__ and once for press.
        for _ in range(len(keys) * 2):
            for k in virtual_remote_listen('localhost', 2033):
                received.append(k)

    t = threading.Thread()
    t.daemon = True
    t.run = listener
    t.start()
    for k in keys:
        time.sleep(0.1)  # Give listener a chance to start listening (sorry)
        vr = VirtualRemote('localhost', 2033)
        time.sleep(0.1)
        vr.press(k)
    t.join()
    assert received == keys


def test_that_lirc_remote_is_symmetric_with_lirc_remote_listen():
    import tempfile

    keys = ['DOWN', 'DOWN', 'UP', 'GOODBYE']

    def fake_lircd(address):
        # This needs to accept 2 connections (from LircRemote and
        # lirc_remote_listen) and, on receiving input from the LircRemote
        # connection, write to the lirc_remote_listen connection.
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(address)
        s.listen(5)
        listener, _ = s.accept()
        # "+ 1" is for LircRemote's __init__.
        for _ in range(len(keys) + 1):
            control, _ = s.accept()
            for cmd in control.makefile():
                m = re.match(r'SEND_ONCE (?P<control>\w+) (?P<key>\w+)', cmd)
                if m:
                    d = m.groupdict()
                    message = '00000000 0 %s %s\n' % (d['key'], d['control'])
                    listener.sendall(message)
                control.sendall('BEGIN\n%sSUCCESS\nEND\n' % cmd)

    lircd_socket = tempfile.mktemp()
    t = threading.Thread()
    t.daemon = True
    t.run = lambda: fake_lircd(lircd_socket)
    t.start()
    time.sleep(0.01)  # Give it a chance to start listening (sorry)
    listener = lirc_remote_listen(lircd_socket, 'test')
    control = new_local_lirc_remote(lircd_socket, 'test')
    for i in keys:
        control.press(i)
        assert listener.next() == i
    t.join()


def test_uri_to_remote():
    global IRNetBoxRemote  # pylint: disable=W0601
    orig_IRNetBoxRemote = IRNetBoxRemote
    try:
        IRNetBoxRemote = lambda *args: ":".join([str(x) for x in args])
        out = uri_to_remote("irnetbox:localhost:1234:1:conf", None)
        assert out == "localhost:1234:1:conf", (
            "Failed to parse uri with irnetbox port. Output was '%s'" % out)
        out = uri_to_remote("irnetbox:localhost:1:conf", None)
        assert out == "localhost:10001:1:conf", (
            "Failed to parse uri without irnetbox port. Output was '%s'" % out)
        try:
            uri_to_remote("irnetbox:localhost::1:conf", None)
            assert False, "Uri with empty field should have raised"
        except ConfigurationError:
            pass
    finally:
        IRNetBoxRemote = orig_IRNetBoxRemote


def test_wait_for_motion_half_motion_str_2of4():
    with _fake_frames_at_half_motion():
        wait_for_motion(consecutive_frames='2/4')


def test_wait_for_motion_half_motion_str_2of3():
    with _fake_frames_at_half_motion():
        wait_for_motion(consecutive_frames='2/3')


def test_wait_for_motion_half_motion_str_3of4():
    with _fake_frames_at_half_motion():
        try:
            wait_for_motion(consecutive_frames='3/4')
            assert False, "wait_for_motion succeeded unexpectedly"
        except MotionTimeout:
            pass


def test_wait_for_motion_half_motion_int():
    with _fake_frames_at_half_motion():
        try:
            wait_for_motion(consecutive_frames=2)
            assert False, "wait_for_motion succeeded unexpectedly"
        except MotionTimeout:
            pass


@contextlib.contextmanager
def _fake_frames_at_half_motion():
    class FakeDisplay:
        def frames(self, _timeout_secs=10):
            for i in range(10):
                yield (
                    [
                        numpy.zeros((2, 2, 3), dtype=numpy.uint8),
                        numpy.ones((2, 2, 3), dtype=numpy.uint8) * 255,
                    ][(i / 2) % 2],
                    i * 1000000000)

    def _get_frame():
        return None

    global _display, get_frame  # pylint: disable=W0601
    orig_display, orig_get_frame = _display, get_frame
    _display, get_frame = FakeDisplay(), _get_frame
    yield
    _display, get_frame = orig_display, orig_get_frame
