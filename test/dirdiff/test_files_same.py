import pytest

from os import path
from meld.dirdiff import _files_same, Different, DodgySame, Same, SameFiltered
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

no_ignore_args = dict(cmp_args)
no_ignore_args['ignore_blank_lines'] = False

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
    (files('diffs/a/e/g/g.txt', 'diffs/b/e/g/g.txt'), [], cmp_args, Different),
    # CRLF vs CRLF with trailing, ignoring blank lines
    (files('diffs/a/crlf.txt', 'diffs/a/crlftrailing.txt'), [], cmp_args, SameFiltered),
    # CRLF vs CRLF with trailing, not ignoring blank lines
    (files('diffs/a/crlf.txt', 'diffs/a/crlftrailing.txt'), [], no_ignore_args, Different),
    # LF vs LF with trailing, ignoring blank lines
    (files('diffs/b/lf.txt', 'diffs/b/lftrailing.txt'), [], cmp_args, SameFiltered),
    # LF vs LF with trailing, not ignoring blank lines
    (files('diffs/b/lf.txt', 'diffs/b/lftrailing.txt'), [], no_ignore_args, Different),
    # CRLF vs LF, ignoring blank lines
    (files('diffs/a/crlf.txt', 'diffs/b/lf.txt'), [], cmp_args, SameFiltered),
    # CRLF vs LF, not ignoring blank lines
    (files('diffs/a/crlf.txt', 'diffs/b/lf.txt'), [], no_ignore_args, Different),
    # CRLF with trailing vs LF with trailing, ignoring blank lines
    (files('diffs/a/crlftrailing.txt', 'diffs/b/lftrailing.txt'), [], cmp_args, SameFiltered),
    # CRLF with trailing vs LF with trailing, not ignoring blank lines
    (files('diffs/a/crlftrailing.txt', 'diffs/b/lftrailing.txt'), [], no_ignore_args, Different),
])
def test_files_same(files, regexes, comparison_args, expected, differnt_dirs):
    result = _files_same(files, regexes, comparison_args)
    assert result == expected
