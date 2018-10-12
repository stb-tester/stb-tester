# coding: utf-8
# Don't import anything not in the Python standard library from this file

from collections import namedtuple


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

    def to_slice(self):
        """A 2-dimensional slice suitable for indexing a `stbt.Frame`."""
        return (slice(self.y, self.bottom), slice(self.x, self.right))

    @staticmethod
    def from_extents(x, y, right, bottom):
        """Create a Region using right and bottom extents rather than width and
        height.

        Typically you'd use the ``right`` and ``bottom`` parameters of the
        ``Region`` constructor instead, but this factory function is useful
        if you need to create a ``Region`` from a tuple.

        >>> extents = (4, 4, 13, 10)
        >>> Region.from_extents(*extents)
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

    def above(self, height=float('inf')):
        """
        :returns: A new region above the current region, extending to the top
            of the frame (or to the specified height).
        """
        return self.replace(y=self.y - height, bottom=self.y)

    def below(self, height=float('inf')):
        """
        :returns: A new region below the current region, extending to the bottom
            of the frame (or to the specified height).
        """
        return self.replace(y=self.bottom, bottom=self.bottom + height)

    def right_of(self, width=float('inf')):
        """
        :returns: A new region to the right of the current region, extending to
            the right edge of the frame (or to the specified width).
        """
        return self.replace(x=self.right, right=self.right + width)

    def left_of(self, width=float('inf')):
        """
        :returns: A new region to the left of the current region, extending to
            the left edge of the frame (or to the specified width).
        """
        return self.replace(x=self.x - width, right=self.x)

    @staticmethod
    def bounding_box(*args):
        r"""Find the bounding box of the given regions.  Returns the smallest
        region which contains all passed regions.

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
        >>> print Region.bounding_box(None, None)
        None
        >>> print Region.bounding_box()
        None
        >>> Region.bounding_box(b)
        Region(x=20, y=30, right=30, bottom=50)
        >>> Region.bounding_box(a, b, c) == \
        ...     Region.bounding_box(a, Region.bounding_box(b, c))
        True

        New in v30: No longer limited to just taking 2 regions.
        """
        args = filter(None, args)
        if not args:
            return None
        return Region.from_extents(
            min(r.x for r in args),
            min(r.y for r in args),
            max(r.right for r in args),
            max(r.bottom for r in args))


Region.ALL = Region(x=-float('inf'), y=-float('inf'),
                    right=float('inf'), bottom=float('inf'))


class UITestError(Exception):
    """The test script had an unrecoverable error."""
    pass


class UITestFailure(Exception):
    """The test failed because the device under test didn't behave as expected.

    Inherit from this if you need to define your own test-failure exceptions.
    """
    pass
