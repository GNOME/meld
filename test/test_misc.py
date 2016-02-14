
import pytest
from meld.misc import merge_intervals


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
