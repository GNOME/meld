import pytest

from os import path
from meld.listdirs import list_dirs
from .fixture import make


@pytest.fixture
def different_dirs():
    make()


def files(*args):
    d = path.dirname(__file__)
    return list(path.join(d, arg) for arg in args)


@pytest.mark.parametrize('roots, canonicalize, max_depth, expected', [
    # empty file list
    (None, None, None, 0),
    ((), None, None, 0),
    # simple
    (files('diffs/a', 'diffs/b'), None, None, 20),
    # ignore case
    (files('diffs/a', 'diffs/b'), str.lower, None, 17),
    # max_depth 0
    (files('diffs/a', 'diffs/b'), None, 0, 1),
    # max_depth 1
    (files('diffs/a', 'diffs/b'), None, 1, 7),
    # max_depth 2
    (files('diffs/a', 'diffs/b'), None, 2, 16),
    # ignore case and max_depth 2
    (files('diffs/a', 'diffs/b'), str.lower, 2, 14),
])
def test_listdirs(roots, canonicalize, max_depth, expected, different_dirs):
    result = list_dirs(roots, canonicalize, max_depth)
    l = list(result)
    size = len(l)
    assert size == expected
