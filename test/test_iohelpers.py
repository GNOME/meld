
import pytest
from gi.repository import Gio

from meld.iohelpers import find_shared_parent_path


@pytest.mark.parametrize(
    'paths, expected_parent',
    [
        # No paths, None return
        ([], None),
        # One path always returns its own parent
        (['/foo/a/b/c'], '/foo/a/b'),
        # Two paths
        (['/foo/a', '/foo/b'], '/foo'),
        # Three paths
        (['/foo/a', '/foo/b', '/foo/c'], '/foo'),
        # First path is deeper
        (['/foo/a/asd/asd', '/foo/b'], '/foo'),
        # Second path is deeper
        (['/foo/a/', '/foo/b/asd/asd'], '/foo'),
        # Common parent is the root
        (['/foo/a/', '/bar/b/'], '/'),
    ],
)
def test_find_shared_parent_path(paths, expected_parent):
    files = [Gio.File.new_for_path(p) for p in paths]
    print([f.get_path() for f in files])
    parent = find_shared_parent_path(files)

    if parent is None:
        assert expected_parent is None
    else:
        print(f'Parent: {parent.get_path()}; expected {expected_parent}')
        assert parent.equal(Gio.File.new_for_path(expected_parent))
