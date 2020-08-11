from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

from itertools import combinations

import networkx as nx
from pytest import raises

from stbt_core import Grid, grid_to_navigation_graph, Position, Region


def test_grid():
    g = Grid(Region(0, 0, 6, 2), cols=6, rows=2)
    assert g.area == 12
    assert len(g) == 12

    def check_conversions(g, region, position, index):
        c = g.get(index=index)
        assert c.region == region
        assert c.position == position
        assert c.data is None
        assert c == g.get(region=region)
        assert c == g.get(position=position)
        assert c == g[index]
        assert c == g[position]
        assert c == g[region]

    check_conversions(g, Region(0, 0, 1, 1), (0, 0), 0)
    check_conversions(g, Region(5, 1, 1, 1), (5, 1), 11)
    check_conversions(g, Region(5, 1, 1, 1), Position(5, 1), 11)

    assert g.get(region=Region(4, 0, 3, 3)).position == (5, 1)
    for x, y in [(-1, 0), (0, -1), (6, 0), (0, 2), (6, 2)]:
        with raises(IndexError):
            g.get(region=Region(x, y, 1, 1))

    with raises(IndexError):
        g.get(index=12)
    with raises(IndexError):
        g.get(index=-13)
    with raises(IndexError):
        g.get(position=(6, 1))
    with raises(IndexError):
        g.get(data="J")

    g = Grid(Region(x=99, y=212, width=630, height=401), cols=5, rows=3)
    check_conversions(g, Region(351, 212, 126, 133), (2, 0), 2)
    check_conversions(g, Region(477, 345, 126, 134), (3, 1), 8)

    # If you use a region from a different source (e.g. stbt.match) then the
    # region you get *back* from the Grid should be the region defined by the
    # grid.
    r = Region(x=99, y=212, width=126, height=133)
    assert r == g.get(region=r.extend(right=5, bottom=5)).region

    for r1, r2 in combinations(g.cells, 2):
        assert Region.intersect(r1.region, r2.region) is None

    for i, c in enumerate(g):
        assert i == c.index


def test_grid_with_data():
    layout = ["ABCDEFG",
              "HIJKLMN",
              "OPQRSTU",
              "VWXYZ-'"]
    g = Grid(Region(0, 0, 100, 50), data=layout)
    assert g.cols == 7
    assert g.rows == 4
    assert g.get(index=9).data == "J"
    assert g.get(position=Position(x=2, y=1)).data == "J"
    assert g.get(data="J").index == 9
    assert g["J"].index == 9
    assert g[Position(x=2, y=1)].data == "J"
    assert g[2, 1].data == "J"
    assert g[-1].data == "'"
    for x in ["a", layout[0], layout]:
        with raises(IndexError):
            print(g[x])


def test_grid_to_navigation_graph():
    grid = Grid(region=None, data=["ABC",
                                   "DEF"])
    graph = grid_to_navigation_graph(grid)
    expected = nx.parse_edgelist(
        """
        A B KEY_RIGHT
        A D KEY_DOWN
        B A KEY_LEFT
        B C KEY_RIGHT
        B E KEY_DOWN
        C B KEY_LEFT
        C F KEY_DOWN
        D A KEY_UP
        D E KEY_RIGHT
        E B KEY_UP
        E D KEY_LEFT
        E F KEY_RIGHT
        F C KEY_UP
        F E KEY_LEFT
        """.split("\n"),
        create_using=nx.DiGraph(),
        data=[("key", str)])
    assert sorted(expected.edges(data=True)) == sorted(graph.edges(data=True))
    assert graph["A"]["B"] == {"key": "KEY_RIGHT"}
    assert graph["B"] == {"A": {"key": "KEY_LEFT"},
                          "C": {"key": "KEY_RIGHT"},
                          "E": {"key": "KEY_DOWN"}}


def test_grid_to_navigation_graph_without_data():
    # 012
    # 345
    grid = Grid(region=None, cols=3, rows=2)
    graph = grid_to_navigation_graph(grid)
    expected = nx.parse_edgelist(
        """
        0 1 KEY_RIGHT
        0 3 KEY_DOWN
        1 0 KEY_LEFT
        1 2 KEY_RIGHT
        1 4 KEY_DOWN
        2 1 KEY_LEFT
        2 5 KEY_DOWN
        3 0 KEY_UP
        3 4 KEY_RIGHT
        4 1 KEY_UP
        4 3 KEY_LEFT
        4 5 KEY_RIGHT
        5 2 KEY_UP
        5 4 KEY_LEFT
        """.split("\n"),
        create_using=nx.DiGraph(),
        nodetype=int,
        data=[("key", str)])
    assert sorted(expected.edges(data=True)) == sorted(graph.edges(data=True))
