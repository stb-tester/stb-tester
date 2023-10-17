from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TypeAlias

import cv2
import numpy

from .imgutils import (
    _convert_color, crop, find_file, Image, ImageT, _image_region, load_image,
    pixel_bounding_box, _relative_filename)
from .logging import logger
from .types import Region

try:
    from _stbt.xxhash import Xxhash64
except ImportError:
    Xxhash64 = None


MaskTypes: TypeAlias = "str | numpy.ndarray | Mask | Region | None"


def load_mask(mask: MaskTypes) -> Mask:
    """Used to load a mask from disk, or to create a mask from a `Region`.

    A mask is a black & white image (the same size as the video-frame) that
    specifies which parts of the frame to process: White pixels select the area
    to process, black pixels the area to ignore.

    In most cases you don't need to call ``load_mask`` directly; Stb-tester's
    image-processing functions such as `is_screen_black`, `press_and_wait`, and
    `wait_for_motion` will call ``load_mask`` with their ``mask`` parameter.
    This function is a public API so that you can use it if you are
    implementing your own image-processing functions.

    Note that you can pass a `Region` directly to the ``mask`` parameter of
    stbt functions, and you can create more complex masks by adding,
    subtracting, or inverting Regions (see :doc:`masks`).

    :param str|Region mask: A relative or absolute filename of a mask PNG
      image. If given a relative filename, this uses the algorithm from
      `load_image` to find the file.

      Or, a `Region` that specifies the area to process.

    :returns: A mask as used by `is_screen_black`, `press_and_wait`,
      `wait_for_motion`, and similar image-processing functions.

    Added in v33.
    """
    if mask is None:
        raise TypeError(
            "'mask=None' means an empty region. To analyse the entire "
            "frame use 'mask=Region.ALL' (which is the default)")
    elif isinstance(mask, Mask):
        return mask
    else:
        return Mask(mask)


class Mask:
    """Internal representation of a mask.

    Most users will never need to use this type directly; instead, pass a
    filename or a `Region` to the ``mask`` parameter of APIs like
    `stbt.wait_for_motion`. See :doc:`masks`.
    """
    def __init__(self, m: MaskTypes, *, invert: bool = False) -> None:
        """Private constructor; for public use see `load_mask`."""
        # One (and only one) of these will be set: filename, array, binop,
        # region.
        self._filename = None
        self._array = None
        self._binop = None
        self._region = None
        if isinstance(m, str):
            absolute_filename = find_file(m)
            self._filename = absolute_filename
            self._invert = invert
        elif isinstance(m, numpy.ndarray):
            self._array = load_image(m, color_channels=(1, 3))
            self._invert = invert
        elif isinstance(m, BinOp):
            self._binop = m
            self._invert = invert
        elif isinstance(m, Mask):
            self._filename = m._filename
            self._array = m._array
            self._binop = m._binop
            self._region = m._region
            self._invert = m._invert
            if invert:
                self._invert = not self._invert
        elif isinstance(m, Region):
            self._region = m
            self._invert = invert
        elif m is None:  # Region.intersect can return None for "no region"
            self._region = Region.ALL
            self._invert = not invert
        else:
            raise TypeError("Expected filename, Image, Mask, or Region. "
                            f"Got {m!r}")

    @staticmethod
    def from_alpha_channel(image: ImageT) -> Mask:
        """Create a mask from the alpha channel of an image.

        :type image: string or `numpy.ndarray`
        :param image:
          An image with an alpha (transparency) channel. This can be the
          filename of a png file on disk, or an image previously loaded with
          `stbt.load_image`.

          Filenames should be relative paths. See `stbt.load_image` for the
          path lookup algorithm.
        """
        image = load_image(image)
        if image.shape[2] == 4:
            return Mask(image[:, :, 3])
        else:
            return Mask(_image_region(image))

    def __eq__(self, o):
        if isinstance(o, Region):
            return self.__eq__(Mask(o))
        if not isinstance(o, Mask):
            return False
        if self._array is not None:
            return numpy.array_equal(self._array, o._array)
        else:
            return ((self._filename, self._binop, self._region, self._invert) ==
                    (o._filename, o._binop, o._region, o._invert))

    def __hash__(self):
        if self._region is not None and not self._invert:
            return hash(self._region)
        elif self._array is not None:
            if Xxhash64:
                h = Xxhash64()
                h.update(numpy.ascontiguousarray(self._array).data)
                digest = h.hexdigest()
            else:
                digest = hash(self._array.data.tobytes())
            return hash((self._array.shape, digest, self._invert))
        else:
            return hash((self._filename, self._binop, self._region,
                         self._invert))

    def to_array(self, region: Region, color_channels: int = 1) \
            -> tuple[numpy.ndarray | None, Region]:
        """Materialize the mask to a numpy array of the specified size.

        Most users will never need to call this method; it's for people who
        are implementing their own image-processing algorithms.

        :param stbt.Region region: A Region matching the size of the frame that
          you are processing.

        :param int color_channels: The number of channels required (1 or 3),
          according to your image-processing algorithm's needs. All channels
          will be identical — for example with 3 channels, pixels will be
          either [0, 0, 0] or [255, 255, 255].

        :rtype: tuple[numpy.ndarray | None, Region]
        :returns:
          A tuple of:

          * An image (numpy array), where masked-in pixels are white (255) and
            masked-out pixels are black (0). The array is the same size as
            the region in the second member of this tuple.
          * A bounding box (`stbt.Region`) around the masked-in area. If most
            of the frame is masked out, limiting your image-processing
            operations to this region will be faster.

          If the mask is just a Region, the first member of the tuple (the
          image) will be `None` because the bounding-box is sufficient.
        """
        if region.x != 0 or region.y != 0:
            raise ValueError(
                f"{region} must be a full-frame region starting at x=0, y=0")
        if color_channels not in (1, 3):
            raise ValueError(f"Invalid {color_channels=} (expected 1 or 3)")
        return _to_array_and_bounding_box_cached(self, region, color_channels)

    def __repr__(self):
        # In-order traversal, removing unnecessary parentheses.
        prefix = "~" if self._invert else ""
        if self._filename is not None:
            return f"{prefix}Mask({_relative_filename(self._filename)!r})"
        elif self._array is not None:
            if isinstance(self._array, Image) and self._array.relative_filename:
                return f"{prefix}Mask({self._array.relative_filename!r})"
            else:
                return f"{prefix}Mask(<Image>)"
        elif self._binop is not None:
            left_repr = repr(self._binop.left)
            right_repr = repr(self._binop.right)
            if "-" in right_repr and right_repr[0] not in ("~", "("):
                right_repr = f"({right_repr})"
            if prefix:
                open_paren, close_paren = "(", ")"
            else:
                open_paren, close_paren = "", ""
            return (f"{prefix}{open_paren}{left_repr} {self._binop.op} "
                    f"{right_repr}{close_paren}")
        elif self._region is not None:
            return f"{prefix}{self._region!r}"
        else:
            assert False, "Internal logic error"

    def __add__(self, other: MaskTypes) -> Mask:
        if isinstance(other, (Region, Mask, type(None))):
            return Mask(BinOp("+", self, Mask(other)))
        else:
            return NotImplemented

    def __radd__(self, other: MaskTypes) -> Mask:
        if isinstance(other, (Region, Mask, type(None))):
            return Mask(other).__add__(self)
        else:
            return NotImplemented

    def __sub__(self, other: MaskTypes) -> Mask:
        if isinstance(other, (Region, Mask, type(None))):
            return Mask(BinOp("-", self, Mask(other)))
        else:
            return NotImplemented

    def __rsub__(self, other: MaskTypes) -> Mask:
        if isinstance(other, (Region, Mask, type(None))):
            return Mask(other).__sub__(self)
        else:
            return NotImplemented

    def __invert__(self) -> Mask:
        return Mask(self, invert=True)


