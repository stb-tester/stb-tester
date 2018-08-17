import inspect
import os
from collections import namedtuple

import cv2
import numpy

from .logging import ddebug, debug
from .types import Region


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


class _ImageFromUser(namedtuple(
        '_ImageFromUser',
        'image relative_filename absolute_filename')):

    @property
    def friendly_name(self):
        if self.image is None:
            return None
        return self.relative_filename or '<Custom Image>'


def _load_image(image, flags=cv2.IMREAD_COLOR):
    if isinstance(image, _ImageFromUser):
        return image
    if isinstance(image, numpy.ndarray):
        return _ImageFromUser(image, None, None)
    else:
        relative_filename = image
        absolute_filename = find_user_file(relative_filename)
        if not absolute_filename:
            raise IOError("No such file: %s" % relative_filename)
        numpy_image = cv2.imread(absolute_filename, flags)
        if numpy_image is None:
            raise IOError("Failed to load image: %s" %
                          absolute_filename)
        return _ImageFromUser(numpy_image, relative_filename, absolute_filename)


def find_user_file(filename):
    """Searches for the given filename and returns the full path.

    Searches in the directory of the script that called `load_image` (or
    `match`, etc), then in the directory of that script's caller, etc.
    Falls back to searching the current working directory.

    :returns: Absolute filename, or None if it can't find the file.
    """
    if isinstance(filename, unicode):
        filename = filename.encode("utf-8")

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

    _stbt_dir = os.path.abspath(os.path.dirname(__file__))
    for caller in _iter_frames(depth=2):
        caller_dir = os.path.abspath(
            os.path.dirname(inspect.getframeinfo(caller).filename))
        if caller_dir.startswith(_stbt_dir):
            continue
        caller_path = os.path.join(caller_dir, filename)
        if os.path.isfile(caller_path):
            ddebug("Resolved relative path %r to %r" % (filename, caller_path))
            return caller_path

    # Fall back to image from cwd, to allow loading an image saved previously
    # during the same test-run.
    if os.path.isfile(filename):
        abspath = os.path.abspath(filename)
        ddebug("Resolved relative path %r to %r" % (filename, abspath))
        return abspath

    return None


def _iter_frames(depth=1):
    frame = inspect.currentframe(depth + 1)
    while frame:
        yield frame
        frame = frame.f_back


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
