# coding: utf-8
"""Main stb-tester python module. Intended to be used with `stbt run`.

See `man stbt` and http://stb-tester.com for documentation.

Copyright 2012-2013 YouView TV Ltd and contributors.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""

from __future__ import absolute_import

import argparse
import datetime
import errno
import functools
import inspect
import itertools
import os
import Queue
import re
import subprocess
import threading
import time
import traceback
import warnings
from collections import deque, namedtuple
from contextlib import contextmanager
from distutils.version import LooseVersion

import cv2
import gi
import numpy
from enum import IntEnum
from kitchen.text.converters import to_bytes

from _stbt import imgproc_cache, logging, utils
from _stbt.config import ConfigurationError, get_config
from _stbt.gst_utils import (array_from_sample, get_frame_timestamp,
                             gst_iterate, gst_sample_make_writable,
                             sample_shape)
from _stbt.logging import ddebug, debug, warn

gi.require_version("Gst", "1.0")
from gi.repository import GLib, GObject, Gst  # isort:skip pylint: disable=E0611

Gst.init(None)

warnings.filterwarnings(
    action="always", category=DeprecationWarning, message='.*stb-tester')


# Functions available to stbt scripts
# ===========================================================================


class MatchParameters(object):
    """Parameters to customise the image processing algorithm used by
    `match`, `wait_for_match`, and `press_until_match`.

    You can change the default values for these parameters by setting a key
    (with the same name as the corresponding python parameter) in the `[match]`
    section of stbt.conf. But we strongly recommend that you don't change the
    default values from what is documented here.

    You should only need to change these parameters when you're trying to match
    a template image that isn't actually a perfect match -- for example if
    there's a translucent background with live TV visible behind it; or if you
    have a template image of a button's background and you want it to match even
    if the text on the button doesn't match.

    :param str match_method:
      The method to be used by the first pass of stb-tester's image matching
      algorithm, to find the most likely location of the "template" image
      within the larger source image.

      Allowed values are "sqdiff-normed", "ccorr-normed", and "ccoeff-normed".
      For the meaning of these parameters, see OpenCV's `cvMatchTemplate
      <http://docs.opencv.org/modules/imgproc/doc/object_detection.html>`_.

      We recommend that you don't change this from its default value of
      "sqdiff-normed".

    :param float match_threshold:
      How strong a result from the first pass must be, to be considered a
      match. Valid values range from 0 (anything is considered to match)
      to 1 (the match has to be pixel perfect). This defaults to 0.8.

    :param str confirm_method:
      The method to be used by the second pass of stb-tester's image matching
      algorithm, to confirm that the region identified by the first pass is a
      good match.

      The first pass often gives false positives (it reports a "match" for an
      image that shouldn't match). The second pass is more CPU-intensive, but
      it only checks the position of the image that the first pass identified.
      The allowed values are:

      :"none":
        Do not confirm the match. Assume that the potential match found is
        correct.

      :"absdiff":
        Compare the absolute difference of each pixel from the template image
        against its counterpart from the candidate region in the source video
        frame.

      :"normed-absdiff":
        Normalise the pixel values from both the template image and the
        candidate region in the source video frame, then compare the absolute
        difference as with "absdiff".

        This gives better results with low-contrast images. We recommend setting
        this as the default `confirm_method` in stbt.conf, with a
        `confirm_threshold` of 0.30.

    :param float confirm_threshold:
      The maximum allowed difference between any given pixel from the template
      image and its counterpart from the candidate region in the source video
      frame, as a fraction of the pixel's total luminance range.

      Valid values range from 0 (more strict) to 1.0 (less strict).
      Useful values tend to be around 0.16 for the "absdiff" method, and 0.30
      for the "normed-absdiff" method.

    :param int erode_passes:
      After the "absdiff" or "normed-absdiff" absolute difference is taken,
      stb-tester runs an erosion algorithm that removes single-pixel differences
      to account for noise. Useful values are 1 (the default) and 0 (to disable
      this step).

    """

    def __init__(self, match_method=None, match_threshold=None,
                 confirm_method=None, confirm_threshold=None,
                 erode_passes=None):
        if match_method is None:
            match_method = get_config('match', 'match_method')
        if match_threshold is None:
            match_threshold = get_config(
                'match', 'match_threshold', type_=float)
        if confirm_method is None:
            confirm_method = get_config('match', 'confirm_method')
        if confirm_threshold is None:
            confirm_threshold = get_config(
                'match', 'confirm_threshold', type_=float)
        if erode_passes is None:
            erode_passes = get_config('match', 'erode_passes', type_=int)

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

    def __repr__(self):
        return (
            "MatchParameters(match_method=%r, match_threshold=%r, "
            "confirm_method=%r, confirm_threshold=%r, erode_passes=%r)"
            % (self.match_method, self.match_threshold,
               self.confirm_method, self.confirm_threshold, self.erode_passes))


class Position(namedtuple('Position', 'x y')):
    """A point within the video frame.

    `x` and `y` are integer coordinates (measured in number of pixels) from the
    top left corner of the video frame.
    """
    pass


class Region(namedtuple('Region', 'x y right bottom')):
    u"""
    ``Region(x, y, width=width, height=height)`` or
    ``Region(x, y, right=right, bottom=bottom)``

    Rectangular region within the video frame.

    For example, given the following regions a, b, and c::

        - 01234567890123
        0 ░░░░░░░░
        1 ░a░░░░░░
        2 ░░░░░░░░
        3 ░░░░░░░░
        4 ░░░░▓▓▓▓░░▓c▓
        5 ░░░░▓▓▓▓░░▓▓▓
        6 ░░░░▓▓▓▓░░░░░
        7 ░░░░▓▓▓▓░░░░░
        8     ░░░░░░b░░
        9     ░░░░░░░░░

    >>> a = Region(0, 0, width=8, height=8)
    >>> b = Region(4, 4, right=13, bottom=10)
    >>> c = Region(10, 4, width=3, height=2)
    >>> a.right
    8
    >>> b.bottom
    10
    >>> b.contains(c), a.contains(b), c.contains(b)
    (True, False, False)
    >>> b.extend(x=6, bottom=-4) == c
    True
    >>> a.extend(right=5).contains(c)
    True
    >>> a.width, a.extend(x=3).width, a.extend(right=-3).width
    (8, 5, 5)
    >>> c.replace(bottom=10)
    Region(x=10, y=4, right=13, bottom=10)
    >>> Region.intersect(a, b)
    Region(x=4, y=4, right=8, bottom=8)
    >>> Region.intersect(a, b) == Region.intersect(b, a)
    True
    >>> Region.intersect(c, b) == c
    True
    >>> print Region.intersect(a, c)
    None
    >>> print Region.intersect(None, a)
    None
    >>> quadrant = Region(x=float("-inf"), y=float("-inf"), right=0, bottom=0)
    >>> quadrant.translate(2, 2)
    Region(x=-inf, y=-inf, right=2, bottom=2)
    >>> c.translate(x=-9, y=-3)
    Region(x=1, y=1, right=4, bottom=3)
    >>> Region.intersect(Region.ALL, c) == c
    True
    >>> Region.ALL
    Region.ALL
    >>> print Region.ALL
    Region.ALL

    .. py:attribute:: x

        The x coordinate of the left edge of the region, measured in pixels
        from the left of the video frame (inclusive).

    .. py:attribute:: y

        The y coordinate of the top edge of the region, measured in pixels from
        the top of the video frame (inclusive).

    .. py:attribute:: right

        The x coordinate of the right edge of the region, measured in pixels
        from the left of the video frame (exclusive).

    .. py:attribute:: bottom

        The y coordinate of the bottom edge of the region, measured in pixels
        from the top of the video frame (exclusive).

    ``x``, ``y``, ``right``, and ``bottom`` can be infinite -- that is,
    ``float("inf")`` or ``-float("inf")``.
    """
    def __new__(cls, x, y, width=None, height=None, right=None, bottom=None):
        if (width is None) == (right is None):
            raise ValueError("You must specify either 'width' or 'right'")
        if (height is None) == (bottom is None):
            raise ValueError("You must specify either 'height' or 'bottom'")
        if right is None:
            right = x + width
        if bottom is None:
            bottom = y + height
        if right <= x:
            raise ValueError("'right' must be greater than 'x'")
        if bottom <= y:
            raise ValueError("'bottom' must be greater than 'y'")
        return super(Region, cls).__new__(cls, x, y, right, bottom)

    def __repr__(self):
        if self == Region.ALL:
            return 'Region.ALL'
        else:
            return 'Region(x=%r, y=%r, right=%r, bottom=%r)' \
                % (self.x, self.y, self.right, self.bottom)

    @property
    def width(self):
        """The width of the region, measured in pixels."""
        return self.right - self.x

    @property
    def height(self):
        """The height of the region, measured in pixels."""
        return self.bottom - self.y

    @staticmethod
    def from_extents(x, y, right, bottom):
        """Create a Region using right and bottom extents rather than width and
        height.

        Deprecated since we added ``right`` and ``bottom`` to Region
        constructor.

        >>> Region.from_extents(4, 4, 13, 10)
        Region(x=4, y=4, right=13, bottom=10)
        """
        return Region(x, y, right=right, bottom=bottom)

    @staticmethod
    def intersect(a, b):
        """
        :returns: The intersection of regions ``a`` and ``b``, or ``None`` if
            the regions don't intersect.

        Either ``a`` or ``b`` can be ``None`` so intersect is commutative and
        associative.
        """
        if a is None or b is None:
            return None
        else:
            extents = (max(a.x, b.x), max(a.y, b.y),
                       min(a.right, b.right), min(a.bottom, b.bottom))
            if extents[0] < extents[2] and extents[1] < extents[3]:
                return Region.from_extents(*extents)
            else:
                return None

    def contains(self, other):
        """:returns: True if ``other`` is entirely contained within self."""
        return (other and self.x <= other.x and self.y <= other.y and
                self.right >= other.right and self.bottom >= other.bottom)

    def extend(self, x=0, y=0, right=0, bottom=0):
        """
        :returns: A new region with the edges of the region adjusted by the
            given amounts.
        """
        return Region.from_extents(
            self.x + x, self.y + y, self.right + right, self.bottom + bottom)

    def replace(self, x=None, y=None, width=None, height=None, right=None,
                bottom=None):
        """
        :returns: A new region with the edges of the region set to the given
            coordinates.

        This is similar to `extend`, but it takes absolute coordinates within
        the image instead of adjusting by a relative number of pixels.

        ``Region.replace`` was added in stb-tester v24.
        """
        def norm_coords(name_x, name_width, name_right,
                        x, width, right,  # or y, height, bottom
                        default_x, _default_width, default_right):
            if all(z is not None for z in (x, width, right)):
                raise ValueError(
                    "Region.replace: Argument conflict: you may only specify "
                    "two of %s, %s and %s.  You specified %s=%s, %s=%s and "
                    "%s=%s" % (name_x, name_width, name_right,
                               name_x, x, name_width, width, name_right, right))
            if x is None:
                if width is not None and right is not None:
                    x = right - width
                else:
                    x = default_x
            if right is None:
                right = x + width if width is not None else default_right
            return x, right

        x, right = norm_coords('x', 'width', 'right', x, width, right,
                               self.x, self.width, self.right)
        y, bottom = norm_coords('y', 'height', 'bottom', y, height, bottom,
                                self.y, self.height, self.bottom)

        return Region(x=x, y=y, right=right, bottom=bottom)

    def translate(self, x=0, y=0):
        """
        :returns: A new region with the position of the region adjusted by the
            given amounts.
        """
        return Region.from_extents(self.x + x, self.y + y,
                                   self.right + x, self.bottom + y)

Region.ALL = Region(x=float("-inf"), y=float("-inf"),
                    right=float("inf"), bottom=float("inf"))


def _bounding_box(a, b):
    """Find the bounding box of two regions.  Returns the smallest region which
    contains both regions a and b.

    >>> print _bounding_box(Region(50, 20, 10, 20), Region(20, 30, 10, 20))
    Region(x=20, y=20, right=60, bottom=50)
    >>> print _bounding_box(Region(20, 30, 10, 20), Region(20, 30, 10, 20))
    Region(x=20, y=30, right=30, bottom=50)
    >>> print _bounding_box(None, Region(20, 30, 10, 20))
    Region(x=20, y=30, right=30, bottom=50)
    >>> print _bounding_box(Region(20, 30, 10, 20), None)
    Region(x=20, y=30, right=30, bottom=50)
    >>> print _bounding_box(Region(20, 30, 10, 20), Region.ALL)
    Region.ALL
    >>> print _bounding_box(None, None)
    None
    """
    if a is None:
        return b
    if b is None:
        return a
    return Region.from_extents(min(a.x, b.x), min(a.y, b.y),
                               max(a.right, b.right), max(a.bottom, b.bottom))


class MatchResult(object):
    """The result from `match`.

    * ``timestamp``: Video stream timestamp.
    * ``match``: Boolean result, the same as evaluating `MatchResult` as a bool.
      That is, ``if match_result:`` will behave the same as
      ``if match_result.match:``.
    * ``region``: The `Region` in the video frame where the image was found.
    * ``first_pass_result``: Value between 0 (poor) and 1.0 (excellent match)
      from the first pass of stb-tester's two-pass image matching algorithm
      (see `MatchParameters` for details).
    * ``frame``: The video frame that was searched, in OpenCV format.
    * ``image``: The template image that was searched for, as given to `match`.
    """
    # pylint: disable=W0621
    def __init__(
            self, timestamp, match, region, first_pass_result, frame=None,
            image=None, _first_pass_matched=None):
        self.timestamp = timestamp
        self.match = match
        self.region = region
        self.first_pass_result = first_pass_result
        if frame is None:
            warnings.warn(
                "Creating a 'MatchResult' without specifying 'frame' is "
                "deprecated. In a future release of stb-tester the 'frame' "
                "parameter will be mandatory.",
                DeprecationWarning, stacklevel=2)
        self.frame = frame
        if image is None:
            warnings.warn(
                "Creating a 'MatchResult' without specifying 'image' is "
                "deprecated. In a future release of stb-tester the 'image' "
                "parameter will be mandatory.",
                DeprecationWarning, stacklevel=2)
            image = ""
        self.image = image
        self._first_pass_matched = _first_pass_matched

    def __repr__(self):
        return (
            "MatchResult(timestamp=%r, match=%r, region=%r, "
            "first_pass_result=%r, frame=<%s>, image=%s)" % (
                self.timestamp,
                self.match,
                self.region,
                self.first_pass_result,
                "None" if self.frame is None else "%dx%dx%d" % (
                    self.frame.shape[1], self.frame.shape[0],
                    self.frame.shape[2]),
                "<Custom Image>" if isinstance(self.image, numpy.ndarray)
                else repr(self.image)))

    @property
    def position(self):
        return Position(self.region.x, self.region.y)

    def __nonzero__(self):
        return self.match


class _AnnotatedTemplate(namedtuple('_AnnotatedTemplate',
                                    'image name filename')):
    @property
    def friendly_name(self):
        return self.filename or '<Custom Image>'


def _load_template(template):
    if isinstance(template, _AnnotatedTemplate):
        return template
    if isinstance(template, numpy.ndarray):
        return _AnnotatedTemplate(template, None, None)
    else:
        template_name = _find_path(template)
        if not template_name or not os.path.isfile(template_name):
            raise UITestError("No such template file: %s" % template)
        image = cv2.imread(template_name, cv2.CV_LOAD_IMAGE_COLOR)
        if image is None:
            raise UITestError("Failed to load template file: %s" %
                              template_name)
        return _AnnotatedTemplate(image, template, template_name)


def _crop(frame, region):
    if not _image_region(frame).contains(region):
        raise ValueError("'frame' doesn't contain 'region'")
    return frame[region.y:region.bottom, region.x:region.right]


def _image_region(image):
    s = sample_shape(image)
    return Region(0, 0, s[1], s[0])


class MotionResult(object):
    """The result from `detect_motion`.

    * `timestamp`: Video stream timestamp.
    * ``motion``: Boolean result, the same as evaluating `MotionResult` as a
      bool. That is, ``if result:`` will behave the same as
      ``if result.motion:``.
    * ``region``: The region of the video frame that contained the motion.
      `None` if no motion detected.
    """
    def __init__(self, timestamp, motion, region=None):
        self.timestamp = timestamp
        self.motion = motion
        self.region = region

    def __nonzero__(self):
        return self.motion

    def __repr__(self):
        return "MotionResult(timestamp=%r, motion=%r, region=%r)" % (
            self.timestamp, self.motion, self.region)


class OcrMode(IntEnum):
    """Options to control layout analysis and assume a certain form of image.

    For a (brief) description of each option, see the `tesseract(1)
    <http://tesseract-ocr.googlecode.com/svn/trunk/doc/tesseract.1.html#_options>`_
    man page.
    """
    ORIENTATION_AND_SCRIPT_DETECTION_ONLY = 0
    PAGE_SEGMENTATION_WITH_OSD = 1
    PAGE_SEGMENTATION_WITHOUT_OSD_OR_OCR = 2
    PAGE_SEGMENTATION_WITHOUT_OSD = 3
    SINGLE_COLUMN_OF_TEXT_OF_VARIABLE_SIZES = 4
    SINGLE_UNIFORM_BLOCK_OF_VERTICALLY_ALIGNED_TEXT = 5
    SINGLE_UNIFORM_BLOCK_OF_TEXT = 6
    SINGLE_LINE = 7
    SINGLE_WORD = 8
    SINGLE_WORD_IN_A_CIRCLE = 9
    SINGLE_CHARACTER = 10

    # For nicer formatting of `ocr` signature in generated API documentation:
    def __repr__(self):
        return str(self)


class TextMatchResult(object):
    """The result from `match_text`.

    * ``timestamp``: Video stream timestamp.
    * ``match``: Boolean result, the same as evaluating `TextMatchResult` as a
      bool. That is, ``if result:`` will behave the same as
      ``if result.match:``.
    * ``region``: The `Region` (bounding box) of the text found, or ``None`` if
      no text was found.
    * ``frame``: The video frame that was searched, in OpenCV format.
    * ``text``: The text (unicode string) that was searched for, as given to
      `match_text`.
    """
    def __init__(self, timestamp, match, region, frame, text):
        self.timestamp = timestamp
        self.match = match
        self.region = region
        self.frame = frame
        self.text = text

    # pylint: disable=E1101
    def __nonzero__(self):
        return self.match

    def __repr__(self):
        return (
            "TextMatchResult(timestamp=%r, match=%r, region=%r, frame=<%s>, "
            "text=%r)" % (
                self.timestamp,
                self.match,
                self.region,
                "%dx%dx%d" % (self.frame.shape[1], self.frame.shape[0],
                              self.frame.shape[2]),
                self.text))


def new_device_under_test_from_config(
        gst_source_pipeline=None, gst_sink_pipeline=None, control_uri=None,
        save_video=False, restart_source=None, transformation_pipeline=None):
    from _stbt.control import uri_to_remote

    if gst_source_pipeline is None:
        gst_source_pipeline = get_config('global', 'source_pipeline')
    if gst_sink_pipeline is None:
        gst_sink_pipeline = get_config('global', 'sink_pipeline')
    if control_uri is None:
        control_uri = get_config('global', 'control')
    if restart_source is None:
        restart_source = get_config('global', 'restart_source')
    if transformation_pipeline is None:
        gst_sink_pipeline = get_config('global', 'transformation_pipeline')

    display = Display(
        gst_source_pipeline, gst_sink_pipeline, _mainloop(), save_video,
        restart_source, transformation_pipeline)
    return DeviceUnderTest(
        display=display, control=uri_to_remote(control_uri, display))


def _pixel_bounding_box(img):
    """
    Find the smallest region that contains all the non-zero pixels in an image.

    >>> _pixel_bounding_box(numpy.array([[0]], dtype=numpy.uint8))
    >>> _pixel_bounding_box(numpy.array([[1]], dtype=numpy.uint8))
    Region(x=0, y=0, right=1, bottom=1)
    >>> _pixel_bounding_box(numpy.array([
    ...     [0, 0, 0, 0],
    ...     [0, 1, 1, 1],
    ...     [0, 1, 1, 1],
    ...     [0, 0, 0, 0],
    ... ], dtype=numpy.uint8))
    Region(x=1, y=1, right=4, bottom=3)
    >>> _pixel_bounding_box(numpy.array([
    ...     [0, 0, 0, 0, 0, 0],
    ...     [0, 0, 0, 1, 0, 0],
    ...     [0, 1, 0, 0, 0, 0],
    ...     [0, 0, 0, 0, 1, 0],
    ...     [0, 0, 1, 0, 0, 0],
    ...     [0, 0, 0, 0, 0, 0]
    ... ], dtype=numpy.uint8))
    Region(x=1, y=1, right=5, bottom=5)
    """
    if len(img.shape) != 2:
        raise ValueError("Single-channel image required.  Provided image has "
                         "shape %r" % (img.shape,))

    out = [None, None, None, None]

    for axis in (0, 1):
        flat = numpy.any(img, axis=axis)
        indices = numpy.where(flat)[0]
        if len(indices) == 0:
            return None
        out[axis] = indices[0]
        out[axis + 2] = indices[-1] + 1

    return Region.from_extents(*out)


class DeviceUnderTest(object):
    def __init__(self, display=None, control=None):
        self._time_of_last_press = None
        self._display = display
        self._control = control

    def __enter__(self):
        if self._display:
            self._display.startup()
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        if self._display:
            self._display.teardown()
            self._display = None
        self._control = None

    def press(self, key, interpress_delay_secs=None):
        if interpress_delay_secs is None:
            interpress_delay_secs = get_config(
                "press", "interpress_delay_secs", type_=float)
        if self._time_of_last_press is not None:
            # `sleep` is inside a `while` loop because the actual suspension
            # time of `sleep` may be less than that requested.
            while True:
                seconds_to_wait = (
                    self._time_of_last_press - datetime.datetime.now() +
                    datetime.timedelta(seconds=interpress_delay_secs)
                ).total_seconds()
                if seconds_to_wait > 0:
                    time.sleep(seconds_to_wait)
                else:
                    break

        self._control.press(key)
        self._time_of_last_press = datetime.datetime.now()
        self.draw_text(key, duration_secs=3)

    def draw_text(self, text, duration_secs=3):
        self._display.draw(text, duration_secs)

    def match(self, image, frame=None, match_parameters=None,
              region=Region.ALL):
        result = next(self._match_all(image, frame, match_parameters, region))
        if result.match:
            debug("Match found: %s" % str(result))
        else:
            debug("No match found. Closest match: %s" % str(result))
        return result

    def match_all(self, image, frame=None, match_parameters=None,
                  region=Region.ALL):
        any_matches = False
        for result in self._match_all(image, frame, match_parameters, region):
            if result.match:
                debug("Match found: %s" % str(result))
                any_matches = True
                yield result
            else:
                if not any_matches:
                    debug("No match found. Closest match: %s" % str(result))
                break

    def _match_all(self, image, frame, match_parameters, region):
        """
        Generator that yields a sequence of zero or more truthy MatchResults,
        followed by a falsey MatchResult.
        """
        if match_parameters is None:
            match_parameters = MatchParameters()

        template = _load_template(image)

        grabbed_from_live = (frame is None)
        if grabbed_from_live:
            frame = self._display.pull_frame()

        imglog = logging.ImageLogger(
            "match", match_parameters=match_parameters,
            template_name=template.friendly_name)

        region = Region.intersect(_image_region(frame), region)

        # Remove this copy once we've confirmed that doing so won't cause
        # push_sample to doodle on the frame later.
        frame = frame.copy()
        frame.flags.writeable = False

        # pylint:disable=undefined-loop-variable
        try:
            for (matched, match_region, first_pass_matched,
                 first_pass_certainty) in _find_matches(
                    _crop(frame, region), template.image,
                    match_parameters, imglog):

                match_region = Region.from_extents(*match_region) \
                                     .translate(region.x, region.y)
                result = MatchResult(
                    get_frame_timestamp(frame), matched, match_region,
                    first_pass_certainty, frame,
                    (template.name or template.image), first_pass_matched)
                imglog.append(matches=result)
                if grabbed_from_live:
                    self._display.draw(
                        result, label="match(%r)" %
                        os.path.basename(template.friendly_name))
                yield result

        finally:
            try:
                _log_match_image_debug(imglog)
            except Exception:  # pylint:disable=broad-except
                pass

    def detect_match(self, image, timeout_secs=10, match_parameters=None,
                     region=Region.ALL):
        template = _load_template(image)

        debug("Searching for " + template.friendly_name)

        for sample in self._display.frames(timeout_secs):
            result = self.match(
                template, frame=sample, match_parameters=match_parameters,
                region=region)
            self._display.draw(result, label="match(%r)" %
                               os.path.basename(template.friendly_name))
            yield result

    def detect_motion(self, timeout_secs=10, noise_threshold=None, mask=None):
        if noise_threshold is None:
            noise_threshold = get_config(
                'motion', 'noise_threshold', type_=float)

        debug("Searching for motion")

        mask_image = None
        if mask:
            mask_image = _load_mask(mask)

        previous_frame_gray = None

        for frame in self._display.frames(timeout_secs):
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if previous_frame_gray is None:
                if (mask_image is not None and
                        mask_image.shape[:2] != frame_gray.shape[:2]):
                    raise UITestError(
                        "The dimensions of the mask '%s' %s don't match the "
                        "video frame %s" % (
                            mask, mask_image.shape, frame_gray.shape))
                previous_frame_gray = frame_gray
                continue

            imglog = logging.ImageLogger("detect_motion")
            imglog.imwrite("source", frame_gray)

            absdiff = cv2.absdiff(frame_gray, previous_frame_gray)
            previous_frame_gray = frame_gray
            imglog.imwrite("absdiff", absdiff)

            if mask_image is not None:
                absdiff = cv2.bitwise_and(absdiff, mask_image)
                imglog.imwrite("mask", mask_image)
                imglog.imwrite("absdiff_masked", absdiff)

            _, thresholded = cv2.threshold(
                absdiff, int((1 - noise_threshold) * 255), 255,
                cv2.THRESH_BINARY)
            eroded = cv2.erode(
                thresholded,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
            imglog.imwrite("absdiff_threshold", thresholded)
            imglog.imwrite("absdiff_threshold_erode", eroded)

            out_region = _pixel_bounding_box(eroded)
            if out_region:
                # Undo cv2.erode above:
                out_region = out_region.extend(x=-1, y=-1)

            motion = bool(out_region)

            result = MotionResult(
                get_frame_timestamp(frame), motion, out_region)
            self._display.draw(result, label="detect_motion()")
            debug("%s found: %s" % (
                "Motion" if motion else "No motion", str(result)))
            yield result

    def wait_for_match(self, image, timeout_secs=10, consecutive_matches=1,
                       match_parameters=None, region=Region.ALL):

        if match_parameters is None:
            match_parameters = MatchParameters()

        match_count = 0
        last_pos = Position(0, 0)
        image = _load_template(image)
        for res in self.detect_match(
                image, timeout_secs, match_parameters=match_parameters,
                region=region):
            if res.match and (match_count == 0 or res.position == last_pos):
                match_count += 1
            else:
                match_count = 0
            last_pos = res.position
            if match_count == consecutive_matches:
                debug("Matched " + image.friendly_name)
                return res

        raise MatchTimeout(res.frame, image.friendly_name, timeout_secs)  # pylint: disable=W0631,C0301

    def press_until_match(
            self,
            key,
            image,
            interval_secs=None,
            max_presses=None,
            match_parameters=None):

        if interval_secs is None:
            # Should this be float?
            interval_secs = get_config(
                "press_until_match", "interval_secs", type_=int)
        if max_presses is None:
            max_presses = get_config(
                "press_until_match", "max_presses", type_=int)

        if match_parameters is None:
            match_parameters = MatchParameters()

        i = 0

        while True:
            try:
                return self.wait_for_match(image, timeout_secs=interval_secs,
                                           match_parameters=match_parameters)
            except MatchTimeout:
                if i < max_presses:
                    self.press(key)
                    i += 1
                else:
                    raise

    def wait_for_motion(
            self, timeout_secs=10, consecutive_frames=None,
            noise_threshold=None, mask=None):

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
        for res in self.detect_motion(timeout_secs, noise_threshold, mask):
            matches.append(res.motion)
            if matches.count(True) >= motion_frames:
                debug("Motion detected.")
                return res

        screenshot = self.get_frame()
        raise MotionTimeout(screenshot, mask, timeout_secs)

    def ocr(self, frame=None, region=Region.ALL,
            mode=OcrMode.PAGE_SEGMENTATION_WITHOUT_OSD,
            lang="eng", tesseract_config=None, tesseract_user_words=None,
            tesseract_user_patterns=None):

        if frame is None:
            frame = self._display.pull_frame()

        if region is None:
            warnings.warn(
                "Passing region=None to ocr is deprecated since 0.21 and the "
                "meaning will change in a future version.  To OCR an entire "
                "video frame pass region=Region.ALL instead",
                DeprecationWarning, stacklevel=2)
            region = Region.ALL

        text, region = _tesseract(
            frame, region, mode, lang, tesseract_config,
            user_patterns=tesseract_user_patterns,
            user_words=tesseract_user_words)
        text = text.strip().translate(_ocr_transtab)
        debug(u"OCR in region %s read '%s'." % (region, text))
        return text

    def match_text(self, text, frame=None, region=Region.ALL,
                   mode=OcrMode.PAGE_SEGMENTATION_WITHOUT_OSD, lang="eng",
                   tesseract_config=None):

        import lxml.etree
        if frame is None:
            frame = self.get_frame()

        _config = dict(tesseract_config or {})
        _config['tessedit_create_hocr'] = 1
        if _tesseract_version() >= LooseVersion('3.04'):
            _config['tessedit_create_txt'] = 0

        ts = get_frame_timestamp(frame)

        xml, region = _tesseract(frame, region, mode, lang, _config,
                                 user_words=text.split())
        if xml == '':
            result = TextMatchResult(ts, False, None, frame, text)
        else:
            hocr = lxml.etree.fromstring(xml.encode('utf-8'))
            p = _hocr_find_phrase(hocr, text.split())
            if p:
                # Find bounding box
                box = None
                for _, elem in p:
                    box = _bounding_box(box, _hocr_elem_region(elem))
                # _tesseract crops to region and scales up by a factor of 3 so
                # we must undo this transformation here.
                box = Region.from_extents(
                    region.x + box.x // 3, region.y + box.y // 3,
                    region.x + box.right // 3, region.y + box.bottom // 3)
                result = TextMatchResult(ts, True, box, frame, text)
            else:
                result = TextMatchResult(ts, False, None, frame, text)

        if result.match:
            debug("match_text: Match found: %s" % str(result))
        else:
            debug("match_text: No match found: %s" % str(result))

        return result

    def frames(self, timeout_secs=None):
        for f in self._display.frames(timeout_secs):
            yield f.copy(), get_frame_timestamp(f)

    def get_frame(self):
        return self._display.pull_frame().copy()

    def is_screen_black(self, frame=None, mask=None, threshold=None):
        if threshold is None:
            threshold = get_config('is_screen_black', 'threshold', type_=int)
        if mask:
            mask = _load_mask(mask)
        if frame is None:
            frame = self._display.pull_frame()
        greyframe = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, greyframe = cv2.threshold(
            greyframe, threshold, 255, cv2.THRESH_BINARY)
        _, maxVal, _, _ = cv2.minMaxLoc(greyframe, mask)

        if logging.get_debug_level() > 1:
            imglog = logging.ImageLogger("is_screen_black")
            imglog.imwrite("source", frame)
            if mask is not None:
                imglog.imwrite('mask', mask)
                imglog.imwrite('non-black-regions-after-masking',
                               numpy.bitwise_and(greyframe, mask))
            else:
                imglog.imwrite('non-black-regions-after-masking', greyframe)

        return maxVal == 0

# Utility functions
# ===========================================================================


def save_frame(image, filename):
    """Saves an OpenCV image to the specified file.

    Takes an image obtained from `get_frame` or from the `screenshot`
    property of `MatchTimeout` or `MotionTimeout`.
    """
    cv2.imwrite(filename, image)


def wait_until(callable_, timeout_secs=10, interval_secs=0):
    """Wait until a condition becomes true, or until a timeout.

    ``callable_`` is any python callable, such as a function or a lambda
    expression. It will be called repeatedly (with a delay of ``interval_secs``
    seconds between successive calls) until it succeeds (that is, it returns a
    truthy value) or until ``timeout_secs`` seconds have passed. In both cases,
    ``wait_until`` returns the value that ``callable_`` returns.

    After you send a remote-control signal to the system-under-test it usually
    takes a few frames to react, so a test script like this would probably
    fail::

        press("KEY_EPG")
        assert match("guide.png")

    Instead, use this::

        press("KEY_EPG")
        assert wait_until(lambda: match("guide.png"))

    Note that instead of the above `assert wait_until(...)` you could use
    `wait_for_match("guide.png")`. `wait_until` is a generic solution that
    also works with stbt's other functions, like `match_text` and
    `is_screen_black`.

    `wait_until` allows composing more complex conditions, such as::

        # Wait until something disappears:
        assert wait_until(lambda: not match("xyz.png"))

        # Assert that something doesn't appear within 10 seconds:
        assert not wait_until(lambda: match("xyz.png"))

        # Assert that two images are present at the same time:
        assert wait_until(lambda: match("a.png") and match("b.png"))

        # Wait but don't raise an exception:
        if not wait_until(lambda: match("xyz.png")):
            do_something_else()

    There are some drawbacks to using `assert` instead of `wait_for_match`:

    * The exception message won't contain the reason why the match failed
      (unless you specify it as a second parameter to `assert`, which is
      tedious and we don't expect you to do it), and
    * The exception won't have the offending video-frame attached (so the
      screenshot in the test-run artifacts will be a few frames later than the
      frame that actually caused the test to fail).

    We hope to solve both of the above drawbacks at some point in the future.

    ``wait_until`` was added in stb-tester v22.
    """
    expiry_time = time.time() + timeout_secs
    while True:
        e = callable_()
        if e:
            return e
        if time.time() > expiry_time:
            debug("wait_until timed out: %s" % _callable_description(callable_))
            return e
        time.sleep(interval_secs)


def _callable_description(callable_):
    """Helper to provide nicer debug output when `wait_until` fails.

    >>> _callable_description(wait_until)
    'wait_until'
    >>> _callable_description(
    ...     lambda: stbt.press("OK"))
    '    lambda: stbt.press("OK"))\\n'
    >>> _callable_description(functools.partial(int, base=2))
    'int'
    >>> _callable_description(functools.partial(functools.partial(int, base=2),
    ...                                         x='10'))
    'int'
    >>> class T(object):
    ...     def __call__(self): return True;
    >>> _callable_description(T())
    '<_stbt.core.T object at 0x...>'
    """
    if hasattr(callable_, "__name__"):
        name = callable_.__name__
        if name == "<lambda>":
            try:
                name = inspect.getsource(callable_)
            except IOError:
                pass
        return name
    elif isinstance(callable_, functools.partial):
        return _callable_description(callable_.func)
    else:
        return repr(callable_)


@contextmanager
def as_precondition(message):
    """Context manager that replaces test failures with test errors.

    Stb-tester's reports show test failures (that is, `UITestFailure` or
    `AssertionError` exceptions) as red results, and test errors (that is,
    unhandled exceptions of any other type) as yellow results. Note that
    `wait_for_match`, `wait_for_motion`, and similar functions raise a
    `UITestFailure` when they detect a failure. By running such functions
    inside an `as_precondition` context, any `UITestFailure` or
    `AssertionError` exceptions they raise will be caught, and a
    `PreconditionError` will be raised instead.

    When running a single testcase hundreds or thousands of times to reproduce
    an intermittent defect, it is helpful to mark unrelated failures as test
    errors (yellow) rather than test failures (red), so that you can focus on
    diagnosing the failures that are most likely to be the particular defect
    you are looking for. For more details see `Test failures vs. errors
    <http://stb-tester.com/preconditions>`_.

    :param str message:
        A description of the precondition. Word this positively: "Channels
        tuned", not "Failed to tune channels".

    :raises:
        `PreconditionError` if the wrapped code block raises a `UITestFailure`
        or `AssertionError`.

    Example::

        def test_that_the_on_screen_id_is_shown_after_booting():
            channel = 100

            with stbt.as_precondition("Tuned to channel %s" % channel):
                mainmenu.close_any_open_menu()
                channels.goto_channel(channel)
                power.cold_reboot()
                assert channels.is_on_channel(channel)

            stbt.wait_for_match("on-screen-id.png")

    """
    try:
        yield
    except (UITestFailure, AssertionError) as e:
        debug("stbt.as_precondition caught a %s exception and will "
              "re-raise it as PreconditionError.\nOriginal exception was:\n%s"
              % (type(e).__name__, traceback.format_exc(e)))
        exc = PreconditionError(message, e)
        if hasattr(e, 'screenshot'):
            exc.screenshot = e.screenshot  # pylint: disable=W0201
        raise exc


class UITestError(Exception):
    """The test script had an unrecoverable error."""
    pass


class UITestFailure(Exception):
    """The test failed because the system under test didn't behave as expected.

    Inherit from this if you need to define your own test-failure exceptions.
    """
    pass


class NoVideo(UITestFailure):
    """No video available from the source pipeline."""
    pass


class MatchTimeout(UITestFailure):
    """Exception raised by `wait_for_match`.

    * ``screenshot``: The last video frame that `wait_for_match` checked before
      timing out.
    * ``expected``: Filename of the image that was being searched for.
    * ``timeout_secs``: Number of seconds that the image was searched for.
    """
    def __init__(self, screenshot, expected, timeout_secs):
        super(MatchTimeout, self).__init__()
        self.screenshot = screenshot
        self.expected = expected
        self.timeout_secs = timeout_secs

    def __str__(self):
        return "Didn't find match for '%s' within %g seconds." % (
            self.expected, self.timeout_secs)


class MotionTimeout(UITestFailure):
    """Exception raised by `wait_for_motion`.

    * ``screenshot``: The last video frame that `wait_for_motion` checked before
      timing out.
    * ``mask``: Filename of the mask that was used, if any.
    * ``timeout_secs``: Number of seconds that motion was searched for.
    """
    def __init__(self, screenshot, mask, timeout_secs):
        super(MotionTimeout, self).__init__()
        self.screenshot = screenshot
        self.mask = mask
        self.timeout_secs = timeout_secs

    def __str__(self):
        return "Didn't find motion%s within %g seconds." % (
            " (with mask '%s')" % self.mask if self.mask else "",
            self.timeout_secs)


class PreconditionError(UITestError):
    """Exception raised by `as_precondition`."""
    def __init__(self, message, original_exception):
        super(PreconditionError, self).__init__()
        self.message = message
        self.original_exception = original_exception

    def __str__(self):
        return (
            "Didn't meet precondition '%s' (original exception was: %s)"
            % (self.message, self.original_exception))


# stbt-run initialisation and convenience functions
# (you will need these if writing your own version of stbt-run)
# ===========================================================================

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

    logging.argparser_add_verbose_argument(parser)

    return parser


def _memoize_property_fn(fn):
    @functools.wraps(fn)
    def inner(self):
        # pylint: disable=protected-access
        if fn not in self._FrameObject__frame_object_cache:
            self._FrameObject__frame_object_cache[fn] = fn(self)
        return self._FrameObject__frame_object_cache[fn]
    return inner


def _noneify_property_fn(fn):
    @functools.wraps(fn)
    def inner(self):
        if self:
            return fn(self)
        else:
            return None
    return inner


class _FrameObjectMeta(type):
    def __new__(mcs, name, parents, dct):
        for k, v in dct.iteritems():
            if isinstance(v, property):
                if v.fset is not None:
                    raise Exception(
                        "FrameObjects must be immutable but this property has "
                        "a setter")
                f = v.fget
                f = _memoize_property_fn(f)
                if k != 'is_visible' and not k.startswith('_'):
                    f = _noneify_property_fn(f)
                dct[k] = property(f)

        if 'AUTO_SELFTEST_EXPRESSIONS' not in dct:
            dct['AUTO_SELFTEST_EXPRESSIONS'] = ['%s(frame={frame})' % name]

        return super(_FrameObjectMeta, mcs).__new__(mcs, name, parents, dct)

    def __init__(cls, name, parents, dct):
        property_names = sorted([
            p for p in dir(cls)
            if isinstance(getattr(cls, p), property)])
        assert 'is_visible' in property_names
        cls._FrameObject__attrs = ["is_visible"] + sorted(
            x for x in property_names
            if x != "is_visible" and not x.startswith('_'))
        super(_FrameObjectMeta, cls).__init__(name, parents, dct)


class FrameObject(object):
    __metaclass__ = _FrameObjectMeta

    def __init__(self, frame):
        if frame is None:
            raise ValueError("FrameObject: frame must not be None")
        self.__frame_object_cache = {}
        self._frame = frame

    def __repr__(self):
        args = ", ".join(("%s=%r" % x) for x in self._iter_attrs())
        return "%s(%s)" % (self.__class__.__name__, args)

    def _iter_attrs(self):
        if self:
            # pylint: disable=protected-access,no-member
            for x in self.__class__.__attrs:
                yield x, getattr(self, x)
        else:
            yield "is_visible", False

    def __nonzero__(self):
        return bool(self.is_visible)

    def __cmp__(self, other):
        # pylint: disable=protected-access
        from itertools import izip_longest
        if isinstance(other, self.__class__):
            for s, o in izip_longest(self._iter_attrs(), other._iter_attrs()):
                v = cmp(s[1], o[1])
                if v != 0:
                    return v
            return 0
        else:
            return NotImplemented

    def __hash__(self):
        return hash(tuple(v for _, v in self._iter_attrs()))

    @property
    def is_visible(self):
        raise NotImplementedError(
            "Objects deriving from FrameObject must define an is_visible "
            "property")


# Internal
# ===========================================================================


@contextmanager
def _mainloop():
    mainloop = GLib.MainLoop.new(context=None, is_running=False)

    thread = threading.Thread(target=mainloop.run)
    thread.daemon = True
    thread.start()

    try:
        yield
    finally:
        mainloop.quit()
        thread.join(10)
        debug("teardown: Exiting (GLib mainloop %s)" % (
              "is still alive!" if thread.isAlive() else "ok"))


class _Annotation(namedtuple("_Annotation", "pts region label colour")):
    MATCHED = (32, 0, 255)  # Red
    NO_MATCH = (32, 255, 255)  # Yellow

    @staticmethod
    def from_result(result, label=""):
        colour = _Annotation.MATCHED if result else _Annotation.NO_MATCH
        return _Annotation(result.timestamp, result.region, label, colour)

    def draw(self, img):
        if not self.region:
            return
        cv2.rectangle(
            img, (self.region.x, self.region.y),
            (self.region.right, self.region.bottom), self.colour,
            thickness=3)

        # Slightly above the match annotation
        label_loc = (self.region.x, self.region.y - 10)
        _draw_text(img, self.label, label_loc, (255, 255, 255), font_scale=0.5)


class Display(object):
    def __init__(self, user_source_pipeline, user_sink_pipeline,
                 mainloop, save_video="",
                 restart_source=False,
                 transformation_pipeline='identity'):
        self.novideo = False
        self.lock = threading.RLock()  # Held by whoever is consuming frames
        self.last_sample = Queue.Queue(maxsize=1)
        self.last_used_sample = None
        self.source_pipeline = None
        self.start_timestamp = None
        self.underrun_timeout = None
        self.tearing_down = False
        self.received_eos = threading.Event()

        self.annotations_lock = threading.Lock()
        self.text_annotations = []
        self.annotations = []

        self.restart_source_enabled = restart_source

        appsink = (
            "appsink name=appsink max-buffers=1 drop=false sync=true "
            "emit-signals=true "
            "caps=video/x-raw,format=BGR")
        # Notes on the source pipeline:
        # * _stbt_raw_frames_queue is kept small to reduce the amount of slack
        #   (and thus the latency) of the pipeline.
        # * _stbt_user_data_queue before the decodebin is large.  We don't want
        #   to drop encoded packets as this will cause significant image
        #   artifacts in the decoded buffers.  We make the assumption that we
        #   have enough horse-power to decode the incoming stream and any delays
        #   will be transient otherwise it could start filling up causing
        #   increased latency.
        self.source_pipeline_description = " ! ".join([
            user_source_pipeline,
            'queue name=_stbt_user_data_queue max-size-buffers=0 '
            '    max-size-bytes=0 max-size-time=10000000000',
            "decodebin",
            'queue name=_stbt_raw_frames_queue max-size-buffers=2',
            'videoconvert',
            'video/x-raw,format=BGR',
            transformation_pipeline,
            appsink])
        self.create_source_pipeline()

        if save_video:
            if not save_video.endswith(".webm"):
                save_video += ".webm"
            debug("Saving video to '%s'" % save_video)
            video_pipeline = (
                "t. ! queue leaky=downstream ! videoconvert ! "
                "vp8enc cpu-used=6 min_quantizer=32 max_quantizer=32 ! "
                "webmmux ! filesink location=%s" % save_video)
        else:
            video_pipeline = ""

        sink_pipeline_description = " ".join([
            "appsrc name=appsrc format=time " +
            "caps=video/x-raw,format=(string)BGR !",
            "tee name=t",
            video_pipeline,
            "t. ! queue leaky=downstream ! videoconvert !",
            user_sink_pipeline
        ])

        self.sink_pipeline = Gst.parse_launch(sink_pipeline_description)
        sink_bus = self.sink_pipeline.get_bus()
        sink_bus.connect(
            "message::error",
            lambda bus, msg: self.on_error(self.sink_pipeline, bus, msg))
        sink_bus.connect("message::warning", self.on_warning)
        sink_bus.connect("message::eos", self.on_eos_from_sink_pipeline)
        sink_bus.add_signal_watch()
        self.appsrc = self.sink_pipeline.get_by_name("appsrc")

        debug("source pipeline: %s" % self.source_pipeline_description)
        debug("sink pipeline: %s" % sink_pipeline_description)
        self.mainloop = mainloop

    def create_source_pipeline(self):
        self.source_pipeline = Gst.parse_launch(
            self.source_pipeline_description)
        source_bus = self.source_pipeline.get_bus()
        source_bus.connect(
            "message::error",
            lambda bus, msg: self.on_error(self.source_pipeline, bus, msg))
        source_bus.connect("message::warning", self.on_warning)
        source_bus.connect("message::eos", self.on_eos_from_source_pipeline)
        source_bus.add_signal_watch()
        appsink = self.source_pipeline.get_by_name("appsink")
        appsink.connect("new-sample", self.on_new_sample)

        if self.restart_source_enabled:
            # Handle loss of video (but without end-of-stream event) from the
            # Hauppauge HDPVR capture device.
            source_queue = self.source_pipeline.get_by_name(
                "_stbt_user_data_queue")
            self.start_timestamp = None
            source_queue.connect("underrun", self.on_underrun)
            source_queue.connect("running", self.on_running)

    def set_source_pipeline_playing(self):
        if (self.source_pipeline.set_state(Gst.State.PAUSED) ==
                Gst.StateChangeReturn.NO_PREROLL):
            # This is a live source, drop frames if we get behind
            self.source_pipeline.get_by_name('_stbt_raw_frames_queue') \
                .set_property('leaky', 'downstream')
            self.source_pipeline.get_by_name('appsink') \
                .set_property('sync', False)

        self.source_pipeline.set_state(Gst.State.PLAYING)

    def _get_sample(self, timeout_secs=10):
        try:
            # Timeout in case no frames are received. This happens when the
            # Hauppauge HDPVR video-capture device loses video.
            gst_sample = self.last_sample.get(timeout=timeout_secs)
            self.novideo = False
        except Queue.Empty:
            self.novideo = True
            pipeline = self.source_pipeline
            if pipeline:
                Gst.debug_bin_to_dot_file_with_ts(
                    pipeline, Gst.DebugGraphDetails.ALL, "NoVideo")
            raise NoVideo("No video")
        if isinstance(gst_sample, Exception):
            raise UITestError(str(gst_sample))

        if isinstance(gst_sample, Gst.Sample):
            self.last_used_sample = array_from_sample(gst_sample)

        return gst_sample

    def pull_frame(self, timeout_secs=10):
        return array_from_sample(self._get_sample(timeout_secs))

    def frames(self, timeout_secs=None):
        self.start_timestamp = None

        with self.lock:
            while True:
                ddebug("user thread: Getting sample at %s" % time.time())
                sample = self._get_sample(max(10, timeout_secs))
                ddebug("user thread: Got sample at %s" % time.time())
                timestamp = sample.get_buffer().pts

                if timeout_secs is not None:
                    if not self.start_timestamp:
                        self.start_timestamp = timestamp
                    if (timestamp - self.start_timestamp >
                            timeout_secs * Gst.SECOND):
                        debug("timed out: %d - %d > %d" % (
                            timestamp, self.start_timestamp,
                            timeout_secs * Gst.SECOND))
                        return

                try:
                    yield array_from_sample(sample)
                finally:
                    self.push_sample(sample)

    def on_new_sample(self, appsink):
        sample = appsink.emit("pull-sample")
        self.tell_user_thread(sample)
        if self.lock.acquire(False):  # non-blocking
            try:
                self.push_sample(sample)
            finally:
                self.lock.release()
        return Gst.FlowReturn.OK

    def tell_user_thread(self, sample_or_exception):
        # `self.last_sample` (a synchronised Queue) is how we communicate from
        # this thread (the GLib main loop) to the main application thread
        # running the user's script. Note that only this thread writes to the
        # Queue.

        if isinstance(sample_or_exception, Exception):
            ddebug("glib thread: reporting exception to user thread: %s" %
                   sample_or_exception)
        else:
            ddebug("glib thread: new sample (timestamp=%s). Queue.qsize: %d" %
                   (sample_or_exception.get_buffer().pts,
                    self.last_sample.qsize()))

        # Drop old frame
        try:
            self.last_sample.get_nowait()
        except Queue.Empty:
            pass

        self.last_sample.put_nowait(sample_or_exception)

    def draw(self, obj, duration_secs=None, label=""):
        with self.annotations_lock:
            if isinstance(obj, str) or isinstance(obj, unicode):
                obj = (
                    datetime.datetime.now().strftime("%H:%M:%S.%f")[:-4] +
                    ' ' + obj)
                self.text_annotations.append(
                    {"text": obj, "duration": duration_secs * Gst.SECOND})
            elif hasattr(obj, "region") and hasattr(obj, "timestamp"):
                annotation = _Annotation.from_result(obj, label=label)
                if annotation.pts:
                    self.annotations.append(annotation)
            else:
                raise TypeError(
                    "Can't draw object of type '%s'" % type(obj).__name__)

    def push_sample(self, sample):
        # Calculate whether we need to draw any annotations on the output video.
        now = sample.get_buffer().pts
        texts = []
        annotations = []
        with self.annotations_lock:
            for x in self.text_annotations:
                x.setdefault('start_time', now)
                if now < x['start_time'] + x['duration']:
                    texts.append(x)
            self.text_annotations = texts[:]
            for annotation in list(self.annotations):
                if annotation.pts == now:
                    annotations.append(annotation)
                if now >= annotation.pts:
                    self.annotations.remove(annotation)

        sample = gst_sample_make_writable(sample)
        img = array_from_sample(sample, readwrite=True)
        # Text:
        _draw_text(
            img, datetime.datetime.now().strftime("%H:%M:%S.%f")[:-4],
            (10, 30), (255, 255, 255))
        for i, x in enumerate(reversed(texts)):
            origin = (10, (i + 2) * 30)
            age = float(now - x['start_time']) / (3 * Gst.SECOND)
            color = (int(255 * max([1 - age, 0.5])),) * 3
            _draw_text(img, x['text'], origin, color)

        # Regions:
        for annotation in annotations:
            annotation.draw(img)

        self.appsrc.props.caps = sample.get_caps()
        self.appsrc.emit("push-buffer", sample.get_buffer())

    def on_error(self, pipeline, _bus, message):
        assert message.type == Gst.MessageType.ERROR
        if pipeline is not None:
            Gst.debug_bin_to_dot_file_with_ts(
                pipeline, Gst.DebugGraphDetails.ALL, "ERROR")
        err, dbg = message.parse_error()
        self.tell_user_thread(
            UITestError("%s: %s\n%s\n" % (err, err.message, dbg)))

    def on_warning(self, _bus, message):
        assert message.type == Gst.MessageType.WARNING
        Gst.debug_bin_to_dot_file_with_ts(
            self.source_pipeline, Gst.DebugGraphDetails.ALL, "WARNING")
        err, dbg = message.parse_warning()
        warn("Warning: %s: %s\n%s\n" % (err, err.message, dbg))

    def on_eos_from_source_pipeline(self, _bus, _message):
        if not self.tearing_down:
            warn("Got EOS from source pipeline")
            self.restart_source()

    def on_eos_from_sink_pipeline(self, _bus, _message):
        debug("Got EOS")
        self.received_eos.set()

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
        self.source_pipeline.set_state(Gst.State.NULL)
        self.source_pipeline = None
        GObjectTimeout(5, self.start_source).start()
        return False  # stop the timeout from running again

    def start_source(self):
        if self.tearing_down:
            return False
        warn("Restarting source pipeline...")
        self.create_source_pipeline()
        self.set_source_pipeline_playing()
        warn("Restarted source pipeline")
        if self.restart_source_enabled:
            self.underrun_timeout.start()
        return False  # stop the timeout from running again

    @staticmethod
    def appsink_await_eos(appsink, timeout=None):
        done = threading.Event()

        def on_eos(_appsink):
            done.set()
            return True
        hid = appsink.connect('eos', on_eos)
        d = appsink.get_property('eos') or done.wait(timeout)
        appsink.disconnect(hid)
        return d

    def startup(self):
        self.set_source_pipeline_playing()
        self.sink_pipeline.set_state(Gst.State.PLAYING)
        self.received_eos.clear()

        self.mainloop.__enter__()

    def teardown(self):
        self.tearing_down = True
        self.source_pipeline, source = None, self.source_pipeline
        if source:
            for elem in gst_iterate(source.iterate_sources()):
                elem.send_event(Gst.Event.new_eos())  # pylint: disable=E1120
            if not self.appsink_await_eos(
                    source.get_by_name('appsink'), timeout=10):
                debug("teardown: Source pipeline did not teardown gracefully")
            source.set_state(Gst.State.NULL)
            source = None

        debug("teardown: Sending eos")
        if self.appsrc.emit("end-of-stream") == Gst.FlowReturn.OK:
            if not self.received_eos.wait(10):
                debug("Timeout waiting for sink EOS")
        else:
            debug("Sending EOS to sink pipeline failed")
        self.sink_pipeline.set_state(Gst.State.NULL)

        self.mainloop.__exit__(None, None, None)


def _draw_text(numpy_image, text, origin, color, font_scale=1.0):
    if not text:
        return

    (width, height), _ = cv2.getTextSize(
        text, fontFace=cv2.FONT_HERSHEY_DUPLEX, fontScale=font_scale,
        thickness=1)
    cv2.rectangle(
        numpy_image, (origin[0] - 2, origin[1] + 2),
        (origin[0] + width + 2, origin[1] - height - 2),
        thickness=cv2.cv.CV_FILLED, color=(0, 0, 0))
    cv2.putText(
        numpy_image, text, origin, cv2.FONT_HERSHEY_DUPLEX,
        fontScale=font_scale, color=color, lineType=cv2.CV_AA)


class GObjectTimeout(object):
    """Responsible for setting a timeout in the GTK main loop."""
    def __init__(self, timeout_secs, handler, *args):
        self.timeout_secs = timeout_secs
        self.handler = handler
        self.args = args
        self.timeout_id = None

    def start(self):
        self.timeout_id = GObject.timeout_add(
            self.timeout_secs * 1000, self.handler, *self.args)

    def cancel(self):
        if self.timeout_id:
            GObject.source_remove(self.timeout_id)
        self.timeout_id = None


_BGR_CAPS = Gst.Caps.from_string('video/x-raw,format=BGR')


@imgproc_cache.memoize_iterator({"version": "25"})
def _find_matches(image, template, match_parameters, imglog):
    """Our image-matching algorithm.

    Runs 2 passes: `_find_candidate_matches` to locate potential matches, then
    `_confirm_match` to discard false positives from the first pass.

    Returns an iterator yielding zero or more `(True, position, certainty)`
    tuples for each location where `template` is found within `image`, followed
    by a single `(False, position, certainty)` tuple when there are no further
    matching locations.
    """

    if any(image.shape[x] < template.shape[x] for x in (0, 1)):
        raise ValueError("Source image must be larger than template image")
    if any(template.shape[x] < 1 for x in (0, 1)):
        raise ValueError("Template image must contain some data")
    if len(template.shape) != 3 or template.shape[2] != 3:
        raise ValueError("Template image must be 3 channel BGR")
    if template.dtype != numpy.uint8:
        raise ValueError("Template image must be 8-bits per channel")

    # pylint:disable=undefined-loop-variable
    for i, first_pass_matched, region, first_pass_certainty in \
            _find_candidate_matches(image, template, match_parameters,
                                    imglog):
        confirmed = (
            first_pass_matched and
            _confirm_match(image, region, template, match_parameters,
                           imwrite=lambda name, img: imglog.imwrite(
                               "match%d-%s" % (i, name), img)))  # pylint:disable=cell-var-from-loop

        yield (confirmed, list(region), first_pass_matched,
               first_pass_certainty)
        if not confirmed:
            break


def _find_candidate_matches(image, template, match_parameters, imglog):
    """First pass: Search for `template` in the entire `image`.

    This searches the entire image, so speed is more important than accuracy.
    False positives are ok; we apply a second pass later (`_confirm_match`) to
    weed out false positives.

    http://docs.opencv.org/modules/imgproc/doc/object_detection.html
    http://opencv-code.com/tutorials/fast-template-matching-with-image-pyramid
    """

    imglog.imwrite("source", image)
    imglog.imwrite("template", template)
    ddebug("Original image %s, template %s" % (image.shape, template.shape))

    method = {
        'sqdiff-normed': cv2.TM_SQDIFF_NORMED,
        'ccorr-normed': cv2.TM_CCORR_NORMED,
        'ccoeff-normed': cv2.TM_CCOEFF_NORMED,
    }[match_parameters.match_method]

    levels = get_config("match", "pyramid_levels", type_=int)
    if levels <= 0:
        raise ConfigurationError("'match.pyramid_levels' must be > 0")
    template_pyramid = _build_pyramid(template, levels)
    image_pyramid = _build_pyramid(image, len(template_pyramid))
    roi_mask = None  # Initial region of interest: The whole image.

    for level in reversed(range(len(template_pyramid))):
        if roi_mask is not None:
            if any(x < 3 for x in roi_mask.shape):
                roi_mask = None
            else:
                roi_mask = cv2.pyrUp(roi_mask)

        def imwrite(name, img):
            imglog.imwrite("level%d-%s" % (level, name), img)  # pylint:disable=cell-var-from-loop

        heatmap = _match_template(
            image_pyramid[level], template_pyramid[level], method,
            roi_mask, level, imwrite)

        # Relax the threshold slightly for scaled-down pyramid levels to
        # compensate for scaling artifacts.
        threshold = max(
            0,
            match_parameters.match_threshold - (0.2 if level > 0 else 0))

        matched, best_match_position, certainty = _find_best_match_position(
            heatmap, method, threshold, level)
        imglog.append(pyramid_levels=(
            matched, best_match_position, certainty, level))

        if not matched:
            break

        _, roi_mask = cv2.threshold(
            heatmap,
            ((1 - threshold) if method == cv2.TM_SQDIFF_NORMED else threshold),
            255,
            (cv2.THRESH_BINARY_INV if method == cv2.TM_SQDIFF_NORMED
             else cv2.THRESH_BINARY))
        roi_mask = roi_mask.astype(numpy.uint8)
        imwrite("source_matchtemplate_threshold", roi_mask)

    # pylint:disable=undefined-loop-variable
    region = Region(*_upsample(best_match_position, level),
                    width=template.shape[1], height=template.shape[0])

    for i in itertools.count():

        imglog.imwrite("match%d-heatmap" % i, heatmap)
        yield (i, matched, region, certainty)
        if not matched:
            return
        assert level == 0

        # Exclude any positions that would overlap the previous match, then
        # keep iterating until we don't find any more matches.
        exclude = region.extend(x=-(region.width - 1), y=-(region.height - 1))
        mask_value = (255 if match_parameters.match_method == 'sqdiff-normed'
                      else 0)
        cv2.rectangle(
            heatmap,
            # -1 because cv2.rectangle considers the bottom-right point to be
            # *inside* the rectangle.
            (exclude.x, exclude.y), (exclude.right - 1, exclude.bottom - 1),
            mask_value, cv2.cv.CV_FILLED)

        matched, best_match_position, certainty = _find_best_match_position(
            heatmap, method, threshold, level)
        region = Region(*best_match_position,
                        width=template.shape[1], height=template.shape[0])


def _match_template(image, template, method, roi_mask, level, imwrite):

    ddebug("Level %d: image %s, template %s" % (
        level, image.shape, template.shape))

    matches_heatmap = (
        (numpy.ones if method == cv2.TM_SQDIFF_NORMED else numpy.zeros)(
            (image.shape[0] - template.shape[0] + 1,
             image.shape[1] - template.shape[1] + 1),
            dtype=numpy.float32))

    if roi_mask is None:
        rois = [  # Initial region of interest: The whole image.
            _Rect(0, 0, matches_heatmap.shape[1], matches_heatmap.shape[0])]
    else:
        contours, _ = cv2.findContours(
            roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        rois = [
            _Rect(*cv2.boundingRect(x))
            # findContours ignores 1-pixel border of the image
            .shift(Position(-1, -1)).expand(_Size(2, 2))
            for x in contours]

    if logging.get_debug_level() > 1:
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
        imwrite("source_with_rois", source_with_rois)

    for roi in rois:
        r = roi.expand(_Size(*template.shape[:2])).shrink(_Size(1, 1))
        ddebug("Level %d: Searching in %s" % (level, roi))
        cv2.matchTemplate(
            image[r.to_slice()],
            template,
            method,
            matches_heatmap[roi.to_slice()])

    imwrite("source", image)
    imwrite("template", template)
    imwrite("source_matchtemplate", matches_heatmap)

    return matches_heatmap


def _find_best_match_position(matches_heatmap, method, threshold, level):
    min_value, max_value, min_location, max_location = cv2.minMaxLoc(
        matches_heatmap)
    if method == cv2.TM_SQDIFF_NORMED:
        certainty = (1 - min_value)
        best_match_position = Position(*min_location)
    elif method in (cv2.TM_CCORR_NORMED, cv2.TM_CCOEFF_NORMED):
        certainty = max_value
        best_match_position = Position(*max_location)
    else:
        raise ValueError("Invalid matchTemplate method '%s'" % method)

    matched = certainty >= threshold
    ddebug("Level %d: %s at %s with certainty %s" % (
        level, "Matched" if matched else "Didn't match",
        best_match_position, certainty))
    return (matched, best_match_position, certainty)


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


def _confirm_match(image, region, template, match_parameters, imwrite):
    """Second pass: Confirm that `template` matches `image` at `region`.

    This only checks `template` at a single position within `image`, so we can
    afford to do more computationally-intensive checks than
    `_find_candidate_matches`.
    """

    if match_parameters.confirm_method == "none":
        return True

    # Set Region Of Interest to the "best match" location
    roi = image[region.y:region.bottom, region.x:region.right]
    image_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    imwrite("confirm-source_roi", roi)
    imwrite("confirm-source_roi_gray", image_gray)
    imwrite("confirm-template_gray", template_gray)

    if match_parameters.confirm_method == "normed-absdiff":
        cv2.normalize(image_gray, image_gray, 0, 255, cv2.NORM_MINMAX)
        cv2.normalize(template_gray, template_gray, 0, 255, cv2.NORM_MINMAX)
        imwrite("confirm-source_roi_gray_normalized", image_gray)
        imwrite("confirm-template_gray_normalized", template_gray)

    absdiff = cv2.absdiff(image_gray, template_gray)
    _, thresholded = cv2.threshold(
        absdiff, int(match_parameters.confirm_threshold * 255),
        255, cv2.THRESH_BINARY)
    eroded = cv2.erode(
        thresholded,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=match_parameters.erode_passes)
    imwrite("confirm-absdiff", absdiff)
    imwrite("confirm-absdiff_threshold", thresholded)
    imwrite("confirm-absdiff_threshold_erode", eroded)

    return cv2.countNonZero(eroded) == 0


def _log_match_image_debug(imglog):

    if not imglog.enabled:
        return

    for matched, position, _, level in imglog.data["pyramid_levels"]:
        template = imglog.images["level%d-template" % level]
        imglog.imwrite("level%d-source_with_match" % level,
                       imglog.images["level%d-source" % level],
                       Region(x=position.x, y=position.y,
                              width=template.shape[1],
                              height=template.shape[0]),
                       _Annotation.MATCHED if matched else _Annotation.NO_MATCH)

    for i, result in enumerate(imglog.data["matches"]):
        imglog.imwrite(
            "match%d-source_with_match" % i, imglog.images["source"],
            result.region, _Annotation.MATCHED if result._first_pass_matched  # pylint:disable=protected-access
            else _Annotation.NO_MATCH)

    try:
        import jinja2
    except ImportError:
        warn(
            "Not generating html view of the image-processing debug images,"
            " because python 'jinja2' module is not installed.")
        return

    template = jinja2.Template("""
        <!DOCTYPE html>
        <html lang='en'>
        <head>
        <link href="http://netdna.bootstrapcdn.com/twitter-bootstrap/2.3.2/css/bootstrap-combined.min.css" rel="stylesheet">
        <style>
            h5 { margin-top: 40px; }
            .table th { font-weight: normal; background-color: #eee; }
            img {
                vertical-align: middle; max-width: 150px; max-height: 36px;
                padding: 1px; border: 1px solid #ccc; }
            p { line-height: 40px; }
            .table td { vertical-align: middle; }
        </style>
        </head>
        <body>
        <div class="container">
        <h4>
            <i>{{template_name}}</i>
            {{"matched" if matched else "didn't match"}}
        </h4>

        <h5>First pass (find candidate matches):</h5>

        <p>Searching for <b>template</b> {{link("template")}}
            within <b>source</b> image {{link("source")}}

        <table class="table">
        <tr>
          <th>Pyramid level</th>
          <th>Match #</th>
          <th>Searching for <b>template</b></th>
          <th>within <b>source regions of interest</b></th>
          <th>
            OpenCV <b>matchTemplate heatmap</b>
            with method {{match_parameters.match_method}}
            ({{"darkest" if match_parameters.match_method ==
                    "sqdiff-normed" else "lightest"}}
            pixel indicates position of best match).
          </th>
          <th>
            matchTemplate heatmap <b>above match_threshold</b>
            of {{"%g"|format(match_parameters.match_threshold)}}
            (white pixels indicate positions above the threshold).
          </th>
          <th><b>Matched?<b></th>
          <th>Best match <b>position</b></th>
          <th>&nbsp;</th>
          <th><b>certainty</b></th>
        </tr>

        {% for matched, position, certainty, level in pyramid_levels %}
        <tr>
          <td><b>{{level}}</b></td>
          <td><b>{{"0" if level == 0 else ""}}</b></td>
          <td>{{link("template", level)}}</td>
          <td>{{link("source_with_rois", level)}}</td>
          <td>{{link("source_matchtemplate", level)}}</td>
          <td>
            {{link("source_matchtemplate_threshold", level) if matched else ""}}
          </td>
          <td>{{"Matched" if matched else "Didn't match"}}</td>
          <td>{{position if level > 0 else matches[0].region}}</td>
          <td>{{link("source_with_match", level)}}</td>
          <td>{{"%.4f"|format(certainty)}}</td>
        </tr>
        {% endfor %}

        {% for m in matches[1:] %}
        {# note that loop.index is 1-based #}
        <tr>
          <td>&nbsp;</td>
          <td><b>{{loop.index}}</b></td>
          <td>&nbsp;</td>
          <td>&nbsp;</td>
          <td>{{link("heatmap", match=loop.index)}}</td>
          <td></td>
          <td>{{"Matched" if m._first_pass_matched else "Didn't match"}}</td>
          <td>{{m.region}}</td>
          <td>{{link("source_with_match", match=loop.index)}}</td>
          <td>{{"%.4f"|format(m.first_pass_result)}}</td>
        </tr>
        {% endfor %}

        </table>

        {% if show_second_pass %}
          <h5>Second pass (confirmation):</h5>

          <p><b>Confirm method:</b> {{match_parameters.confirm_method}}</p>

          {% if match_parameters.confirm_method != "none" %}
            <table class="table">
            <tr>
              <th>Match #</th>
              <th>Comparing <b>template</b></th>
              <th>against <b>source image's region of interest</b></th>
              {% if match_parameters.confirm_method == "normed-absdiff" %}
                <th><b>Normalised template</b></th>
                <th><b>Normalised source</b></th>
              {% endif %}
              <th><b>Absolute differences</b></th>
              <th>
                Differences <b>above confirm_threshold</b>
                of {{"%.2f"|format(match_parameters.confirm_threshold)}}
              </th>
              <th>
                After <b>eroding</b>
                {{match_parameters.erode_passes}}
                {{"time" if match_parameters.erode_passes == 1
                  else "times"}};
                the template matches if any differences (white pixels) remain
              </th>
            </tr>

            {% for m in matches %}
              {% if m._first_pass_matched %}
                <tr>
                  <td><b>{{loop.index0}}</b></td>
                  <td>{{link("confirm-template_gray", match=0)}}</td>
                  <td>{{link("confirm-source_roi_gray", match=loop.index0)}}</td>
                  {% if match_parameters.confirm_method == "normed-absdiff" %}
                    <td>{{link("confirm-template_gray_normalized", match=loop.index0)}}</td>
                    <td>{{link("confirm-source_roi_gray_normalized", match=loop.index0)}}</td>
                  {% endif %}
                  <td>{{link("confirm-absdiff", match=loop.index0)}}</td>
                  <td>{{link("confirm-absdiff_threshold", match=loop.index0)}}</td>
                  <td>{{link("confirm-absdiff_threshold_erode", match=loop.index0)}}</td>
                </tr>
              {% endif %}
            {% endfor %}

            </table>
          {% endif %}
        {% endif %}

        <p>For further help please read
            <a href="http://stb-tester.com/match-parameters.html">stb-tester
            image matching parameters</a>.

        </div>
        </body>
        </html>
    """)

    def link(name, level=None, match=None):
        return ("<a href='{0}{1}{2}.png'><img src='{0}{1}{2}.png'></a>"
                .format("" if level is None else "level%d-" % level,
                        "" if match is None else "match%d-" % match,
                        name))

    with open(os.path.join(imglog.outdir, "index.html"), "w") as f:
        f.write(template.render(
            link=link,
            match_parameters=imglog.data["match_parameters"],
            matches=imglog.data["matches"],
            min=min,
            pyramid_levels=imglog.data["pyramid_levels"],
            show_second_pass=any(
                x._first_pass_matched for x in imglog.data["matches"]),  # pylint:disable=protected-access
            template_name=imglog.data["template_name"],
        ))


def _iter_frames(depth=1):
    frame = inspect.currentframe(depth + 1)
    while frame:
        yield frame
        frame = frame.f_back


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
    for caller in _iter_frames(depth=2):
        caller_image = os.path.join(
            os.path.dirname(inspect.getframeinfo(caller).filename),
            image)
        if os.path.isfile(caller_image):
            return os.path.abspath(caller_image)

    # Fall back to image from cwd, for convenience of the selftests
    if os.path.isfile(image):
        return os.path.abspath(image)

    return None


def _load_mask(mask):
    """Loads the given mask file and returns it as an OpenCV image."""
    mask_path = _find_path(mask)
    debug("Using mask %s" % mask_path)
    if not mask_path or not os.path.isfile(mask_path):
        raise UITestError("No such mask file: %s" % mask)
    mask_image = cv2.imread(mask_path, cv2.CV_LOAD_IMAGE_GRAYSCALE)
    if mask_image is None:
        raise UITestError("Failed to load mask file: %s" % mask_path)
    return mask_image


# Tesseract sometimes has a hard job distinguishing certain glyphs such as
# ligatures and different forms of the same punctuation.  We strip out this
# superfluous information improving matching accuracy with minimal effect on
# meaning.  This means that stbt.ocr give much more consistent results.
_ocr_replacements = {
    # Ligatures
    u'ﬀ': u'ff',
    u'ﬁ': u'fi',
    u'ﬂ': u'fl',
    u'ﬃ': u'ffi',
    u'ﬄ': u'ffl',
    u'ﬅ': u'ft',
    u'ﬆ': u'st',
    # Punctuation
    u'“': u'"',
    u'”': u'"',
    u'‘': u'\'',
    u'’': u'\'',
    # These are actually different glyphs!:
    u'‐': u'-',
    u'‑': u'-',
    u'‒': u'-',
    u'–': u'-',
    u'—': u'-',
    u'―': u'-',
}
_ocr_transtab = dict((ord(amb), to) for amb, to in _ocr_replacements.items())


def _find_tessdata_dir():
    from distutils.spawn import find_executable

    tessdata_prefix = os.environ.get("TESSDATA_PREFIX", None)
    if tessdata_prefix:
        tessdata = tessdata_prefix + '/tessdata'
        if os.path.exists(tessdata):
            return tessdata
        else:
            raise RuntimeError('Invalid TESSDATA_PREFIX: %s' % tessdata_prefix)

    tess_prefix_share = os.path.normpath(
        find_executable('tesseract') + '/../../share/')
    for suffix in [
            '/tessdata', '/tesseract-ocr/tessdata', '/tesseract/tessdata']:
        if os.path.exists(tess_prefix_share + suffix):
            return tess_prefix_share + suffix
    raise RuntimeError('Installation error: Cannot locate tessdata directory')


def _symlink_copy_dir(a, b):
    """Behaves like `cp -rs` with GNU cp but is portable and doesn't require
    execing another process.  Tesseract requires files in the "tessdata"
    directory to be modified to set config options.  tessdata may be on a
    read-only system directory so we use this to work around that limitation.
    """
    from os.path import basename, join, relpath
    newroot = join(b, basename(a))
    for dirpath, dirnames, filenames in os.walk(a):
        for name in dirnames:
            if name not in ['.', '..']:
                rel = relpath(join(dirpath, name), a)
                os.mkdir(join(newroot, rel))
        for name in filenames:
            rel = relpath(join(dirpath, name), a)
            os.symlink(join(a, rel), join(newroot, rel))

_memoise_tesseract_version = None


def _tesseract_version(output=None):
    r"""Different versions of tesseract have different bugs.  This function
    allows us to tell the user if what they want isn't going to work.

    >>> (_tesseract_version('tesseract 3.03\n leptonica-1.70\n') >
    ...  _tesseract_version('tesseract 3.02\n'))
    True
    """
    global _memoise_tesseract_version
    if output is None:
        if _memoise_tesseract_version is None:
            try:
                _memoise_tesseract_version = subprocess.check_output(
                    ['tesseract', '--version'], stderr=subprocess.STDOUT)
            except OSError as e:
                if e.errno == errno.ENOENT:
                    return None
                else:
                    raise
        output = _memoise_tesseract_version

    line = [x for x in output.split('\n') if x.startswith('tesseract')][0]
    return LooseVersion(line.split()[1])


def _tesseract(frame, region, mode, lang, _config,
               user_patterns=None, user_words=None):

    if _config is None:
        _config = {}

    frame_region = _image_region(frame)
    intersection = Region.intersect(frame_region, region)
    if intersection is None:
        warn("Requested OCR in region %s which doesn't overlap with "
             "the frame %s" % (str(region), frame_region))
        return (u'', None)
    else:
        region = intersection

    return (_tesseract_subprocess(_crop(frame, region), mode, lang,
                                  _config, user_patterns, user_words),
            region)


@imgproc_cache.memoize({"tesseract_version": str(_tesseract_version()),
                        "version": "25"})
def _tesseract_subprocess(
        frame, mode, lang, _config, user_patterns, user_words):
    # We scale image up 3x before feeding it to tesseract as this
    # significantly reduces the error rate by more than 6x in tests.  This
    # uses bilinear interpolation which produces the best results.  See
    # http://stb-tester.com/blog/2014/04/14/improving-ocr-accuracy.html
    outsize = (frame.shape[1] * 3, frame.shape[0] * 3)
    subframe = cv2.resize(frame, outsize, interpolation=cv2.INTER_LINEAR)

    # $XDG_RUNTIME_DIR is likely to be on tmpfs:
    tmpdir = os.environ.get("XDG_RUNTIME_DIR", None)

    # The second argument to tesseract is "output base" which is a filename to
    # which tesseract will append an extension. Unfortunately this filename
    # isn't easy to predict in advance across different versions of tesseract.
    # If you give it "hello" the output will be written to "hello.txt", but in
    # hOCR mode it will be "hello.html" (tesseract 3.02) or "hello.hocr"
    # (tesseract 3.03). We work around this with a temporary directory:
    with utils.named_temporary_directory(prefix='stbt-ocr-', dir=tmpdir) as tmp:
        outdir = tmp + '/output'
        os.mkdir(outdir)

        cmd = ["tesseract", '-l', lang, tmp + '/input.png',
               outdir + '/output', "-psm", str(int(mode))]

        tessenv = os.environ.copy()

        if _config or user_words or user_patterns:
            tessdata_dir = tmp + '/tessdata'
            os.mkdir(tessdata_dir)
            _symlink_copy_dir(_find_tessdata_dir(), tmp)
            tessenv['TESSDATA_PREFIX'] = tmp + '/'

        if user_words:
            if 'user_words_suffix' in _config:
                raise ValueError(
                    "You cannot specify 'user_words' and " +
                    "'_config[\"user_words_suffix\"]' at the same time")
            with open('%s/%s.user-words' % (tessdata_dir, lang), 'w') as f:
                f.write('\n'.join(to_bytes(x) for x in user_words))
            _config['user_words_suffix'] = 'user-words'

        if user_patterns:
            if 'user_patterns_suffix' in _config:
                raise ValueError(
                    "You cannot specify 'user_patterns' and " +
                    "'_config[\"user_patterns_suffix\"]' at the same time")
            if _tesseract_version() < LooseVersion('3.03'):
                raise RuntimeError(
                    'tesseract version >=3.03 is required for user_patterns.  '
                    'version %s is currently installed' % _tesseract_version())
            with open('%s/%s.user-patterns' % (tessdata_dir, lang), 'w') as f:
                f.write('\n'.join(to_bytes(x) for x in user_patterns))
            _config['user_patterns_suffix'] = 'user-patterns'

        if _config:
            with open(tessdata_dir + '/configs/stbtester', 'w') as cfg:
                for k, v in _config.iteritems():
                    if isinstance(v, bool):
                        cfg.write(('%s %s\n' % (k, 'T' if v else 'F')))
                    else:
                        cfg.write("%s %s\n" % (k, to_bytes(v)))
            cmd += ['stbtester']

        cv2.imwrite(tmp + '/input.png', subframe)
        subprocess.check_output(cmd, stderr=subprocess.STDOUT, env=tessenv)
        with open(outdir + '/' + os.listdir(outdir)[0], 'r') as outfile:
            return outfile.read().decode('utf-8')


def _hocr_iterate(hocr):
    started = False
    need_space = False
    for elem in hocr.iterdescendants():
        if elem.tag == '{http://www.w3.org/1999/xhtml}p' and started:
            yield (u'\n', elem)
            need_space = False
        if elem.tag == '{http://www.w3.org/1999/xhtml}span' and \
                'ocr_line' in elem.get('class').split() and started:
            yield (u'\n', elem)
            need_space = False
        for e, t in [(elem, elem.text), (elem.getparent(), elem.tail)]:
            if t:
                if t.strip():
                    if need_space and started:
                        yield (u' ', None)
                    need_space = False
                    yield (unicode(t).strip(), e)
                    started = True
                else:
                    need_space = True


def _hocr_find_phrase(hocr, phrase):
    l = list(_hocr_iterate(hocr))
    words_only = [(w, elem) for w, elem in l if w.strip() != u'']

    # Dumb and poor algorithmic complexity but succint and simple
    if len(phrase) <= len(words_only):
        for x in range(0, len(words_only)):
            sublist = words_only[x:x + len(phrase)]
            if all(w[0].lower() == p.lower() for w, p in zip(sublist, phrase)):
                return sublist
    return None


def _hocr_elem_region(elem):
    while elem is not None:
        m = re.search(r'bbox (\d+) (\d+) (\d+) (\d+)', elem.get('title') or u'')
        if m:
            extents = [int(x) for x in m.groups()]
            return Region.from_extents(*extents)
        elem = elem.getparent()

# Tests
# ===========================================================================


def test_wait_for_motion_half_motion_str_2of4():
    with _fake_frames_at_half_motion() as dut:
        dut.wait_for_motion(consecutive_frames='2/4')


def test_wait_for_motion_half_motion_str_2of3():
    with _fake_frames_at_half_motion() as dut:
        dut.wait_for_motion(consecutive_frames='2/3')


def test_wait_for_motion_half_motion_str_3of4():
    with _fake_frames_at_half_motion() as dut:
        try:
            dut.wait_for_motion(consecutive_frames='3/4')
            assert False, "wait_for_motion succeeded unexpectedly"
        except MotionTimeout:
            pass


def test_wait_for_motion_half_motion_int():
    with _fake_frames_at_half_motion() as dut:
        try:
            dut.wait_for_motion(consecutive_frames=2)
            assert False, "wait_for_motion succeeded unexpectedly"
        except MotionTimeout:
            pass


@contextmanager
def _fake_frames_at_half_motion():
    class FakeDisplay(object):
        def frames(self, _timeout_secs=10):
            from _stbt.gst_utils import CapturedFrame
            data = [
                numpy.zeros((2, 2, 3), dtype=numpy.uint8),
                numpy.ones((2, 2, 3), dtype=numpy.uint8) * 255,
            ]
            for i in range(10):
                yield CapturedFrame(data[(i // 2) % 2], _gst_pts=int(i * 1e9))

        def draw(self, *_args, **_kwargs):
            pass

    dut = DeviceUnderTest(display=FakeDisplay())
    dut.get_frame = lambda: None
    yield dut


def test_ocr_on_static_images():
    for image, expected_text, region, mode in [
        # pylint: disable=C0301
        ("Connection-status--white-on-dark-blue.png", "Connection status: Connected", None, None),
        ("Connection-status--white-on-dark-blue.png", "Connected", Region(x=210, y=0, width=120, height=40), None),
        ("programme--white-on-black.png", "programme", None, None),
        ("UJJM--white-text-on-grey-boxes.png", "", None, None),
        ("UJJM--white-text-on-grey-boxes.png", "UJJM", None, OcrMode.SINGLE_LINE),
    ]:
        kwargs = {"region": region}
        if mode is not None:
            kwargs["mode"] = mode
        text = DeviceUnderTest().ocr(
            cv2.imread(os.path.join(
                os.path.dirname(__file__), "..", "tests", "ocr", image)),
            **kwargs)
        assert text == expected_text, (
            "Unexpected text. Expected '%s'. Got: %s" % (expected_text, text))


def test_region_replace():
    from nose.tools import eq_, raises

    r = Region(x=10, y=20, width=20, height=30)

    def t(kwargs, expected):
        eq_(r.replace(**kwargs), expected)

    @raises(ValueError)
    def e(kwargs):
        r.replace(**kwargs)

    # No change
    yield t, dict(x=10), r
    yield t, dict(x=10, width=20), r
    yield t, dict(x=10, right=30), r

    # Not allowed
    yield e, dict(x=1, width=2, right=3)
    yield e, dict(y=1, height=2, bottom=3)

    # Allowed  # pylint:disable=C0301
    yield t, dict(x=11), Region(x=11, y=r.y, width=19, height=r.height)
    yield t, dict(width=19), Region(x=10, y=r.y, width=19, height=r.height)
    yield t, dict(right=29), Region(x=10, y=r.y, width=19, height=r.height)
    yield t, dict(x=11, width=20), Region(x=11, y=r.y, width=20, height=r.height)
    yield t, dict(x=11, right=21), Region(x=11, y=r.y, width=10, height=r.height)
    yield t, dict(x=11, right=21, y=0, height=5), Region(x=11, y=0, width=10, height=5)
