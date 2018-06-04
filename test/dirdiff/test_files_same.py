import pytest

from os import path
from meld.dirdiff import _files_same, Different, DodgySame, Same
from .fixture import make


@pytest.fixture
def differnt_dirs():
    make()


def files(*args):
    d = path.dirname(__file__)
    return list(path.join(d, arg) for arg in args)


cmp_args = {
    'shallow-comparison': False,
    'time-resolution': 10000000000,
    'ignore_blank_lines': True,
    'apply-text-filters': True
}

dodgy_args = dict(cmp_args)
dodgy_args['shallow-comparison'] = True


@pytest.mark.parametrize('files, regexes, comparison_args, expected', [
    # empty file list
    (files(), [], cmp_args, Same),
    # dirs are same
    (files('diffs/a', 'diffs/b'), [], cmp_args, Same),
    # dir and file ar diffent
    (files('diffs/a', 'diffs/b/b.txt'), [], cmp_args, Different),
    # shallow equal (time + size)
    (files('diffs/a/d/d.txt', 'diffs/b/d/d.1.txt'), [], dodgy_args, DodgySame),
    # empty files (fastest equal, wont read files)
    (files('diffs/a/c/c.txt', 'diffs/b/c/c.txt'), [], cmp_args, Same),
    # 4.1kb vs 4.1kb file (slow equal, read both until end)
    (files('diffs/a/d/d.txt', 'diffs/b/d/d.txt'), [], cmp_args, Same),
    # 4.1kb vs 4.1kb file (fast different, first chunk diff)
    (files('diffs/a/d/d.txt', 'diffs/b/d/d.1.txt'), [], cmp_args, Different),
    # 4.1kb vs 4.1kb file (slow different, read both until end)
    (files('diffs/a/d/d.txt', 'diffs/b/d/d.2.txt'), [], cmp_args, Different),
    # empty vs 1b file (fast different, first chunk diff)
    (files('diffs/a/e/g/g.txt', 'diffs/b/e/g/g.txt'), [], cmp_args, Different)
])
def test_files_same(files, regexes, comparison_args, expected, differnt_dirs):
    result = _files_same(files, regexes, comparison_args)
    assert result == expected
