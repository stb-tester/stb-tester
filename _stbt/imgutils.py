# coding: utf-8

from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import inspect
import os
from collections import namedtuple

import cv2
import numpy

from .logging import ddebug, debug, warn
from .types import Region
from .utils import to_native_str, to_unicode


class Frame(numpy.ndarray):
    """A frame of video.

    A ``Frame`` is what you get from `stbt.get_frame` and `stbt.frames`. It is
    a subclass of `numpy.ndarray`, which is the type that OpenCV uses to
    represent images. Data is stored in 8-bit, 3 channel BGR format.

    In addition to the members inherited from `numpy.ndarray`, ``Frame``
    defines the following attributes:

    :ivar float time: The wall-clock time when this video-frame was captured,
        as number of seconds since the unix epoch (1970-01-01T00:00:00Z). This
        is the same format used by the Python standard library function
        `time.time`.
    """
    def __new__(cls, array, dtype=None, order=None, time=None, _draw_sink=None):
        obj = numpy.asarray(array, dtype=dtype, order=order).view(cls)
        obj.time = time
        obj._draw_sink = _draw_sink  # pylint: disable=protected-access
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        self.time = getattr(obj, 'time', None)  # pylint: disable=attribute-defined-outside-init
        self._draw_sink = getattr(obj, '_draw_sink', None)  # pylint: disable=attribute-defined-outside-init

    def __repr__(self):
        if len(self.shape) == 3:
            dimensions = "%dx%dx%d" % (
                self.shape[1], self.shape[0], self.shape[2])
        else:
            dimensions = "%dx%d" % (self.shape[1], self.shape[0])
        return "<stbt.Frame(time=%s, dimensions=%s)>" % (
            "None" if self.time is None else "%.3f" % self.time,
            dimensions)


def _frame_repr(frame):
    if frame is None:
        return "None"
    if isinstance(frame, Frame):
        return repr(frame)
    if len(frame.shape) == 3:
        return "<%dx%dx%d>" % (frame.shape[1], frame.shape[0], frame.shape[2])
    else:
        return "<%dx%d>" % (frame.shape[1], frame.shape[0])


def crop(frame, region):
    """Returns an image containing the specified region of ``frame``.

    :type frame: `stbt.Frame` or `numpy.ndarray`
    :param frame: An image in OpenCV format (for example as returned by
      `frames`, `get_frame` and `load_image`, or the ``frame`` parameter of
      `MatchResult`).

    :type Region region: The region to crop.

    :returns: An OpenCV image (`numpy.ndarray`) containing the specified region
      of the source frame. This is a view onto the original data, so if you
      want to modify the cropped image call its ``copy()`` method first.

    Added in v28.
    """
    if not _image_region(frame).contains(region):
        raise ValueError("frame with dimensions %r doesn't contain %r"
                         % (frame.shape, region))
    return frame[region.y:region.bottom, region.x:region.right]


def _image_region(image):
    s = image.shape
    return Region(0, 0, s[1], s[0])


def load_image(filename, flags=None):
    """Find & read an image from disk.

    If given a relative filename, this will search in the directory of the
    Python file that called ``load_image``, then in the directory of that
    file's caller, etc. This allows you to use ``load_image`` in a helper
    function, and then call that helper function from a different Python file
    passing in a filename relative to the caller.

    Finally this will search in the current working directory. This allows
    loading an image that you had previously saved to disk during the same
    test run.

    This is the same lookup algorithm used by `stbt.match` and similar
    functions.

    :type filename: str or unicode
    :param filename: A relative or absolute filename.

    :param flags: Flags to pass to :ocv:pyfunc:`cv2.imread`.

    :returns: An image in OpenCV format — that is, a `numpy.ndarray` of 8-bit
        values. With the default ``flags`` parameter this will be 3 channels
        BGR, or 4 channels BGRA if the file has transparent pixels.
    :raises: `IOError` if the specified path doesn't exist or isn't a valid
        image file.

    * Added in v28.
    * Changed in v30: Include alpha (transparency) channel if the file has
      transparent pixels.
    """

    absolute_filename = find_user_file(filename)
    if not absolute_filename:
        raise IOError(to_native_str("No such file: %s" % to_unicode(filename)))
    image = imread(absolute_filename, flags)
    if image is None:
        raise IOError(to_native_str("Failed to load image: %s" %
                                    to_unicode(absolute_filename)))
    return image


def save_frame(image, filename):
    """Saves an OpenCV image to the specified file.

    Takes an image obtained from `get_frame` or from the `screenshot`
    property of `MatchTimeout` or `MotionTimeout`.
    """
    cv2.imwrite(filename, image)


class _ImageFromUser(namedtuple(
        '_ImageFromUser',
        'image relative_filename absolute_filename')):

    @property
    def friendly_name(self):
        if self.image is None:
            return None
        return self.relative_filename or '<Custom Image>'

    def short_repr(self):
        if self.image is None:
            return "None"
        if self.relative_filename:
            return repr(os.path.basename(self.relative_filename))
        return "<Custom Image>"


def _load_image(image, flags=None):
    if isinstance(image, _ImageFromUser):
        return image
    if isinstance(image, numpy.ndarray):
        return _ImageFromUser(image, None, None)
    else:
        relative_filename = image
        absolute_filename = find_user_file(relative_filename)
        if not absolute_filename:
            raise IOError("No such file: %s" % relative_filename)
        numpy_image = imread(absolute_filename, flags)
        if numpy_image is None:
            raise IOError("Failed to load image: %s" %
                          absolute_filename)
        return _ImageFromUser(numpy_image, relative_filename, absolute_filename)


