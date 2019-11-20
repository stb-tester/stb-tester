"""Copyright 2019 Stb-tester.com Ltd."""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

from collections import namedtuple

import networkx as nx

from .types import Position, Region
from .utils import native_int


class Grid(object):
    """A grid with items arranged left to right, then down.

    For example a keyboard, or a grid of posters, arranged like this::

        ABCDE
        FGHIJ
        KLMNO

    All items must be the same size, and the spacing between them must be
    consistent.

    This class is useful for converting between pixel coordinates on a screen,
    to x & y indexes into the grid positions.

    :param Region region: Where the grid is on the screen.
    :param int cols: Width of the grid, in number of columns.
    :param int rows: Height of the grid, in number of rows.
    :param data: A 2D array (list of lists) containing data to associate with
        each cell. The data can be of any type. For example, if you are
        modelling a grid-shaped keyboard, the data could be the letter at each
        grid position. If ``data`` is specified, then ``cols`` and ``rows`` are
        optional.
    """
    def __init__(self, region, cols=None, rows=None, data=None):
        self.region = region
        self.data = data
        if (rows is None or cols is None) and data is None:
            raise ValueError(
                "Either `cols` and `rows`, or `data` must be specified")
        if rows is None:
            self.rows = len(data)
        else:
            self.rows = rows
        if cols is None:
            self.cols = len(data[0])
        else:
            self.cols = cols

    class Cell(namedtuple("Cell", "index position region data")):
        """A single cell in a `Grid`.

        Don't construct Cells directly; create a `Grid` instead.

        :ivar int index: The cell's 1D index into the grid, starting from 0 at
            the top left, counting along the top row left to right, then the
            next row left to right, etc.

        :ivar Position position: The cell's 2D index (x, y) into the grid
            (zero-based). For example in this grid "I" is index ``8`` and
            position ``(x=3, y=1)``::

                ABCDE
                FGHIJ
                KLMNO

        :ivar Region region: Pixel coordinates (relative to the entire frame)
            of the cell's bounding box.

        :ivar data: The data corresponding to the cell, if data was specified
            when you created the `Grid`.
        """
        pass

    def __repr__(self):
        s = "Grid(region=%r, cols=%r, rows=%r)" % (
            self.region, self.cols, self.rows)
        if self.data:
            return "<" + s + ">"
        else:
            return s

    @property
    def area(self):
        return self.cols * self.rows

    @property
    def cells(self):
        return [self.get(index=i)
                for i in range(self.cols * self.rows)]

    def get(self, index=None, position=None, region=None, data=None):
        """Retrieve a single cell in the Grid.

        For example, let's say that you're looking for the selected item in
        a grid by matching a reference image of the selection border. Then you
        can find the (x, y) position in the grid of the selection, like this::

            selection = stbt.match("selection.png")
            cell = grid.get(region=selection.region)
            position = cell.position

        You must specify one (and only one) of ``index``, ``position``,
        ``region``, or ``data``. For the meaning of these parameters see
        `Grid.Cell`. A negative index counts backwards from the end of the grid
        (so ``-1`` is the bottom right position).

        :returns: The `Grid.Cell` that matches the specified query; raises
            `IndexError` if the index/position/region is out of bounds or the
            data is not found.
        """
        if len([x for x in [index, position, region, data]
                if x is not None]) != 1:
            raise ValueError("Exactly one of index, position, region, or data "
                             "must be specified")
        if data is not None and self.data is None:
            raise IndexError("Searching by data %r but this Grid doesn't have "
                             "any data associated" % data)
        if index is not None:
            position = self._index_to_position(index)
            region = (None if self.region is None
                      else self._position_to_region(position))
        elif position is not None:
            index = self._position_to_index(position)
            region = (None if self.region is None
                      else self._position_to_region(position))
        elif region is not None:
            position = self._region_to_position(region)
            index = self._position_to_index(position)
            region = (None if self.region is None
                      else self._position_to_region(position))
        elif data is not None:
            for i in range(self.cols * self.rows):
                position = self._index_to_position(i)
                if data == self.data[position[1]][position[0]]:
                    index = i
                    region = (None if self.region is None
                              else self._position_to_region(position))
                    break
            else:
                raise IndexError("data %r not found" % (data,))

        return Grid.Cell(
            index,
            position,
            region,
            self.data and self.data[position[1]][position[0]])

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.get(index=key)
        elif isinstance(key, Region):
            return self.get(region=key)
        elif isinstance(key, Position) or (
                isinstance(key, tuple) and
                len(key) == 2 and
                isinstance(key[0], int) and
                isinstance(key[1], int)):
            return self.get(position=key)
        else:
            return self.get(data=key)

    def __iter__(self):
        for i in range(len(self)):  # pylint:disable=consider-using-enumerate
            yield self[i]

    def __len__(self):
        return self.cols * self.rows

    def _index_to_position(self, index):
        area = self.cols * self.rows
        if index < -area:
            raise IndexError("Index out of range: index %r in %r" %
                             (index, self))
        elif index < 0:
            return self._index_to_position(area + index)
        elif index < area:
            return Position(x=index % self.cols, y=index // self.cols)
        else:
            raise IndexError("Index out of range: index %r in %r" %
                             (index, self))

    def _position_to_index(self, position):
        return position[0] + position[1] * self.cols

    def _region_to_position(self, region):
        rel = region.translate(x=-self.region.x, y=-self.region.y)
        centre = (float(rel.x + rel.right) / 2,
                  float(rel.y + rel.bottom) / 2)
        pos = (centre[0] * self.cols // self.region.width,
               centre[1] * self.rows // self.region.height)
        if (pos[0] < 0 or pos[1] < 0 or
                pos[0] >= self.cols or pos[1] >= self.rows):
            raise IndexError(
                "The centre of region %r is outside the grid area %r" % (
                    region, self.region))
        return Position(native_int(pos[0]), native_int(pos[1]))

    def _position_to_region(self, position):
        if isinstance(position, int):
            position = self._index_to_position(position)
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


def grid_to_navigation_graph(grid):
    """Generate a Graph that describes navigation between cells in the grid.

    Creates a `networkx.DiGraph` (`Directed Graph`_) that models cells in the
    grid as nodes in the graph. Each edge in the graph has a ``key`` attribute
    set to "KEY_LEFT", "KEY_RIGHT", "KEY_UP", or "KEY_DOWN", corresponding to
    the keypress that will move a selection from one node to another.

    :param Grid grid: The grid to model. If the Grid has data associated
        with the cells, each node in the graph will be named with the
        corresponding cell's ``data``; otherwise the nodes are numbered
        according to the cell's ``index``. This means that the cell's ``data``
        must be `hashable`_ so that it can be used as a `networkx` node.

    :returns: A `networkx.DiGraph`.

    For example, to create a graph suitable as the ``graph`` parameter of
    `stbt.Keyboard`::

        grid = stbt.Grid(region, data=["ABCDEFG",
                                       "HIJKLMN",
                                       "OPQRSTU",
                                       "VWXYZ-'"])
        keyboard = stbt.Keyboard(grid_to_navigation_graph(grid))

    .. _Directed Graph: https://en.wikipedia.org/wiki/Directed_graph
    .. _hashable: https://docs.python.org/3.6/glossary.html#term-hashable
    """
    G = nx.DiGraph()

    def name(c):
        if c.data is None:
            return c.index
        else:
            return c.data

    for cell in grid:
        x, y = cell.position
        if x > 0:
            G.add_edge(name(cell), name(grid[x - 1, y]), key="KEY_LEFT")
        if x < grid.cols - 1:
            G.add_edge(name(cell), name(grid[x + 1, y]), key="KEY_RIGHT")
        if y > 0:
            G.add_edge(name(cell), name(grid[x, y - 1]), key="KEY_UP")
        if y < grid.rows - 1:
            G.add_edge(name(cell), name(grid[x, y + 1]), key="KEY_DOWN")
    return G
