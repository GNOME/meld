
from unittest import mock

import pytest

from meld.misc import all_same, calc_syncpoint, merge_intervals


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


@pytest.mark.parametrize("lst, expected", [
    (None, True),
    ([], True),
    ([0], True),
    ([1], True),
    ([0, 0], True),
    ([0, 1], False),
    ([1, 0], False),
    ([1, 1], True),
    ([0, 0, 0], True),
    ([0, 0, 1], False),
    ([0, 1, 0], False),
    ([0, 1, 1], False),
    ([1, 0, 0], False),
    ([1, 0, 1], False),
    ([1, 1, 0], False),
    ([1, 1, 1], True)
])
def test_all_same(lst, expected):
    assert all_same(lst) == expected


@pytest.mark.parametrize("os_name, paths, expected", [
    ('posix', ['/tmp/foo1', '/tmp/foo2'], ['foo1', 'foo2']),
    ('posix', ['/tmp/foo1', '/tmp/foo2', '/tmp/foo3'], ['foo1', 'foo2', 'foo3']),
    ('posix', ['/tmp/bar/foo1', '/tmp/woo/foo2'], ['foo1', 'foo2']),
    ('posix', ['/tmp/bar/foo1', '/tmp/woo/foo1'], ['[bar] foo1', '[woo] foo1']),
    ('posix', ['/tmp/bar/foo1', '/tmp/woo/foo1', '/tmp/ree/foo1'], ['[bar] foo1', '[woo] foo1', '[ree] foo1']),
    ('posix', ['/tmp/bar/deep/deep', '/tmp/bar/shallow'], ['deep', 'shallow']),
    ('posix', ['/tmp/bar/deep/deep/foo1', '/tmp/bar/shallow/foo1'], ['[deep] foo1', '[shallow] foo1']),
    # This case doesn't actually make much sense, so it's not that bad
    # that our output is... somewhat unclear.
    ('posix', ['/tmp/bar/subdir/subsub', '/tmp/bar/'], ['subsub', 'bar']),
    ('nt', ['C:\\Users\\hmm\\bar', 'C:\\Users\\hmm\\foo'], ['bar', 'foo']),
    ('nt', ['C:\\Users\\bar\\hmm', 'C:\\Users\\foo\\hmm'], ['[bar] hmm', '[foo] hmm']),
    # Check that paths with no commonality are handled
    ('posix', ['nothing in', 'common'], ['nothing in', 'common']),
    ('posix', ['<unnamed>', '/tmp/real/path'], ['<unnamed>', '/tmp/real/path']),
])
def test_shorten_names(os_name, paths, expected):
    from meld.misc import shorten_names

    with mock.patch('os.name', os_name):
        assert shorten_names(*paths) == expected