def imread(filename, flags=None):
    if flags is None:
        cv2_flags = cv2.IMREAD_UNCHANGED
    else:
        cv2_flags = flags

    img = cv2.imread(to_native_str(filename), cv2_flags)
    if img is None:
        return None

    if img.dtype == numpy.uint16:
        warn("Image %s has 16 bits per channel. Converting to 8 bits."
             % filename)
        img = cv2.convertScaleAbs(img, alpha=1.0 / 256)
    elif img.dtype != numpy.uint8:
        raise ValueError("Image %s must be 8-bits per channel (got %s)"
                         % (filename, img.dtype))

    if flags is None:
        # We want: 3 colours, 8 bits per channel, alpha channel if present.
        # This differs from cv2.imread's default mode:
        #
        #                                     Alpha channel?   Converts from
        # Mode                                (if present)     grayscale to BGR?
        # ----------------------------------------------------------------------
        # IMREAD_COLOR (cv2.imread default)   No               Yes
        # IMREAD_UNCHANGED                    Yes              No
        # Our default                         Yes              Yes
        # ----------------------------------------------------------------------

        if len(img.shape) == 2 or img.shape[2] == 1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        # Remove alpha channel if it's 100% opaque
        if img.shape[2] == 4 and numpy.all(img[:, :, 3] == 255):
            img = img[:, :, :3]

    return img


def pixel_bounding_box(img):
    """
    Find the smallest region that contains all the non-zero pixels in an image.

    >>> pixel_bounding_box(numpy.array([[0]], dtype=numpy.uint8))
    >>> pixel_bounding_box(numpy.array([[1]], dtype=numpy.uint8))
    Region(x=0, y=0, right=1, bottom=1)
    >>> a = numpy.array([
    ...     [0, 0, 0, 0],
    ...     [0, 1, 1, 1],
    ...     [0, 1, 1, 1],
    ...     [0, 0, 0, 0],
    ... ], dtype=numpy.uint8)
    >>> pixel_bounding_box(a)
    Region(x=1, y=1, right=4, bottom=3)
    >>> pixel_bounding_box(numpy.stack([
    ...     numpy.zeros((4, 4), dtype=numpy.uint8),
    ...     numpy.zeros((4, 4), dtype=numpy.uint8),
    ...     a],
    ...     axis=-1))
    Region(x=1, y=1, right=4, bottom=3)
    >>> pixel_bounding_box(numpy.array([
    ...     [0, 0, 0, 0, 0, 0],
    ...     [0, 0, 0, 1, 0, 0],
    ...     [0, 1, 0, 0, 0, 0],
    ...     [0, 0, 0, 0, 1, 0],
    ...     [0, 0, 0, 0, 0, 0],
    ...     [0, 0, 1, 0, 0, 0],
    ...     [0, 0, 0, 0, 0, 0]
    ... ], dtype=numpy.uint8))
    Region(x=1, y=1, right=5, bottom=6)
    """
    if len(img.shape) == 2:
        pass
    elif len(img.shape) == 3 and img.shape[2] == 3:
        img = img.max(axis=2)
    else:
        raise ValueError("Single-channel or 3-channel (BGR) image required. "
                         "Provided image has shape %r" % (img.shape,))

    out = [None, None, None, None]

    for axis in (0, 1):
        flat = numpy.any(img, axis=axis)
        indices = numpy.where(flat)[0]
        if len(indices) == 0:
            return None
        out[axis] = indices[0]
        out[axis + 2] = indices[-1] + 1

    return Region.from_extents(*out)


def find_user_file(filename):
    """Searches for the given filename and returns the full path.

    Searches in the directory of the script that called `load_image` (or
    `match`, etc), then in the directory of that script's caller, etc.
    Falls back to searching the current working directory.

    :returns: Absolute filename, or None if it can't find the file.
    """
    if os.path.isabs(filename) and os.path.isfile(filename):
        return filename

    # Start searching from the first parent stack-frame that is outside of
    # the _stbt installation directory (this file's directory). We can ignore
    # the first 2 stack-frames:
    #
    # * stack()[0] is _find_user_file;
    # * stack()[1] is _find_user_file's caller: load_image or _load_image;
    # * stack()[2] is load_image's caller (the user script). It could also be
    #   _load_image's caller (e.g. `match`) so we still need to check until
    #   we're outside of the _stbt directory.

    filename = to_native_str(filename)
    _stbt_dir = os.path.abspath(os.path.dirname(__file__))
    caller = inspect.currentframe()
    try:
        # Skip this frame and the parent:
        caller = caller.f_back
        caller = caller.f_back
        while caller:
            caller_dir = os.path.abspath(
                os.path.dirname(inspect.getframeinfo(caller).filename))
            if not caller_dir.startswith(_stbt_dir):
                caller_path = os.path.join(caller_dir, filename)
                if os.path.isfile(caller_path):
                    ddebug("Resolved relative path %r to %r" % (
                        filename, caller_path))
                    return caller_path
            caller = caller.f_back
    finally:
        # Avoid circular references between stack frame objects and themselves
        # for more deterministic GC.  See
        # https://docs.python.org/3.7/library/inspect.html#the-interpreter-stack
        # for more information.
        del caller

    # Fall back to image from cwd, to allow loading an image saved previously
    # during the same test-run.
    if os.path.isfile(filename):
        abspath = os.path.abspath(filename)
        ddebug("Resolved relative path %r to %r" % (filename, abspath))
        return abspath

    return None


def limit_time(frames, duration_secs):
    """
    Adapts a frame iterator such that it will return EOS after `duration_secs`
    worth of video has been read.
    """
    import time
    end_time = time.time() + duration_secs
    for frame in frames:
        if frame.time > end_time:
            debug("timed out: %.3f > %.3f" % (frame.time, end_time))
            break
        else:
            yield frame
