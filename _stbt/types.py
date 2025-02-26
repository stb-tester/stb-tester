# Don't import anything not in the Python standard library from this file

from __future__ import annotations

import typing
from collections import namedtuple
from enum import Enum
from typing import Optional, TypeAlias

if typing.TYPE_CHECKING:
    from .mask import Mask


PositionT : TypeAlias = tuple[int, int]
SizeT : TypeAlias = tuple[int, int]


class Position(typing.NamedTuple):
    """A point with ``x`` and ``y`` coordinates."""
    x: int
    y: int


class Size(typing.NamedTuple):
    """Size of a rectangle with ``width`` and ``height``."""
    width: int
    height: int


class Direction(Enum):

    #: Process the image from left to right
    HORIZONTAL = "horizontal"

    #: Process the image from top to bottom
    VERTICAL = "vertical"

    # For nicer formatting in generated API documentation:
    def __repr__(self):
        return str(self)


# None means no region
RegionT : TypeAlias = "Region | None"


class _RegionClsMethods(type):
    """Metaclass for `Region`.

    This defines some classmethods for Region, but in a way that they can't be
    called on an instance of Region (which is an easy mistake to make, but with
    incorrect behaviour). See <https://stackoverflow.com/a/42327454/606705>.
    """

    def intersect(cls, *args: RegionT) -> RegionT:
        out = Region.ALL
        args = iter(args)
        try:
            out = next(args)
        except StopIteration:
            # No arguments passed:
            return Region.ALL
        if out is None:
            return None

        for r in args:
            if not r:
                return None
            out = (max(out[0], r[0]), max(out[1], r[1]),
                   min(out[2], r[2]), min(out[3], r[3]))
            if out[0] >= out[2] or out[1] >= out[3]:
                return None
        return Region.from_extents(*out)

    @typing.overload
    def bounding_box(cls) -> None:
        ...

    @typing.overload
    def bounding_box(cls, *args: Region) -> Region:
        ...

    @typing.overload
    def bounding_box(cls, *args: RegionT) -> RegionT:
        ...

    def bounding_box(cls, *args: RegionT) -> RegionT:
        args = [_f for _f in args if _f]
        if not args:
            return None
        return Region.from_extents(
            min(r.x for r in args),
            min(r.y for r in args),
            max(r.right for r in args),
            max(r.bottom for r in args))


