"""Copyright 2019 Stb-tester.com Ltd."""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

import networkx as nx

from _stbt.types import Position, Region


class Grid(object):
    """A grid with items arranged left to right then down.

    For example a keyboard, or a grid of posters, arranged like this::

        ABCDE
        FGHIJ
        KLMNO

    This class contains methods for converting between pixel coordinates on a
    screen, to x & y indexes into the grid positions.

    :param Region region: Where the grid is on the screen.
    :param int cols: Width of the grid, in number of columns.
    :param int rows: Height of the grid, in number of rows.
    """
    def __init__(self, region, cols, rows):
        self.region = region
        self.cols = cols
        self.rows = rows

    def __repr__(self):
        return "Grid(region=%r, cols=%r, rows=%r)" % (
            self.region, self.cols, self.rows)

    @property
    def area(self):
        return self.cols * self.rows

    @property
    def cells(self):
        return [self.position_to_region(x)
                for x in range(self.cols * self.rows)]

    def index_to_position(self, index):
        """Convert a 1D index into a 2D position.

        For example in this grid "I" is index ``9`` and position
        ``(x=3, y=1)``::

            ABCDE
            FGHIJ
            KLMNO

        :param int index: A 1D index into the grid, starting from 0 at the top
            left, counting along the top row left to right, then the next row,
            etc.
            A negative index counts backwards from the end of the grid (so
            ``-1`` is the bottom right position).

        :rtype: Position
        :returns: x & y indexes into the grid (zero-based).
        """
        area = self.cols * self.rows
        if index < -area:
            raise IndexError("Index out of range: index %r in %r" %
                             (index, self))
        elif index < 0:
            return self.index_to_position(area + index)
        elif index < area:
            return Position(x=index % self.cols, y=index // self.cols)
        else:
            raise IndexError("Index out of range: index %r in %r" %
                             (index, self))

    def position_to_index(self, position):
        """Convert a 2D position into a 1D index.

        The inverse of `Grid.index_to_position`.

        :param Position position: x & y indexes into the grid (zero-based).

        :rtype: int
        :returns: A 1D index into the grid, starting from 0 at the top
            left, counting along the top row left to right, then the next row,
            etc.
        """
        return position[0] + position[1] * self.cols

    def region_to_position(self, region):
        """Find the grid position that contains ``region``'s centre.

        :param stbt.Region region: Pixel coordinates on the screen, relative to
            the entire frame.
        :returns: A `Position`.
        """
        rel = region.translate(x=-self.region.x, y=-self.region.y)
        centre = (float(rel.x + rel.right) / 2,
                  float(rel.y + rel.bottom) / 2)
        pos = (centre[0] * self.cols // self.region.width,
               centre[1] * self.rows // self.region.height)
        if (pos[0] < 0 or pos[1] < 0 or
                pos[0] >= self.cols or pos[1] >= self.rows):
            raise ValueError(
                "The centre of region %r is outside the grid area %r" % (
                    region, self.region))
        return Position(int(pos[0]), int(pos[1]))

    def position_to_region(self, position):
        """Calculate the region of the screen that is covered by a grid cell.

        :param Position position: A 2D index (x, y) into the grid.

        :rtype: stbt.Region
        :returns: The pixel coordinates (relative to the entire frame) that
            correspond to the specified position.
        """
        if isinstance(position, int):
            position = self.index_to_position(position)
        elif not isinstance(position, Position):
            position = Position(position[0], position[1])

        position = Position(
            position.x if position.x >= 0 else self.cols - position.x,
            position.y if position.y >= 0 else self.rows - position.y)
        if (0 <= position.x < self.cols and 0 <= position.y < self.rows):
            return Region.from_extents(
                self.region.x + self.region.width * position.x //
                self.cols,
                self.region.y + self.region.height * position.y //
                self.rows,
                self.region.x + self.region.width * (position.x + 1) //
                self.cols,
                self.region.y + self.region.height * (position.y + 1) //
                self.rows)
        else:
            raise IndexError("Index out of range: position %r in %r" %
                             (position, self))

    def region_to_index(self, region):
        """Like `Grid.region_to_position`, but returns a 1D index instead of
        a 2D position.

        :param stbt.Region region: See `Grid.region_to_position`.
        :returns: See `Grid.position_to_index`.
        """
        pos = self.region_to_position(region)
        return pos.x + pos.y * self.cols

    def index_to_region(self, index):
        """Like `Grid.position_to_region`, but takes a 1D index instead of a 2D
        position.

        :param int index: See `Grid.index_to_position`.
        :returns: See `Grid.position_to_region`.
        """
        return self.position_to_region(self.index_to_position(index))

    def navigation_graph(self, names):
        """Generate a Graph that describes navigation between cells in the grid.

        Creates a `Directed Graph`_ that links adjacent cells in the grid with
        edges named "KEY_LEFT", "KEY_RIGHT", "KEY_UP", and "KEY_DOWN",
        corresponding to the keypress that will move a selection from one cell
        to another.

        :param names: An iterable containing the names for each node in the
            graph (cell in the grid) in the order corresponding to the cell's
            1D index into the grid (see `Grid.index_to_position`). For example
            if you have an on-screen keyboard that looks like this::

                A  B  C  D  E  F  G
                H  I  J  K  L  M  N
                O  P  Q  R  S  T  U
                V  W  X  Y  Z  -  '

            then ``names`` could be the string "ABCDEFGHIJKLMNOPQRSTUVWXYZ-'".

        :returns: A `networkx.DiGraph` suitable as the ``graph`` parameter of
            `stbt.Keyboard`.

        .. _Directed Graph: https://en.wikipedia.org/wiki/Directed_graph
        """
        G = nx.DiGraph()
        for index, name in enumerate(names):
            x, y = self.index_to_position(index)
            if x > 0:
                G.add_edge(name, names[self.position_to_index((x - 1, y))],
                           key="KEY_LEFT")
            if x < self.cols - 1:
                G.add_edge(name, names[self.position_to_index((x + 1, y))],
                           key="KEY_RIGHT")
            if y > 0:
                G.add_edge(name, names[self.position_to_index((x, y - 1))],
                           key="KEY_UP")
            if y < self.rows - 1:
                G.add_edge(name, names[self.position_to_index((x, y + 1))],
                           key="KEY_DOWN")
        return G
