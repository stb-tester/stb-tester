from itertools import combinations

from pytest import raises

from stbt import Grid, Region


def test_grid():
    g = Grid(Region(0, 0, 6, 2), cols=6, rows=2)
    assert g.area == 12

    def check_conversions(g, region, position, index):
        assert g.region_to_position(region) == position
        assert g.index_to_position(index) == position
        assert g.region_to_index(region) == index
        assert g.position_to_index(position) == index
        assert g.index_to_region(index) == region
        assert g.position_to_region(position) == region

    check_conversions(g, Region(0, 0, 1, 1), (0, 0), 0)
    check_conversions(g, Region(5, 1, 1, 1), (5, 1), 11)

    assert g.region_to_position(Region(4, 0, 3, 3)) == (5, 1)
    for x, y in [(-1, 0), (0, -1), (6, 0), (0, 2), (6, 2)]:
        with raises(ValueError):
            g.region_to_position(Region(x, y, 1, 1))

    g = Grid(Region(x=99, y=212, width=630, height=401), cols=5, rows=3)
    check_conversions(g, Region(351, 212, 126, 133), (2, 0), 2)
    check_conversions(g, Region(351, 212, 126, 133), (2, 0), 2)
    check_conversions(g, Region(477, 345, 126, 134), (3, 1), 8)

    for r1, r2 in combinations(g.cells, 2):
        assert Region.intersect(r1, r2) is None
