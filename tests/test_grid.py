from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # pylint:disable=redefined-builtin,unused-wildcard-import,wildcard-import,wrong-import-order

from itertools import combinations

import networkx as nx
from pytest import raises

from stbt import Grid, Position, Region


def test_grid():
    g = Grid(Region(0, 0, 6, 2), cols=6, rows=2)
    assert g.area == 12

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
    assert g[-1].data == "'"
    for x in ["a", layout[0], layout]:
        with raises(IndexError):
            print(g[x])


def test_grid_navigation_graph():
    # The keyboard looks like this::
    #
    #     A  B  C  D  E  F  G
    #     H  I  J  K  L  M  N
    #     O  P  Q  R  S  T  U
    #     V  W  X  Y  Z  -  '

    grid = Grid(Region(0, 0, 100, 100), cols=7, rows=4)
    graph = grid.navigation_graph("ABCDEFGHIJKLMNOPQRSTUVWXYZ-'")
    assert sorted(G.edges(data="key")) == sorted(graph.edges(data="key"))


EDGELIST = """
    A B KEY_RIGHT
    A H KEY_DOWN
    B A KEY_LEFT
    B C KEY_RIGHT
    B I KEY_DOWN
    C B KEY_LEFT
    C D KEY_RIGHT
    C J KEY_DOWN
    D C KEY_LEFT
    D E KEY_RIGHT
    D K KEY_DOWN
    E D KEY_LEFT
    E F KEY_RIGHT
    E L KEY_DOWN
    F E KEY_LEFT
    F G KEY_RIGHT
    F M KEY_DOWN
    G F KEY_LEFT
    G N KEY_DOWN
    H I KEY_RIGHT
    H A KEY_UP
    H O KEY_DOWN
    I H KEY_LEFT
    I J KEY_RIGHT
    I B KEY_UP
    I P KEY_DOWN
    J I KEY_LEFT
    J K KEY_RIGHT
    J C KEY_UP
    J Q KEY_DOWN
    K J KEY_LEFT
    K L KEY_RIGHT
    K D KEY_UP
    K R KEY_DOWN
    L K KEY_LEFT
    L M KEY_RIGHT
    L E KEY_UP
    L S KEY_DOWN
    M L KEY_LEFT
    M N KEY_RIGHT
    M F KEY_UP
    M T KEY_DOWN
    N M KEY_LEFT
    N G KEY_UP
    N U KEY_DOWN
    O P KEY_RIGHT
    O H KEY_UP
    O V KEY_DOWN
    P O KEY_LEFT
    P Q KEY_RIGHT
    P I KEY_UP
    P W KEY_DOWN
    Q P KEY_LEFT
    Q R KEY_RIGHT
    Q J KEY_UP
    Q X KEY_DOWN
    R Q KEY_LEFT
    R S KEY_RIGHT
    R K KEY_UP
    R Y KEY_DOWN
    S R KEY_LEFT
    S T KEY_RIGHT
    S L KEY_UP
    S Z KEY_DOWN
    T S KEY_LEFT
    T U KEY_RIGHT
    T M KEY_UP
    T - KEY_DOWN
    U T KEY_LEFT
    U N KEY_UP
    U ' KEY_DOWN
    V W KEY_RIGHT
    V O KEY_UP
    W V KEY_LEFT
    W X KEY_RIGHT
    W P KEY_UP
    X W KEY_LEFT
    X Y KEY_RIGHT
    X Q KEY_UP
    Y X KEY_LEFT
    Y Z KEY_RIGHT
    Y R KEY_UP
    Z Y KEY_LEFT
    Z - KEY_RIGHT
    Z S KEY_UP
    - Z KEY_LEFT
    - ' KEY_RIGHT
    - T KEY_UP
    ' - KEY_LEFT
    ' U KEY_UP
"""
G = nx.parse_edgelist(EDGELIST.split("\n"),
                      create_using=nx.DiGraph(),
                      data=[("key", str)])
