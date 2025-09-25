from __future__ import annotations

import errno
import inspect
import os
import re
import typing
import warnings
from functools import lru_cache
from typing import Optional, overload, TypeAlias

import cv2
import numpy
import numpy.typing

from .logging import ddebug, debug, warn
from .types import Region


FrameT : TypeAlias = numpy.typing.NDArray[numpy.uint8]

# Anything that load_image can take:
ImageT : TypeAlias = numpy.typing.NDArray[numpy.uint8] | str


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
    :ivar int width: The width of the frame, in pixels.
    :ivar int height: The height of the frame, in pixels.
    :ivar Region region: A `Region` corresponding to the full size of the
        frame — that is, ``Region(0, 0, width, height)``.
    """
    def __new__(cls, array, dtype=None, order=None, time: float|None = None,
                _draw_sink=None):
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
        # pylint: disable=attribute-defined-outside-init
        if time := getattr(obj, "time", None):
            self.time = float(time)
        else:
            self.time = None
        self._draw_sink = getattr(obj, '_draw_sink', None)  # pylint: disable=attribute-defined-outside-init

    def __repr__(self):
        return "<Frame(time=%s)>" % (
            "None" if self.time is None else "%.3f" % self.time,)

    def __str__(self):
        return repr(self)

    @property
    def width(self) -> int:
        return self.shape[1]  # pylint:disable=unsubscriptable-object

    @property
    def height(self) -> int:
        return self.shape[0]  # pylint:disable=unsubscriptable-object

    @property
    def region(self) -> Region:
        return Region(0, 0, self.shape[1], self.shape[0])


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
    """
    def __new__(cls, array, dtype=None, order=None,
                filename: str|None = None,
                absolute_filename: str|None = None):

        obj = numpy.asarray(array, dtype=dtype, order=order).view(cls)
        i = isinstance(array, Image)
        obj.filename = filename or (i and array.filename) or None
        obj.absolute_filename = (absolute_filename or
                                 (i and array.absolute_filename) or
                                 None)
        obj.relative_filename = _relative_filename(obj.absolute_filename)
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        # pylint: disable=attribute-defined-outside-init
        if filename := getattr(obj, "filename", None):
            self.filename = str(filename)
        else:
            self.filename = None
        if absolute_filename := getattr(obj, "absolute_filename", None):
            self.absolute_filename = str(absolute_filename)
        else:
            self.absolute_filename = None
        if relative_filename := getattr(obj, "relative_filename", None):
            self.relative_filename = str(relative_filename)
        else:
            self.relative_filename = None

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
    def width(self) -> int:
        return self.shape[1]  # pylint:disable=unsubscriptable-object

    @property
    def height(self) -> int:
        return self.shape[0]  # pylint:disable=unsubscriptable-object

    @property
    def region(self) -> Region:
        return Region(0, 0, self.shape[1], self.shape[0])


