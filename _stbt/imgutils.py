# coding: utf-8

import inspect
import os
import re
import warnings
from collections import namedtuple
from typing import overload, Tuple

import cv2
import numpy

from .logging import ddebug, debug, warn
from .types import Region
from .utils import to_unicode


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
        i = isinstance(array, Frame)
        if time is None and i:
            obj.time = array.time
        else:
            obj.time = time
        obj._draw_sink = _draw_sink or (i and array._draw_sink) or None
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        self.time = getattr(obj, 'time', None)  # pylint: disable=attribute-defined-outside-init
        self._draw_sink = getattr(obj, '_draw_sink', None)  # pylint: disable=attribute-defined-outside-init

    def __repr__(self):
        if len(self.shape) == 3:
            dimensions = "%dx%dx%d" % (
                self.shape[1], self.shape[0], self.shape[2])  # pylint:disable=unsubscriptable-object

        elif len(self.shape) == 2:
            dimensions = "%dx%d" % (self.shape[1], self.shape[0])  # pylint:disable=unsubscriptable-object
        else:
            return super().__repr__()
        return "<Frame(time=%s, dimensions=%s)>" % (
            "None" if self.time is None else "%.3f" % self.time,
            dimensions)

    def __str__(self):
        return repr(self)

    @property
    def width(self):
        return self.shape[1]  # pylint:disable=unsubscriptable-object

    @property
    def height(self):
        return self.shape[0]  # pylint:disable=unsubscriptable-object


class Image(numpy.ndarray):
    """An image, possibly loaded from disk.

    This is a subclass of `numpy.ndarray`, which is the type that OpenCV uses
    to represent images.

    In addition to the members inherited from `numpy.ndarray`, ``Image``
    defines the following attributes:

    :vartype filename: str or None
    :ivar filename: The filename that was given to `stbt.load_image`.

    :vartype absolute_filename: str or None
    :ivar absolute_filename: The absolute path resolved by `stbt.load_image`.

    :vartype relative_filename: str or None
    :ivar relative_filename: The path resolved by `stbt.load_image`, relative
        to the root of the test-pack git repo.

    Added in v32.
    """
    def __new__(cls, array, dtype=None, order=None,
                filename=None, absolute_filename=None):

        obj = numpy.asarray(array, dtype=dtype, order=order).view(cls)
        i = isinstance(array, Image)
        obj.filename = filename or (i and array.filename) or None
        obj.absolute_filename = (absolute_filename or
                                 (i and array.absolute_filename) or
                                 None)
        obj.relative_filename = None

        if obj.absolute_filename is not None:
            import stbt_core
            root = getattr(stbt_core, "TEST_PACK_ROOT", None)
            if root is not None:
                obj.relative_filename = os.path.relpath(obj.absolute_filename,
                                                        root)
            else:
                obj.relative_filename = obj.absolute_filename

        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        # pylint: disable=attribute-defined-outside-init
        self.filename = getattr(obj, "filename", None)
        self.relative_filename = getattr(obj, "relative_filename", None)
        self.absolute_filename = getattr(obj, "absolute_filename", None)

    def __repr__(self):
        if len(self.shape) == 3:
            dimensions = "%dx%dx%d" % (
                self.shape[1], self.shape[0], self.shape[2])  # pylint:disable=unsubscriptable-object
        elif len(self.shape) == 2:
            dimensions = "%dx%d" % (self.shape[1], self.shape[0])  # pylint:disable=unsubscriptable-object
        else:
            return super().__repr__()
        if (self.relative_filename is None or
                self.relative_filename.startswith('../')):
            filename = self.absolute_filename
        else:
            filename = self.relative_filename
        return "<Image(filename=%r, dimensions=%s)>" % (filename, dimensions)

    def __str__(self):
        return repr(self)

    @property
    def width(self):
        return self.shape[1]  # pylint:disable=unsubscriptable-object

    @property
    def height(self):
        return self.shape[0]  # pylint:disable=unsubscriptable-object


def _frame_repr(frame):
    if frame is None:
        return "None"
    if isinstance(frame, (Image, Frame)):
        return repr(frame)
    if len(frame.shape) == 3:
        return "<%dx%dx%d>" % (frame.shape[1], frame.shape[0], frame.shape[2])
    else:
        return "<%dx%d>" % (frame.shape[1], frame.shape[0])