@dataclass(frozen=True)
class BinOp:
    op: str  # "+" or "-"
    left: Mask
    right: Mask


@lru_cache(maxsize=10)
def _to_array_and_bounding_box_cached(
        mask: Mask,
        region: Region,
        color_channels: int) -> tuple[numpy.ndarray | None, Region]:

    if mask._region is not None and not mask._invert:
        array = None
    else:
        array = _to_array(mask, region)

    if mask._region is Region.ALL:
        if mask._invert:
            bounding_box = None
        else:
            bounding_box = region
    elif mask._region is not None and not mask._invert:
        bounding_box = Region.intersect(region, mask._region)
    else:
        bounding_box = pixel_bounding_box(array)
        if bounding_box is None:
            logger.warning("%r is an empty Region", mask)

    if bounding_box is None:
        raise ValueError("%r doesn't overlap with the frame's %r"
                         % (mask, region))

    if array is not None:
        array = crop(array, bounding_box)
        nonzeros = numpy.count_nonzero(array)
        if nonzeros == array.size:
            # Every pixel is masked in so the pixel-mask is redundant.
            array = None
    if array is not None:
        if color_channels == 3:
            array = cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)
        array.flags.writeable = False

    return array, bounding_box


def _to_array(mask: Mask, region: Region) -> numpy.ndarray:
    array: numpy.ndarray
    shape = (region.height, region.width, 1)
    if mask._filename is not None:
        array = load_image(mask._filename, color_channels=(1,))
        if array.shape != shape:
            raise ValueError(f"{mask}: shape {array.shape} doesn't match "
                             f"required shape {shape}")
    elif mask._array is not None:
        array = mask._array
        array = _convert_color(array, color_channels=(1,),
                               absolute_filename=array.absolute_filename)
        if array.shape != shape:
            raise ValueError(f"{mask}: shape {array.shape} doesn't match "
                             f"required shape {shape}")
    elif mask._binop is not None:
        n = mask._binop
        if n.op == "+":
            array = _to_array(n.left, region) | _to_array(n.right, region)
        elif n.op == "-":
            array = _to_array(n.left, region) & ~_to_array(n.right, region)  # pylint:disable=invalid-unary-operand-type
        else:
            assert False, f"Unreachable: Unknown op {n.op}"
    elif mask._region is not None:
        array = numpy.full(shape, 0, dtype=numpy.uint8)
        r = Region.intersect(mask._region, region)
        if r:
            array[r.y:r.bottom, r.x:r.right] = 255
    else:
        assert False, "Internal logic error"

    if mask._invert:
        array = ~array  # pylint:disable=invalid-unary-operand-type

    return array
