
import pytest
from meld.misc import calc_syncpoint, merge_intervals


@pytest.mark.parametrize("intervals, expected", [
    # Dominated by a single range
    ([(1, 5), (5, 9), (10, 11), (0, 20)], [(0, 20)]),
    # No overlap
    ([(1, 5), (6, 9), (10, 11)], [(1, 5), (6, 9), (10, 11)]),
    # Two overlap points between ranges
    ([(1, 5), (5, 9), (10, 12), (11, 20)], [(1, 9), (10, 20)]),
    # Two overlap points between ranges, out of order
    ([(5, 9), (1, 5), (11, 20), (10, 12)], [(1, 9), (10, 20)]),
    # Two equal ranges
    ([(1, 5), (7, 8), (1, 5)], [(1, 5), (7, 8)]),
    # Three ranges overlap
    ([(1, 5), (4, 10), (9, 15)], [(1, 15)])
])
def test_merge_intervals(intervals, expected):
    merged = merge_intervals(intervals)
    assert merged == expected


@pytest.mark.parametrize("value, page_size, lower, upper, expected", [
    # Boring top
    (0, 100, 0, 1000, 0.0),
    # Above the top!
    (0, 100, 100, 1000, 0.0),
    # Normal top scaling
    (25, 100, 0, 1000, 0.25),
    (50, 100, 0, 1000, 0.5),
    # Scaling with a lower offset
    (25, 100, 25, 1000, 0.0),
    (50, 100, 25, 1000, 0.25),
    # Somewhere in the middle
    (500, 100, 0, 1000, 0.5),
    # Normal bottom scaling
    (850, 100, 0, 1000, 0.5),
    (875, 100, 0, 1000, 0.75),
    # Boring bottom
    (900, 100, 0, 1000, 1.0),
    # Below the bottom!
    (1100, 100, 0, 1000, 1.0),
])
def test_calc_syncpoint(value, page_size, lower, upper, expected):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    adjustment = Gtk.Adjustment()
    adjustment.configure(value, lower, upper, 1, 1, page_size)
    syncpoint = calc_syncpoint(adjustment)
    assert syncpoint == expected