class Region(namedtuple('Region', 'x y right bottom'),
             metaclass=_RegionClsMethods):
    r"""
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
    >>> b.center
    Position(x=8, y=7)
    >>> b.contains(c), a.contains(b), c.contains(b), c.contains(None)
    (True, False, False, False)
    >>> b.contains(c.center), a.contains(b.center)
    (True, False)
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
    >>> print(Region.intersect(a, c))
    None
    >>> print(Region.intersect(None, a))
    None
    >>> Region.intersect(a)
    Region(x=0, y=0, right=8, bottom=8)
    >>> Region.intersect()
    Region.ALL
    >>> quadrant = Region(x=float("-inf"), y=float("-inf"), right=0, bottom=0)
    >>> quadrant.translate(2, 2)
    Region(x=-inf, y=-inf, right=2, bottom=2)
    >>> c.translate(x=-9, y=-3)
    Region(x=1, y=1, right=4, bottom=3)
    >>> Region(2, 3, 2, 1).translate(b)
    Region(x=6, y=7, right=8, bottom=8)
    >>> Region.intersect(Region.ALL, c) == c
    True
    >>> Region.ALL
    Region.ALL
    >>> print(Region.ALL)
    Region.ALL
    >>> c.above()
    Region(x=10, y=-inf, right=13, bottom=4)
    >>> c.below()
    Region(x=10, y=6, right=13, bottom=inf)
    >>> a.right_of()
    Region(x=8, y=0, right=inf, bottom=8)
    >>> a.right_of(width=2)
    Region(x=8, y=0, right=10, bottom=8)
    >>> c.left_of()
    Region(x=-inf, y=4, right=10, bottom=6)

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

    .. py:attribute:: width

        The width of the region, measured in pixels.

    .. py:attribute:: height

        The height of the region, measured in pixels.

    ``x``, ``y``, ``right``, ``bottom``, ``width`` and ``height`` can be
    infinite --- that is, ``float("inf")`` or ``-float("inf")``.

    .. py:attribute:: center

        A `stbt.Position` specifying the x & y coordinates of the region's
        center.

    .. py:staticmethod:: from_extents

        Create a Region using right and bottom extents rather than width and
        height.

        Typically you'd use the ``right`` and ``bottom`` parameters of the
        ``Region`` constructor instead, but this factory function is useful
        if you need to create a ``Region`` from a tuple.

        >>> extents = (4, 4, 13, 10)
        >>> Region.from_extents(*extents)
        Region(x=4, y=4, right=13, bottom=10)

    .. py:staticmethod:: bounding_box(*args)

        :returns: The smallest region that contains all the given regions.

        >>> a = Region(50, 20, right=60, bottom=40)
        >>> b = Region(20, 30, right=30, bottom=50)
        >>> c = Region(55, 25, right=70, bottom=35)
        >>> Region.bounding_box(a, b)
        Region(x=20, y=20, right=60, bottom=50)
        >>> Region.bounding_box(b, b)
        Region(x=20, y=30, right=30, bottom=50)
        >>> Region.bounding_box(None, b)
        Region(x=20, y=30, right=30, bottom=50)
        >>> Region.bounding_box(b, None)
        Region(x=20, y=30, right=30, bottom=50)
        >>> Region.bounding_box(b, Region.ALL)
        Region.ALL
        >>> print(Region.bounding_box(None, None))
        None
        >>> print(Region.bounding_box())
        None
        >>> Region.bounding_box(b)
        Region(x=20, y=30, right=30, bottom=50)
        >>> Region.bounding_box(a, b, c) == \
        ...     Region.bounding_box(a, Region.bounding_box(b, c))
        True

    .. py:staticmethod:: intersect(*args)

        :returns: The intersection of the passed regions, or ``None`` if the
            regions don't intersect.

        Any parameter can be ``None`` (an empty Region) so intersect is
        commutative and associative.
    """

    ALL: "Region"

    def __new__(
        cls,
        x: float,
        y: float,
        width: Optional[float] = None,
        height: Optional[float] = None,
        right: Optional[float] = None,
        bottom: Optional[float] = None,
    ):
        if (width is None) == (right is None):
            raise ValueError("You must specify either 'width' or 'right'")
        if (height is None) == (bottom is None):
            raise ValueError("You must specify either 'height' or 'bottom'")
        if right is None:
            right = x + width
        if bottom is None:
            bottom = y + height
        if right <= x:
            raise ValueError("'right' (%r) must be greater than 'x' (%r)"
                             % (right, x))
        if bottom <= y:
            raise ValueError("'bottom' (%r) must be greater than 'y' (%r)"
                             % (bottom, y))
        return super(Region, cls).__new__(cls, x, y, right, bottom)

    def __repr__(self):
        if self == Region.ALL:
            return 'Region.ALL'
        else:
            return 'Region(x=%r, y=%r, right=%r, bottom=%r)' \
                % (self.x, self.y, self.right, self.bottom)

    def __add__(self, other) -> Mask:
        """Adding 2 or more Regions together creates a mask with the pixels
        inside those Regions selected; all other pixels ignored."""
        from .mask import Mask
        return Mask(self).__add__(other)

    def __radd__(self, other) -> Mask:
        """Adding 2 or more Regions together creates a mask with the pixels
        inside those Regions selected; all other pixels ignored."""
        from .mask import Mask
        return Mask(self).__radd__(other)

    def __sub__(self, other) -> Mask:
        """Subtracting a Region removes that Region's pixels from the mask
        (so those pixels will be ignored)."""
        from .mask import Mask
        return Mask(self).__sub__(other)

    def __rsub__(self, other) -> Mask:
        """Subtracting a Region removes that Region's pixels from the mask
        (so those pixels will be ignored)."""
        from .mask import Mask
        return Mask(self).__rsub__(other)

    def __invert__(self) -> Mask:
        """Inverting a Region creates a mask with the Region's pixels ignored,
        and the pixels outside the Region selected."""
        from .mask import Mask
        return Mask(self, invert=True)

    @property
    def width(self) -> float:
        return self.right - self.x

    @property
    def height(self) -> float:
        return self.bottom - self.y

    @property
    def center(self) -> Position:
        return Position((self.x + self.right) // 2,
                        (self.y + self.bottom) // 2)

    @staticmethod
    def from_extents(x, y, right, bottom) -> Region:
        return Region(x, y, right=right, bottom=bottom)

    def to_slice(self) -> tuple[slice, slice]:
        """A 2-dimensional slice suitable for indexing a `stbt.Frame`."""
        return (slice(max(0, self.y),
                      max(0, self.bottom)),
                slice(max(0, self.x),
                      max(0, self.right)))

    def contains(self, other: Region) -> bool:
        """
        :returns: True if ``other`` (a `Region` or `Position`) is entirely
            contained within self.
        """
        if other is None:
            return False
        elif all(hasattr(other, a) for a in ("x", "y", "right", "bottom")):
            # a Region
            return (self.x <= other.x and other.right <= self.right and
                    self.y <= other.y and other.bottom <= self.bottom)
        elif all(hasattr(other, a) for a in ("x", "y")):  # a Position
            return (self.x <= other.x < self.right and
                    self.y <= other.y < self.bottom)
        else:
            raise TypeError("Region.contains expects a Region, Position, or "
                            "None. Got %r" % (other,))

    @typing.overload
    def translate(self, x: Region) -> Region:
        ...

    @typing.overload
    def translate(self, x: float | None, y: float | None) -> Region:
        ...

    @typing.overload
    def translate(self, x: tuple[int, int]) -> Region:
        ...

    def translate(self, x=None, y=None):
        """
        :returns: A new region with the position of the region adjusted by the
            given amounts.  The width and height are unaffected.

        ``translate`` accepts separate x and y arguments, or a single `Region`.

        For example, move the region 1px right and 2px down:

        >>> b = Region(4, 4, 9, 6)
        >>> b.translate(1, 2)
        Region(x=5, y=6, right=14, bottom=12)

        Move the region 1px to the left:

        >>> b.translate(x=-1)
        Region(x=3, y=4, right=12, bottom=10)

        Move the region 3px up:

        >>> b.translate(y=-3)
        Region(x=4, y=1, right=13, bottom=7)

        Move the region by another region.  This can be helpful if `TITLE`
        defines a region relative another UI element on screen.  You can then
        combine the two like so:

        >>> TITLE = Region(20, 5, 160, 40)
        >>> CELL = Region(140, 45, 200, 200)
        >>> TITLE.translate(CELL)
        Region(x=160, y=50, right=320, bottom=90)
        """
        try:
            p = x[0], x[1]
        except TypeError:
            p = x or 0, y or 0
        else:
            if y is not None:
                raise TypeError(
                    "translate() takes either a single Region argument or two "
                    "ints (both given)")
        return Region.from_extents(self.x + p[0], self.y + p[1],
                                   self.right + p[0], self.bottom + p[1])

    def extend(
        self,
        x: Optional[float] = 0,
        y: Optional[float] = 0,
        right: Optional[float] = 0,
        bottom: Optional[float] = 0,
    ) -> Region:
        """
        :returns: A new region with the edges of the region adjusted by the
            given amounts.
        """
        return Region.from_extents(
            self.x + x, self.y + y, self.right + right, self.bottom + bottom)

    def replace(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        width: Optional[float] = None,
        height: Optional[float] = None,
        right: Optional[float] = None,
        bottom: Optional[float] = None,
    ) -> Region:
        """
        :returns: A new region with the edges of the region set to the given
            coordinates.

        This is similar to `extend`, but it takes absolute coordinates within
        the image instead of adjusting by a relative number of pixels.
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

    def dilate(self, n: int) -> Region:
        """Expand the region by n px in all directions.

        >>> Region(20, 30, right=30, bottom=50).dilate(3)
        Region(x=17, y=27, right=33, bottom=53)
        """
        return self.extend(x=-n, y=-n, right=n, bottom=n)

    def erode(self, n: int) -> Region:
        """Shrink the region by n px in all directions.

        >>> Region(20, 30, right=30, bottom=50).erode(3)
        Region(x=23, y=33, right=27, bottom=47)
        >>> print(Region(20, 30, 10, 20).erode(5))
        None
        """
        if self.width > n * 2 and self.height > n * 2:
            return self.dilate(-n)
        else:
            return None

    def above(self, height: float = float("inf")) -> Region:
        """
        :returns: A new region above the current region, extending to the top
            of the frame (or to the specified height).
        """
        return self.replace(y=self.y - height, bottom=self.y)

    def below(self, height: float = float("inf")) -> Region:
        """
        :returns: A new region below the current region, extending to the bottom
            of the frame (or to the specified height).
        """
        return self.replace(y=self.bottom, bottom=self.bottom + height)

    def right_of(self, width: float = float("inf")) -> Region:
        """
        :returns: A new region to the right of the current region, extending to
            the right edge of the frame (or to the specified width).
        """
        return self.replace(x=self.right, right=self.right + width)

    def left_of(self, width: float = float("inf")) -> Region:
        """
        :returns: A new region to the left of the current region, extending to
            the left edge of the frame (or to the specified width).
        """
        return self.replace(x=self.x - width, right=self.x)


Region.ALL = Region(x=-float('inf'), y=-float('inf'),
                    right=float('inf'), bottom=float('inf'))


KeyT : TypeAlias = str


class Keypress():
    """Information about a keypress sent with `stbt.press`."""
    def __init__(self, key: str, start_time: float, end_time: float,
                 frame_before: "stbt.Frame"):

        #: The name of the key that was pressed.
        self.key: str = key

        #: The time just before the keypress started (in seconds since the
        #: unix epoch, like ``time.time()`` and ``stbt.Frame.time``).
        self.start_time: float = start_time

        #: The time when transmission of the keypress signal completed.
        self.end_time: float = end_time

        #: The most recent video-frame just before the keypress started.
        #: Typically this is used by functions like `stbt.press_and_wait` to
        #: detect when the device-under-test reacted to the keypress.
        self.frame_before: "stbt.Frame" = frame_before

    def __repr__(self):
        from .imgutils import _frame_repr
        return (
            "Keypress(key=%r, start_time=%r, end_time=%r, frame_before=%s)" % (
                self.key, self.start_time, self.end_time,
                _frame_repr(self.frame_before)))


class UITestError(Exception):
    """The test script had an unrecoverable error."""


class UITestFailure(Exception):
    """The test failed because the device under test didn't behave as expected.

    Inherit from this if you need to define your own test-failure exceptions.
    """


class NoVideo(Exception):
    """No video available from the source pipeline."""


class PDU:
    """API to control a specific outlet of a network-controlled Power
    Distribution Unit (PDU).
    """
    def power_on(self):
        self.set(True)

    def power_off(self):
        self.set(False)

    def set(self, power: bool):
        raise NotImplementedError()

    def get(self) -> bool:
        raise NotImplementedError()
