from unittest import mock

import pytest
from gi.repository import Gio

from meld.iohelpers import (
    find_shared_parent_path,
    format_home_relative_path,
    format_parent_relative_path,
)


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
        # One path, one missing path
        (['/foo/a', None], None),
        # Two paths, one missing path
        (['/foo/a', None, '/foo/c'], None),
    ],
)
def test_find_shared_parent_path(paths, expected_parent):
    files = [Gio.File.new_for_path(p) if p else None for p in paths]
    print([f.get_path() if f else repr(f) for f in files])
    parent = find_shared_parent_path(files)

    if parent is None:
        assert expected_parent is None
    else:
        print(f'Parent: {parent.get_path()}; expected {expected_parent}')
        if expected_parent is None:
            assert parent is None
        else:
            assert parent.equal(Gio.File.new_for_path(expected_parent))


@pytest.mark.parametrize(
    "path, expected_format",
    [
        ("/home/hey/foo", "~/foo"),
        ("/home/hmph/foo", "/home/hmph/foo"),
    ]
)
def test_format_home_relative_path(path, expected_format):

    with mock.patch(
        "meld.iohelpers.GLib.get_home_dir",
        return_value="/home/hey/",
    ):
        gfile = Gio.File.new_for_path(path)
        assert format_home_relative_path(gfile) == expected_format


@pytest.mark.parametrize(
    'parent, child, expected_label',
    [
        # Child is a direct child of parent
        (
            '/home/hey/',
            '/home/hey/foo.txt',
            '…/hey/foo.txt',
        ),
        # Child is a direct child of parent and parent is the root
        (
            '/',
            '/foo.txt',
            '/foo.txt',
        ),
        # Child is a 2-depth child of parent
        (
            '/home/hey/',
            '/home/hey/project/foo.txt',
            '…/project/foo.txt',
        ),
        # Child is a 3-depth child of parent
        (
            '/home/hey/',
            '/home/hey/project/package/foo.txt',
            '…/project/package/foo.txt',
        ),
        # Child is a more-than-3-depth child of parent, with long
        # immediate parent
        (
            '/home/hey/',
            '/home/hey/project/package/subpackage/foo.txt',
            '…/project/…/subpackage/foo.txt',
        ),
        # Child is a more-than-3-depth child of parent, with short
        # immediate parent
        (
            '/home/hey/',
            '/home/hey/project/package/src/foo.txt',
            '…/project/package/src/foo.txt',
        ),
    ],
)
def test_format_parent_relative_path(
    parent: str,
    child: str,
    expected_label: str,
):
    parent_gfile = Gio.File.new_for_path(parent)
    child_gfile = Gio.File.new_for_path(child)

    label = format_parent_relative_path(parent_gfile, child_gfile)

    assert label == expected_label


def test_format_parent_relative_path_no_parent():
    parent_gfile = Gio.File.new_for_path('/')
    child_gfile = Gio.File.new_for_path('/')

    with pytest.raises(ValueError, match='has no parent'):
        format_parent_relative_path(parent_gfile, child_gfile)