def _relative_filename(absolute_filename) -> str|None:
    """Returns filename relative to the test-pack root if inside the test-pack,
    or absolute path if outside the test-pack.
    """
    if absolute_filename is None:
        return None
    import stbt_core
    root = stbt_core.TEST_PACK_ROOT
    if root is None:
        return absolute_filename
    relpath = os.path.relpath(absolute_filename, root)
    if relpath.startswith(".."):
        return absolute_filename
    return relpath


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

    Any ``stbt`` APIs that take a ``Color`` will also accept a string or tuple
    in the above formats, so you don't need to construct a ``Color`` explicitly.
    """
    @overload
    def __init__(self, hexstring: str) -> None:
        ...
    @overload
    def __init__(self, blue: int, green: int, red: int, /) -> None:
        ...
    @overload
    def __init__(self, blue: int, green: int, red: int,
                 alpha: Optional[int] = None, /) -> None:
        ...
    # kwargs:
    @overload
    def __init__(self, *, blue: int, green: int, red: int,
                 alpha: Optional[int] = None) -> None:
        ...
    @overload
    def __init__(self, bgr: tuple[int, int, int]) -> None:
        ...
    @overload
    def __init__(self, bgra: tuple[int, int, int, int]) -> None:
        ...
    @overload
    def __init__(self, color: Color, /) -> None:
        ...
    def __init__(self, *args,
                 hexstring: str|None = None,
                 blue: int|None = None,
                 green: int|None = None,
                 red: int|None = None,
                 alpha: int|None = None,
                 bgr: tuple[int, int, int]|None = None,
                 bgra: tuple[int, int, int, int]|None = None) -> None:

        self.array: numpy.ndarray  # BGR with shape (1, 1, 3) or BGRA (1, 1, 4)

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
        elif not args and bgra is not None:
            self.array = Color._from_sequence(*bgra)
        elif (not args and
                blue is not None and green is not None and red is not None):
            self.array = Color._from_sequence(blue, green, red, alpha)

        else:
            raise TypeError("Color: __init__() expected a Color, '#rrggbb' "
                            "string, or 3 integers in Blue-Green-Red order.")

        self.array.flags.writeable = False

        self.hexstring = (
            "#{0:02x}{1:02x}{2:02x}{3}".format(
                self.array[0][0][2], self.array[0][0][1], self.array[0][0][0],
                ("" if self.array.shape[2] == 3
                 else f"{self.array[0][0][3]:02x}")))

    @staticmethod
    def _from_string(s: str):
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
    def _from_sequence(b: int|str, g: int|str, r: int|str,
                       a: int|str|None = None):
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

    def __repr__(self) -> str:
        return f"Color('{self.hexstring}')"

    def __eq__(self, other: Color) -> bool:
        return isinstance(other, Color) and self.hexstring == other.hexstring

    def __hash__(self) -> int:
        return hash(self.hexstring)


ColorT : TypeAlias = Color | str | tuple[int, int, int]


def crop(frame: FrameT, region: Region) -> FrameT:
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


@typing.overload
def load_image(filename: ImageT) -> Image:
    ...


@typing.overload
def load_image(filename: ImageT, flags: int) -> Image:
    ...


@typing.overload
def load_image(
        filename: ImageT, *, color_channels: int | tuple[int, ...]) -> Image:
    ...


def load_image(filename, flags=None, color_channels=None) -> Image:
    """Find & read an image from disk.

    If given a relative filename, this will search in the directory of the
    Python file that called ``load_image``, then in the directory of that
    file's caller, and so on, until it finds the file. This allows you to use
    ``load_image`` in a helper function that takes a filename from its caller.

    Finally this will search in the current working directory. This allows
    loading an image that you had previously saved to disk during the same
    test run.

    This is the same search algorithm used by `stbt.match` and similar
    functions.

    :param str filename: A relative or absolute filename.

    :param flags: Flags to pass to :ocv:pyfunc:`cv2.imread`. Deprecated; use
      ``color_channels`` instead.

    :param tuple[int] color_channels: Tuple of acceptable numbers of color
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

    * Changed in v33: Added the ``color_channels`` parameter and deprecated
      ``flags``. The image will always be converted to the format specified by
      ``color_channels`` (previously it was only converted to the format
      specified by ``flags`` if it was given as a filename, not as a
      `stbt.Image` or numpy array). The returned numpy array is read-only.
    """
    if flags is not None:
        # Backwards compatibility
        if color_channels is not None:
            raise ValueError(
                "flags cannot be specified at the same time as color_channels")
        if flags == cv2.IMREAD_GRAYSCALE:
            color_channels = (1,)
        elif flags == cv2.IMREAD_COLOR:
            color_channels = (3,)
        elif flags == cv2.IMREAD_UNCHANGED:
            color_channels = (1, 3, 4)
        else:
            raise ValueError("Unsupported imread flags %s" % flags)
        warnings.warn(
            "load_image: flags=%s argument is deprecated. Use "
            "color_channels=%r instead" % (flags, color_channels),
            DeprecationWarning, stacklevel=2)

    if color_channels is None:
        color_channels = (3, 4)
    elif isinstance(color_channels, int):
        color_channels = (color_channels,)

    obj = filename
    if isinstance(obj, Image):
        filename = obj.filename
        absolute_filename = obj.absolute_filename
        img = _convert_color(obj, color_channels, absolute_filename)
    elif isinstance(obj, numpy.ndarray):
        filename = None
        absolute_filename = None
        img = _convert_color(obj, color_channels, absolute_filename)
        if img.shape[2] == 4:
            # Normalise transparency channel to either 0 or 255, for stbt.match
            img = img.copy()
            chan = img[:, :, 3]
            chan[chan < 255] = 0
    elif isinstance(filename, str):
        absolute_filename = find_file(filename)
        img = _imread(absolute_filename, color_channels)
    else:
        raise TypeError("load_image requires a filename or Image")

    if not isinstance(img, Image):
        img = Image(img, filename=filename, absolute_filename=absolute_filename)
    return img


@lru_cache(maxsize=5)
def _imread(absolute_filename, color_channels):
    if color_channels == (3,):
        flags = cv2.IMREAD_COLOR
    elif color_channels == (1,):
        flags = cv2.IMREAD_GRAYSCALE
    else:
        flags = cv2.IMREAD_UNCHANGED
    img = cv2.imread(absolute_filename, flags)
    if img is None:
        raise IOError("Failed to load image: %s" % absolute_filename)
    img = _convert_color(img, color_channels, absolute_filename)
    if img.shape[2] == 4:
        # Normalise transparency channel to either 0 or 255, for stbt.match
        chan = img[:, :, 3]
        chan[chan < 255] = 0
    img.flags.writeable = False
    return img


def _convert_color(img, color_channels, absolute_filename):
    if len(img.shape) not in [2, 3]:
        raise ValueError(
            "Invalid shape for image: %r. Shape must have 2 or 3 elements" %
            (img.shape,))

    if img.dtype == numpy.uint16:
        warn("Image %s has 16 bits per channel. Converting to 8 bits."
             % _filename_repr(absolute_filename))
        img = cv2.convertScaleAbs(img, alpha=1.0 / 256)
    elif img.dtype != numpy.uint8:
        raise ValueError("Image %s must be 8-bits per channel (got %s)"
                         % (_filename_repr(absolute_filename), img.dtype))

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
            "%s has %i channels" % (_filename_repr(absolute_filename), c))

    assert img.shape[2] in color_channels
    return img


def _filename_repr(absolute_filename):
    if absolute_filename is None:
        return "<Image>"
    else:
        return repr(_relative_filename(absolute_filename))


def save_frame(image: FrameT, filename: str):
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
    >>> pixel_bounding_box(numpy.array([[[1]]], dtype=numpy.uint8))
    Region(x=0, y=0, right=1, bottom=1)
    >>> pixel_bounding_box(numpy.array([[[1, 1, 1]]], dtype=numpy.uint8))
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
    if len(img.shape) == 2 or len(img.shape) == 3 and img.shape[2] == 1:
        pass
    elif len(img.shape) == 3 and img.shape[2] == 3:
        img = img.max(axis=2)
    else:
        raise ValueError("Single-channel or 3-channel (BGR) image required. "
                         "Provided image has shape %r" % (img.shape,))
    rect = cv2.boundingRect(img)
    if rect[2] == 0 or rect[3] == 0:
        return None
    else:
        return Region(*rect)


def find_file(filename: str) -> str:
    """Searches for the given filename relative to the directory of the caller.

    When Stb-tester runs a test, the "current working directory" is not the
    same as the directory of the test-pack git checkout. If you want to read
    a file that's committed to git (for example a CSV file with data that your
    test needs) you can use this function to find it. For example::

        f = open(stbt.find_file("my_data.csv"))

    If the file is not found in the directory of the Python file that called
    ``find_file``, this will continue searching in the directory of that
    function's caller, and so on, until it finds the file. This allows you to
    use ``find_file`` in a helper function that takes a filename from its
    caller.

    This is the same algorithm used by `load_image`.

    :param str filename: A relative filename.

    :rtype: str
    :returns: Absolute filename.
    :raises: `FileNotFoundError` if the file can't be found.

    Added in v33.
    """
    if os.path.isabs(filename):
        if os.path.isfile(filename):
            return filename

    else:
        caller = inspect.currentframe()
        assert caller
        try:
            caller = caller.f_back  # skip this frame (find_file)
            while caller:
                caller_dir = os.path.abspath(
                    os.path.dirname(inspect.getframeinfo(caller).filename))
                caller_path = os.path.join(caller_dir, filename)
                if os.path.isfile(caller_path):
                    ddebug("Resolved relative path %r to %r" % (
                        filename, caller_path))
                    return caller_path
                caller = caller.f_back
        finally:
            # Avoid circular references between stack frame objects and
            # themselves for more deterministic GC. See
            # https://docs.python.org/3.10/library/inspect.html#the-interpreter-stack
            del caller

        # Fall back to image from cwd, to allow loading an image saved
        # previously during the same test-run.
        if os.path.isfile(filename):
            abspath = os.path.abspath(filename)
            ddebug("Resolved relative path %r to %r" % (filename, abspath))
            return abspath

    raise FileNotFoundError(errno.ENOENT, "No such file", filename)


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
