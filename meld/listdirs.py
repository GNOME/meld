from enum import Enum
from os import listdir, stat
from os.path import sep, abspath
from itertools import chain
import stat as stat_const


class ATTR(int, Enum):
    NAME = 0
    CANON = 1
    PATH = 2
    ABS_PATH = 3
    PARENT_PATH = 4
    ROOT = 5
    STAT = 6
    TYPE = 7
    STAT_ERR = 8
S = ATTR


class TYPE(int, Enum):
    DIR = stat_const.S_IFDIR
    CHR = stat_const.S_IFCHR
    BLK = stat_const.S_IFBLK
    REG = stat_const.S_IFREG
    LNK = stat_const.S_IFLNK
    FIFO = stat_const.S_IFIFO
    SOCK = stat_const.S_IFSOCK


def file_attrs(
    name, canon=None, path=None, abs_path=None,
    parent_path=None, root=None, stat_err=None
):
    '''
    Create a tuple of file infos (
        NAME, CANON, PATH, ABS_PATH, PARENT_PATH,
        ROOT, STAT, EXISTS, TYPE, STAT_ERR
    )

    Why not a named tuple?
    Performance issue until 3.7
    See: https://bugs.python.org/issue28638
    '''
    stats = None
    if not stat_err:
        try:
            stats = stat(abs_path, follow_symlinks=False)
        except OSError as e:
            stat_err = e
    return (
        # path
        name,
        # canon
        canon,
        # path
        path,
        # abs_path
        abs_path,
        # parent path
        parent_path,
        # root
        root,
        # stat
        stats,
        # type
        stats and stat_const.S_IFMT(stats.st_mode),
        # stat_err
        stat_err
    )


def _dir_err_attr(directory, root, e):
    canon = directory[S.CANON] + e.strerror
    name = directory[S.NAME] + e.strerror
    return file_attrs(
        name,
        canon,
        path=directory[S.PATH],
        abs_path=directory[S.ABS_PATH],
        root=root,
        stat_err=e
    )


def _list_dir(parents, canonicalize, filterer=None):
    files = {}
    directories = (p for p in parents if p[S.TYPE] == TYPE.DIR)
    for directory in directories:
        root = directory[S.ROOT] or directory
        names = ()
        try:
            names = filter(filterer, listdir(directory[S.ABS_PATH]))
            for name in names:
                canon = canonicalize and canonicalize(name) or name
                info = file_attrs(
                    name,
                    canon,
                    path=directory[S.PATH] + sep + name,
                    abs_path=directory[S.ABS_PATH] + sep + name,
                    parent_path=directory[S.PATH],
                    root=root
                )
                files[canon] = files.get(canon, ()) + (info,)
        except OSError as e:
            info = _dir_err_attr(directory, root, e)
            files[canon] = files.get(canon, ()) + (info,)
    return files.values()


def _first_canon_key(files):
    return files[0][ATTR.CANON].lower()


def dirs_recursion(parents, canonicalize, filterer=None):
    '''
    list all contensts for parents
    use listdirs to start from root

    parents: Iterable[file_attrs] of base dirs
    canonicalize: function for name standadization
        ie: lambda i: i.lower()
    filterer: function that filters

    returns: Iterable[tuple[Iterable[file_attrs], Iterable[children]]]

    children signature is same as return
    '''

    nodes = sorted(
        _list_dir(parents, canonicalize, filterer),
        key=_first_canon_key
    )

    # list current depth first
    for files in nodes:
        yield files, dirs_recursion(
            files, canonicalize, filterer
        )


def list_dirs(roots, canonicalize=None, filterer=None):
    '''
    list all contensts for roots

    roots: Iterable[str] of base dirs
    canonicalize: function for name standadization
        ie: lambda i: i.lower()
    filterer: function that filters

    returns: Iterable[tuple[Iterable[file_attrs], Iterable[children]]]

    children signature is same as return
    '''

    name_path = [(f.strip(sep).split(sep)[-1], abspath(f)) for f in roots or ()]
    name_path = [
        (name, abs_path)
        for name, abs_path in name_path
        if not filterer or filterer(name)
    ]
    files = [
        file_attrs(
            abs_path=abs_path,
            path=name,
            name=name,
            canon=canonicalize and canonicalize(name) or name
        ) for name, abs_path in name_path
    ]

    # list roots files
    yield files, dirs_recursion(
        files, canonicalize, filterer
    )


def flattern_bfs(iterator, max_depth=None, depth=None):
    '''
    Flattern list_dirs using breadth-first search

    iterator: Iterable[tuple[Iterable[file_attrs], Iterable[children]]]
    depth: int of current depth
    max_depth: int of max depth

    returns: Iterable[tuple[depth, Iterable[file_attrs]]]
    '''
    sub_iterator = ()
    depth = depth or 0
    for files, children in iterator:
        sub_iterator = sub_iterator + (children,)
        yield depth, files
    if max_depth != depth:
        for iterator in sub_iterator:
            yield from flattern_bfs(iterator, max_depth, depth + 1)


def flattern(iterator, max_depth=None, depth=None):
    '''
    Flattern list_dirs using depth-first preorder

    iterator: Iterable[tuple[Iterable[file_attrs], Iterable[children]]]
    depth: int of current depth
    max_depth: int of max depth

    returns: Iterable[tuple[depth, Iterable[file_attrs]]]
    '''
    depth = depth or 0
    for files, children in iterator:
        yield depth, files
        if max_depth != depth:
            yield from flattern(children, max_depth, depth + 1)


if __name__ == '__main__':
    import sys
    roots = [
        '.',
        '.'
    ]
    if 'dirs_recursion_sort' in sys.argv:
        # for 52k files * 2
        # 1.62user 0.57system 0:02.20elapsed 99%CPU 15mb
        for depth, files in flattern_bfs(list_dirs(roots)):
            print(depth, files[0][ATTR.PATH])

    elif 'dirs_recursion' in sys.argv:
        # for 52k files * 2
        # 1.62user 0.57system 0:02.20elapsed 99%CPU 15mb
        for depth, files in flattern(list_dirs(roots)):
            print(depth, files[0][ATTR.PATH])
    else:
        # for 0 files
        # 0.02user 0.00system 0:00.03elapsed 97%CPU 8MB
        pass
