from os import listdir, stat
from os.path import sep as SEP, abspath
from functools import partial
from collections import defaultdict, deque
import stat as stat_const

(
    NAME, CANON, PATH, ABS_PATH, PARENT_PATH,
    ROOT, POS, STAT, TYPE, STAT_ERR
) = range(10)


S_IFMT = 0o170000
DIR = stat_const.S_IFDIR
CHR = stat_const.S_IFCHR
BLK = stat_const.S_IFBLK
REG = stat_const.S_IFREG
LNK = stat_const.S_IFLNK
FIFO = stat_const.S_IFIFO
SOCK = stat_const.S_IFSOCK


def file_attrs(
    name, canon=None, path=None, abs_path=None,
    parent_path=None, root=None, stat_err=None, pos=None
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
        # parent path
        parent_path,
        # root
        root,
        # root position
        pos,
        # stat
        stats,
        # type
        stats and (stats.st_mode & S_IFMT) or 0,
        # stat_err
        stat_err
    )


def _dir_err_attr(directory, root, e):
    canon = directory[CANON] + e.strerror
    name = directory[NAME] + e.strerror
    return file_attrs(
        name,
        canon,
        path=directory[PATH],
        abs_path=directory[ABS_PATH],
        root=root,
        stat_err=e,
        pos=directory[POS]
    )


def _list_dir(parents, canonicalize=None, filterer=None):
    # TODO use scandir when min version is 3.5
    files = defaultdict(tuple)
    for node in parents:
        if node[TYPE] != DIR:
            continue

        root = node[ROOT] or node
        try:
            for name in listdir(node[ABS_PATH]):
                canon = canonicalize and canonicalize(name) or name
                if filterer and not filterer(canon):
                    continue

                files[canon] += (
                    file_attrs(
                        name,
                        canon,
                        path=node[PATH] + SEP + name,
                        abs_path=node[ABS_PATH] + SEP + name,
                        parent_path=node[PATH],
                        root=root,
                        pos=node[POS]
                    )
                ,)
        except OSError as e:
            yield node[CANON], (
                _dir_err_attr(node, root, e)
            ,)
    yield from sorted(files.items())


_default_list_dir = partial(_list_dir, canonicalize=None, filterer=None)


def dirs_recursion(parents, fn=_default_list_dir):
    '''
    list all contensts for parents
    use listdirs to start from root

    parents: Iterable[file_attrs] of base dirs

    returns: Iterable[tuple[name, Iterable[file_attrs], Iterable[children]]]

    children signature is same as return
    '''

    for name, files in fn(parents):
        yield name, files, dirs_recursion(files, fn)


def list_dirs(roots, canonicalize=None, filterer=None):
    '''
    list all contensts for roots

    roots: Iterable[str] of base dirs

    returns: Iterable[tuple[name, Iterable[file_attrs], Iterable[children]]]

    children signature is same as return
    '''

    name_path = [
        (pos, f.strip(SEP).split(SEP)[-1], abspath(f))
        for pos, f in enumerate(roots or ())
    ]
    files = [
        file_attrs(
            pos=pos,
            abs_path=abs_path,
            path=name,
            name=name,
            canon=canonicalize and canonicalize(name) or name
        ) for pos, name, abs_path in name_path
    ]

    fn = partial(_list_dir, canonicalize=canonicalize, filterer=filterer)
    yield '', files, dirs_recursion(files, fn)


def flattern_bfs(iterator, max_depth=None, depth=None):
    '''
    Flattern list_dirs using breadth-first search

    iterator: Iterable[tuple[Iterable[file_attrs], Iterable[children]]]
    depth: int of current depth
    max_depth: int of max depth

    returns: Iterable[tuple[depth, name, Iterable[file_attrs]]]
    '''
    depth = depth or 0
    sub_iterator = ()
    for name, files, children in iterator:
        sub_iterator = sub_iterator + (children,)
        yield depth, name, files
    if max_depth != depth:
        for iterator in sub_iterator:
            yield from flattern_bfs(iterator, max_depth, depth + 1)


def flattern(iterator, max_depth=None, depth=None):
    '''
    Flattern list_dirs using depth-first preorder

    iterator: Iterable[tuple[Iterable[file_attrs], Iterable[children]]]
    depth: int of current depth
    name: name o current node
    max_depth: int of max depth

    returns: Iterable[tuple[depth, name, Iterable[file_attrs]]]
    '''
    depth = depth or 0
    for name, files, children in iterator:
        yield depth, name, files
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
        for depth, name, files in flattern_bfs(list_dirs(roots)):
            print(depth, name, files[0][PATH])

    elif 'dirs_recursion' in sys.argv:
        # for 52k files * 2
        # 1.38user 0.54system 0:01.94elapsed 14mb
        for depth, name, files in flattern(list_dirs(roots)):
            print(depth, name, files[0][PATH])
    else:
        # for 0 files
        # 0.02user 0.00system 0:00.03elapsed 97%CPU 8MB
        pass
