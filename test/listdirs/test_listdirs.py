import pytest

from os import path
from meld.listdirs import list_dirs, flattern
from .fixture import make


@pytest.fixture
def different_dirs():
    make()


def files(*args):
    d = path.dirname(__file__)
    return list(path.join(d, arg) for arg in args)


@pytest.mark.parametrize(
    'roots, canonicalize, filterer, max_depth, expected', [
    # empty file list
    (None, None, None, None, 1),
    ((), None, None, None, 1),
    # simple
    (files('diffs/a', 'diffs/b'), None, None, None, 20),
    # ignore case
    (files('diffs/a', 'diffs/b'), str.lower, None, None, 17),
    # max_depth 0
    (files('diffs/a', 'diffs/b'), None, None, 0, 1),
    # max_depth 1
    (files('diffs/a', 'diffs/b'), None, None, 1, 7),
    # max_depth 2
    (files('diffs/a', 'diffs/b'), None, None, 2, 16),
    # ignore case and max_depth 2
    (files('diffs/a', 'diffs/b'), str.lower, None, 2, 14),
    # filter
    (files('diffs/a', 'diffs/b'), None, str.isalpha, None, 8),
])
def test_listdirs(
    roots, canonicalize, filterer, max_depth, expected, different_dirs
):
    result = flattern(list_dirs(roots, canonicalize, filterer), max_depth)
    lst = list(result)
    size = len(lst)
    assert size == expected
