from enum import Enum
from os import listdir, stat
from os.path import sep, abspath
import stat as stat_const


class ATTR(int, Enum):
    NAME = 0
    CANON = 1
    PATH = 2
    ABS_PATH = 3
    ROOT = 4
    STAT = 5
    TYPE = 6
    STAT_ERR = 7
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
    name, canon=None, path=None, abs_path=None, root=None, stat_err=None
):
    '''
    Create a tuple of file infos
    (NAME, CANON, PATH, ABS_PATH, ROOT, STAT, EXISTS, TYPE, STAT_ERR)

    Why not a named tuple?
    Performance issue until 3.7
    See: https://bugs.python.org/issue28638
    '''
    stats = None
    if not stat_err:
        try:
            stats = stat(abs_path)
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
        # root
        root,
        # stat
        stats,
        # type
        stats and stat_const.S_IFMT(stats.st_mode),
        # stat_err
        stat_err
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
                    root=root
                )
                files[canon] = files.get(canon, ()) + (info,)
        except OSError as e:
            canon = directory[S.CANON] + ' OsError'
            name = directory[S.NAME] + ' OsError'
            info = file_attrs(
                name,
                canon,
                path=directory[S.PATH],
                abs_path=directory[S.ABS_PATH],
                root=root,
                stat_err=e
            )
            files[canon] = files.get(canon, ()) + (info,)
    return files.values()


def _first_canon_key(files):
    return files[0][ATTR.CANON].lower()


def dirs_recursion(
    parents, canonicalize, filterer=None, max_depth=None, depth=0
):
    '''
    list all contensts for parents
    use listdirs to start from root

    parents: Iterable[file_attrs] of base dirs
    canonicalize: function for name standadization
        ie: lambda i: i.lower()
    filterer: function that filters
    max_depth: int of max depth
    depth: int of current depth

    returns iterable(depth, Iterable[file_attrs])
    '''

    depth += 1
    if max_depth is not None and max_depth < depth:
        return

    files = sorted(
        _list_dir(parents, canonicalize, filterer),
        key=_first_canon_key
    )

    # list current depth first
    for f in files:
        yield depth, f

    # list next depth
    for items in files:
        yield from dirs_recursion(
            items, canonicalize, filterer, max_depth, depth
        )


def list_dirs(roots, canonicalize=None, filterer=None, max_depth=None):
    '''
    list all contensts for roots

    roots: Iterable[str] of base dirs
    canonicalize: function for name standadization
        ie: lambda i: i.lower()
    filterer: function that filters
    max_depth: int of max depth

    retuns iterable(depth, Iterable[file_attrs])
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
    depth = 0

    # list roots files
    yield depth, files

    # list subitems
    yield from dirs_recursion(files, canonicalize, filterer, max_depth, depth)


if __name__ == '__main__':
    import sys
    roots = [
        '.',
        '.'
    ]
    if 'dirs_recursion_sort' in sys.argv:
        # for 52k files * 2
        # 1.62user 0.57system 0:02.20elapsed 99%CPU 15mb
        for depth, files in list_dirs(roots):
            print(depth, files[0][ATTR.PATH])
    elif 'dirs_recursion_lower' in sys.argv:
        # for 52k files * 2
        # 1.62user 0.57system 0:02.20elapsed 99%CPU 15mb
        for depth, files in list_dirs(roots, lambda x: x.upper()):
            print(depth, files[0][ATTR.CANON])
    else:
        # for 0 files
        # 0.02user 0.00system 0:00.03elapsed 97%CPU 8MB
        pass
