from itertools import combinations

from pytest import raises

from stbt_core import Grid, Position, Region


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
