from enum import Enum
from os import path

import pytest

DiffResult = Enum(
    "DiffResult", "Same SameFiltered DodgySame DodgyDifferent Different FileError"
)


def abspath(*args):
    d = path.dirname(__file__)
    return list(path.join(d, arg) for arg in args)


cmp_args = {
    "shallow-comparison": False,
    "time-resolution": 10000000000,
    "ignore_blank_lines": True,
    "apply-text-filters": True,
}

no_ignore_args = dict(cmp_args)
no_ignore_args["ignore_blank_lines"] = False
no_ignore_args["apply-text-filters"] = False

dodgy_args = dict(cmp_args)
dodgy_args["shallow-comparison"] = True


@pytest.mark.parametrize(
    "files, regexes, comparison_args, expected",
    [
        # empty file list
        ((), [], cmp_args, DiffResult.Same),
        # dirs are same
        (("a", "b"), [], cmp_args, DiffResult.Same),
        # dir and file are different
        (("a", "b/b.txt"), [], cmp_args, DiffResult.Different),
        # shallow equal (time + size)
        (("a/d/d.txt", "b/d/d.1.txt"), [], dodgy_args, DiffResult.DodgySame),
        # empty files (fastest equal, won't read files)
        (("a/c/c.txt", "b/c/c.txt"), [], cmp_args, DiffResult.Same),
        # 4.1kb vs 4.1kb file (slow equal, read both until end)
        (("a/d/d.txt", "b/d/d.txt"), [], cmp_args, DiffResult.Same),
        # 4.1kb vs 4.1kb file (fast different, first chunk diff)
        (("a/d/d.txt", "b/d/d.1.txt"), [], cmp_args, DiffResult.Different),
        # 4.1kb vs 4.1kb file (slow different, read both until end)
        (("a/d/d.txt", "b/d/d.2.txt"), [], cmp_args, DiffResult.Different),
        # empty vs 1b file (fast different, first chunk diff)
        (("a/e/g/g.txt", "b/e/g/g.txt"), [], cmp_args, DiffResult.Different),
        # CRLF vs CRLF with trailing, ignoring blank lines
        (("a/crlf.txt", "a/crlftrailing.txt"), [], cmp_args, DiffResult.SameFiltered),
        # CRLF vs CRLF with trailing, not ignoring blank lines
        (
            ("a/crlf.txt", "a/crlftrailing.txt"),
            [],
            no_ignore_args,
            DiffResult.Different,
        ),
        # LF vs LF with trailing, ignoring blank lines
        (("b/lf.txt", "b/lftrailing.txt"), [], cmp_args, DiffResult.SameFiltered),
        # LF vs LF with trailing, not ignoring blank lines
        (("b/lf.txt", "b/lftrailing.txt"), [], no_ignore_args, DiffResult.Different),
        # CRLF vs LF, ignoring blank lines
        (("a/crlf.txt", "b/lf.txt"), [], cmp_args, DiffResult.SameFiltered),
        # CRLF vs LF, not ignoring blank lines
        (("a/crlf.txt", "b/lf.txt"), [], no_ignore_args, DiffResult.Different),
        # CRLF with trailing vs LF with trailing, ignoring blank lines
        (
            ("a/crlftrailing.txt", "b/lftrailing.txt"),
            [],
            cmp_args,
            DiffResult.SameFiltered,
        ),
        # CRLF with trailing vs LF with trailing, not ignoring blank lines
        (
            ("a/crlftrailing.txt", "b/lftrailing.txt"),
            [],
            no_ignore_args,
            DiffResult.Different,
        ),
    ],
)
def test_files_same(create_sample_dir, files, regexes, comparison_args, expected):
    from meld.dirdiff import _files_same

    files_path = [create_sample_dir / f for f in files]
    result = _files_same(files_path, regexes, comparison_args)
    actual = DiffResult(result + 1)
    assert actual == expected