class Color:
    """A BGR color, optionally with an alpha (transparency) value.

    A Color can be created from an HTML-style hex string:

    >>> Color('#f77f00')
    Color('#f77f00')

    Or from Blue, Green, Red values in the range 0-255:

    >>> Color(0, 127, 247)
    Color('#f77f00')

    Note: When you specify the colors in this way, the BGR order is the
    opposite of the HTML-style RGB order. This is for compatibility with the
    way OpenCV stores colors.
    """
    @overload
    def __init__(self, hexstring: str) -> None:
        ...
    @overload
    def __init__(self, blue: int, green: int, red: int) -> None:
        ...
    @overload
    def __init__(self, bgr: Tuple[int, int, int]) -> None:
        ...
    def __init__(self, *args,
                 hexstring: str = None,
                 blue: int = None, green: int = None, red: int = None,
                 bgr: Tuple[int, int, int] = None):

        self.array: numpy.ndarray  # BGR with shape (1, 1, 3) or BGRA

        if len(args) == 1 and isinstance(args[0], Color):
            self.array = args[0].array

        elif len(args) == 1 and isinstance(args[0], str):
            self.array = Color._from_string(args[0])
        elif not args and hexstring is not None:
            self.array = Color._from_string(hexstring)

        elif (len(args) == 1 and
                isinstance(args[0], (list, tuple, numpy.ndarray)) and
                len(args[0]) in (3, 4)):
            self.array = Color._from_sequence(*args[0])
        elif len(args) in (3, 4):
            self.array = Color._from_sequence(*args)  # pylint:disable=no-value-for-parameter
        elif not args and bgr is not None:
            self.array = Color._from_sequence(*bgr)
        elif not args and all(x is not None for x in (blue, green, red)):
            self.array = Color._from_sequence(blue, green, red)

        else:
            raise TypeError("Color: __init__() expected a Color, '#rrggbb' "
                            "string, or 3 integers in Blue-Green-Red order. ")

        self.hexstring = (
            "#{0:02x}{1:02x}{2:02x}{3}".format(
                self.array[0][0][2], self.array[0][0][1], self.array[0][0][0],
                ("" if self.array.shape[2] == 3
                 else f"{self.array[0][0][3]:02x}")))

    @staticmethod
    def _from_string(s):
        m = re.match(r"^#?([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$", s)
        if m:
            s = m.group(1)
            if len(s) == 8:
                r = s[0:2]
                g = s[2:4]
                b = s[4:6]
                a = s[6:8]
            elif len(s) == 6:
                r = s[0:2]
                g = s[2:4]
                b = s[4:6]
                a = None
            elif len(s) == 3:
                r = s[0] * 2
                g = s[1] * 2
                b = s[2] * 2
                a = None
            else:
                assert False, f"unreachable: {s}"
        else:
            raise ValueError(
                f"Invalid color string. Expected hexadesimal digits in the "
                f"format '#rrggbb'; got {s!r}")
        return Color._from_sequence(b, g, r, a)

    @staticmethod
    def _from_sequence(b, g, r, a=None):
        channels = [b, g, r]
        if a is not None:
            channels.append(a)
        out = []
        for x in channels:
            if isinstance(x, str):
                x = int(x, 16)
            else:
                x = int(x)
            if not 0 <= x <= 255:
                raise ValueError(f"Color: __init__ expected a value between 0 "
                                 f"and 255: Got {x}")
            out.append(x)
        return (numpy.asarray(out, dtype=numpy.uint8)
                     .reshape((1, 1, len(channels))))

    def __repr__(self):
        return f"Color('{self.hexstring}')"

    def __eq__(self, other):
        return isinstance(other, Color) and self.hexstring == other.hexstring

    def __hash__(self):
        return hash(self.hexstring)


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
    """
    r = _validate_region(frame, region)
    return frame[r.y:r.bottom, r.x:r.right]


def _validate_region(frame, region):
    if region is None:
        raise TypeError(
            "'region=None' means an empty region. To analyse the entire "
            "frame use 'region=Region.ALL' (which is the default)")
    f = _image_region(frame)
    r = Region.intersect(f, region)
    if r is None:
        raise ValueError("%r doesn't overlap with the frame dimensions %ix%i"
                         % (region, frame.shape[1], frame.shape[0]))
    return r


def _image_region(image):
    s = image.shape
    return Region(0, 0, s[1], s[0])


def load_image(filename, flags=None, color_channels=None) -> Image:
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

    :param str filename: A relative or absolute filename.

    :param flags: Flags to pass to :ocv:pyfunc:`cv2.imread`. Deprecated; use
      ``color_channels`` instead.

    :param Tuple[int] color_channels: Tuple of acceptable numbers of color
      channels for the output image: 1 for grayscale, 3 for color, and 4 for
      color with an alpha (transparency) channel. For example,
      ``color_channels=(3, 4)`` will accept color images with or without an
      alpha channel. Defaults to ``(3, 4)``.

      If the image doesn't match the specified ``color_channels`` it will be
      converted to the specified format.

    :rtype: stbt.Image
    :returns: An image in OpenCV format — that is, a `numpy.ndarray` of 8-bit
        values. With the default ``color_channels`` parameter this will be 3
        channels BGR, or 4 channels BGRA if the file has transparent pixels.
    :raises: `IOError` if the specified path doesn't exist or isn't a valid
        image file.

    * Changed in v30: Include alpha (transparency) channel if the file has
      transparent pixels.
    * Changed in v32: Return type is now `stbt.Image`, which is a
      `numpy.ndarray` sub-class with additional attributes ``filename``,
      ``relative_filename`` and ``absolute_filename``.
    * Changed in v32: Allows passing an image (`numpy.ndarray` or `stbt.Image`)
      instead of a string, in which case this function returns the given image.
    * Changed in v33: Added the ``color_channels`` parameter and deprecated
      ``flags``. The image will always be converted to the format specified by
      ``color_channels`` (previously it was only converted to the format
      specified by ``flags`` if it was given as a filename, not as a
      `stbt.Image` or numpy array).
    """
    if flags is not None:
        # Backwards compatibility
        if color_channels is not None:
            raise Exception(
                "flags cannot be specified at the same time as color_channels")
        if flags == cv2.IMREAD_GRAYSCALE:
            color_channels = (1,)
        elif flags == cv2.IMREAD_COLOR:
            color_channels = (3,)
        elif flags == cv2.IMREAD_UNCHANGED:
            color_channels = (1, 3, 4)
        else:
            raise Exception("Unsupported imread flags %s" % flags)
        warnings.warn(
            "load_image: flags=%s argument is deprecated. Use "
            "color_channels=%r instead" % (flags, color_channels),
            DeprecationWarning)

    if color_channels is None:
        color_channels = (3, 4)
    elif isinstance(color_channels, int):
        color_channels = (color_channels,)

    obj = filename
    if isinstance(obj, Image):
        img = obj
        filename = obj.filename
        absolute_filename = obj.absolute_filename
    elif isinstance(obj, numpy.ndarray):
        img = obj  # obj.filename etc. will be None
        filename = None
        absolute_filename = None
    else:
        filename = to_unicode(filename)
        absolute_filename = find_user_file(filename)
        if not absolute_filename:
            raise IOError("No such file: %s" % filename)
        if color_channels == (3,):
            flags = cv2.IMREAD_COLOR
        elif color_channels == (1,):
            flags = cv2.IMREAD_GRAYSCALE
        else:
            flags = cv2.IMREAD_UNCHANGED
        img = cv2.imread(absolute_filename, flags)
        if img is None:
            raise IOError("Failed to load image: %s" % absolute_filename)

    if len(img.shape) not in [2, 3]:
        raise ValueError(
            "Invalid shape for image: %r. Shape must have 2 or 3 elements" %
            (img.shape,))

    if img.dtype == numpy.uint16:
        warn("Image %s has 16 bits per channel. Converting to 8 bits."
             % filename)
        img = cv2.convertScaleAbs(img, alpha=1.0 / 256)
    elif img.dtype != numpy.uint8:
        raise ValueError("Image %s must be 8-bits per channel (got %s)"
                         % (filename, img.dtype))

    if len(img.shape) == 2:
        img = img.reshape(img.shape + (1,))
    c = img.shape[2]

    if c == 1:
        if 1 in color_channels:
            pass
        elif 3 in color_channels:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif 4 in color_channels:
            img = numpy.concatenate(
                (cv2.cvtColor(img, cv2.COLOR_GRAY2BGR),
                 numpy.full(img.shape[:2] + (1,), 255, dtype=img.dtype)),
                axis=2)
        else:
            raise ValueError(
                "Can only convert 1 channel image to 1, 3 or 4 channels")
    elif c == 3:
        if 3 in color_channels:
            pass
        elif 4 in color_channels:
            img = numpy.concatenate(
                (img, numpy.full(img.shape[:2] + (1,), 255, dtype=img.dtype)),
                axis=2)
        elif 1 in color_channels:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img = img.reshape(img.shape + (1,))
        else:
            raise ValueError(
                "Can only convert 3 channel image to 1, 3 or 4 channels")
    elif c == 4:
        if 4 in color_channels:
            # Remove alpha channel if it's 100% opaque
            if 3 in color_channels and numpy.all(img[:, :, 3] == 255):
                img = img[:, :, :3]
        elif 3 in color_channels:
            img = img[:, :, :3]
        elif 1 in color_channels:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img = img.reshape(img.shape + (1,))
        else:
            raise ValueError(
                "Can only convert 3 channel image to 1, 3 or 4 channels")
    else:
        raise ValueError(
            "load_image can only handle images with 1, 3 or 4 color channels. "
            "%s has %i channels" % (filename, c))

    assert img.shape[2] in color_channels
    if not isinstance(img, Image):
        img = Image(img, filename=filename, absolute_filename=absolute_filename)

    return img


