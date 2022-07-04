from dataclasses import dataclass
from functools import lru_cache
from typing import Union, Tuple

import numpy

from .imgutils import (
    _convert_color, find_file, Image, load_image, _relative_filename)
from .types import Region

try:
    from _stbt.xxhash import Xxhash64
except ImportError:
    Xxhash64 = None


MaskTypes = Union[str, numpy.ndarray, "Mask", Region, None]


def load_mask(mask: MaskTypes) -> "Mask":
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
    subtracting, or inverting Regions (see `Region`).

    :param str|Region mask: A relative or absolute filename of a mask PNG
      image. If given a relative filename, this uses the algorithm from
      `load_image` to find the file.

      Or, a `Region` that specifies the area to process.

    :returns: A mask as used by `is_screen_black`, `press_and_wait`,
      `wait_for_motion`, and similar image-processing functions.

    Added in v33.
    """
    if mask is None:
        return None
    elif isinstance(mask, Mask):
        return mask
    else:
        return Mask(mask)


class Mask:
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
            if invert:
                self._region = Region.ALL
            else:
                self._region = None
            self._invert = False
        else:
            raise TypeError("Expected filename, Image, Mask, or Region. "
                            f"Got {m!r}")

    def __eq__(self, o):
        if not isinstance(o, Mask):
            return False
        if self._array is not None:
            return numpy.array_equal(self._array, o._array)
        else:
            return ((self._filename, self._binop, self._region, self._invert) ==
                    (o._filename, o._binop, o._region, o._invert))

    def __hash__(self):
        if self._array is not None:
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

    def to_array(self, shape: Tuple[int, int, int]) -> numpy.ndarray:
        return _to_array(self, shape)

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
        else:  # self._region is a Region or None
            return f"{prefix}{self._region!r}"

    def __add__(self, other: MaskTypes) -> "Mask":
        if isinstance(other, (Region, Mask, type(None))):
            return Mask(BinOp("+", self, Mask(other)))
        else:
            return NotImplemented

    def __radd__(self, other: MaskTypes) -> "Mask":
        if isinstance(other, (Region, Mask, type(None))):
            return Mask(other).__add__(self)
        else:
            return NotImplemented

    def __sub__(self, other: MaskTypes) -> "Mask":
        if isinstance(other, (Region, Mask, type(None))):
            return Mask(BinOp("-", self, Mask(other)))
        else:
            return NotImplemented

    def __rsub__(self, other: MaskTypes) -> "Mask":
        if isinstance(other, (Region, Mask, type(None))):
            return Mask(other).__sub__(self)
        else:
            return NotImplemented

    def __invert__(self) -> "Mask":
        return Mask(self, invert=True)


@dataclass(frozen=True)
class BinOp:
    op: str  # "+" or "-"
    left: Mask
    right: Mask


@lru_cache(maxsize=5)
def _to_array(mask: Mask, shape: Tuple[int, int, int]) -> numpy.ndarray:
    array: numpy.ndarray
    if len(shape) == 2:
        shape = shape + (1,)
    if mask._filename is not None:
        array = load_image(mask._filename, color_channels=(shape[2],))
        if array.shape != shape:
            raise ValueError(f"Mask shape {array.shape} and required shape "
                             f"{shape} don't match")
    elif mask._array is not None:
        array = mask._array
        array = _convert_color(array, color_channels=(shape[2],),
                               absolute_filename=array.absolute_filename)
        if array.shape != shape:
            raise ValueError(f"Mask shape {array.shape} and required shape "
                             f"{shape} don't match")
    elif mask._binop is not None:
        n = mask._binop
        if n.op == "+":
            array = n.left.to_array(shape) | n.right.to_array(shape)
        elif n.op == "-":
            array = n.left.to_array(shape) & ~n.right.to_array(shape)
        else:
            assert False, f"Unreachable: Unknown op {n.op}"
    else:  # Region (including None)
        array = numpy.full(shape, 0, dtype=numpy.uint8)
        r = Region.intersect(mask._region, Region(0, 0, shape[1], shape[0]))
        if r:
            array[r.y:r.bottom, r.x:r.right] = 255

    if mask._invert:
        array = ~array  # pylint:disable=invalid-unary-operand-type

    array.flags.writeable = False
    return array