class NotRegion(namedtuple("NotRegion", "region")):
    """This is the inverse of a region.  This can be useful to pass as the mask
    parameter to our image processing functions.  Create instances of this type
    with:

    >>> mask_out(Region(34, 433, right=44, bottom=444))
    NotRegion(region=Region(x=34, y=433, right=44, bottom=444))
    """
    pass


def mask_out(mask):
    """Mask out a region (invert a mask).

    Example:

        SPINNER_REGION = stbt.Region(34, 433, right=44, bottom=444)
        stbt.wait_for_motion(mask=mask_out(SPINNER_REGION))
    """
    if isinstance(mask, Region):
        return NotRegion(mask)
    elif isinstance(mask, NotRegion):
        return mask.region
    else:
        return ~load_image(mask, color_channels=(1, 3))  # pylint:disable=invalid-unary-operand-type


def load_mask(mask, shape):
    """Used to load a mask from disk, or to convert it from a stbt.Region.

    This should be used by image processing functions, not by test-scripts
    """
    if mask is None:
        return None
    if isinstance(mask, Region):
        return _to_ndarray_mask(mask, shape=shape)
    elif isinstance(mask, NotRegion):
        return _to_ndarray_mask(mask, shape=shape, invert=True)
    elif isinstance(mask, (str, numpy.ndarray)):
        if shape is None:
            color_channels = (1, 3)
        else:
            color_channels = shape[2]
        mask = load_image(mask, color_channels=color_channels)
        if shape is not None and mask.shape != shape:
            raise ValueError(
                "Mask %r has wrong shape %r. Expected %r" % (
                    mask.relative_filename, mask.shape, shape))
        return mask
    else:
        raise TypeError("Don't know how to make mask from %r" % (mask,))


def _to_ndarray_mask(x, shape, dtype=numpy.uint8, invert=False):
    """Creates an ndarray mask from a stbt.Region"""
    out_val = 0
    if dtype == numpy.uint8:
        in_val = 255
    else:
        in_val = 1

    if invert:
        out_val, in_val = in_val, out_val

    out = numpy.full(shape, out_val, dtype=dtype)
    r = Region.intersect(x, Region(0, 0, shape[1], shape[0]))
    if r:
        out[r.y:r.bottom, r.x:r.right] = in_val

    return out


def save_frame(image, filename):
    """Saves an OpenCV image to the specified file.

    Takes an image obtained from `get_frame` or from the `screenshot`
    property of `MatchTimeout` or `MotionTimeout`.
    """
    cv2.imwrite(filename, image)


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
        out[axis] = int(indices[0])
        out[axis + 2] = int(indices[-1] + 1)

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
    # * stack()[0] is find_user_file;
    # * stack()[1] is find_user_file's caller: load_image
    # * stack()[2] is load_image's caller -- load_image can be called
    #   directly from the user script, or indirectly via stbt.match so we still
    #   need to check until we're outside of the _stbt directory.

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
        # https://docs.python.org/3.6/library/inspect.html#the-interpreter-stack
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
