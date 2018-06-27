import stat as stat_const
from os import listdir, stat
from os.path import sep as SEP, abspath
from functools import partial
from collections import ChainMap, defaultdict


class ATTRS(object):
    name = 0
    canon = 1
    path = 2
    abs_path = 3
    parent_path = 4
    root = 5
    pos = 6
    stat = 7
    type = 8
    stat_err = 9

s = ATTRS


DIR = stat_const.S_IFDIR
CHR = stat_const.S_IFCHR
BLK = stat_const.S_IFBLK
REG = stat_const.S_IFREG
LNK = stat_const.S_IFLNK
FIFO = stat_const.S_IFIFO
SOCK = stat_const.S_IFSOCK
S_IFMT = 0o170000


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
    if abs_path and not stat_err:
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
    canon = directory[s.canon] + e.strerror
    name = directory[s.name] + e.strerror
    return file_attrs(
        name,
        canon,
        path=directory[s.path],
        abs_path=directory[s.abs_path],
        root=root,
        stat_err=e,
        pos=directory[s.pos]
    )


def _list_dir(parents, canonicalize=None, filterer=None):
    # TODO use scandir when min version is 3.5
    files = defaultdict(tuple)
    for node in parents:
        if node[s.type] != DIR:
            continue

        root = node[s.root] or node
        try:
            for name in listdir(node[s.abs_path]):
                canon = canonicalize and canonicalize(name) or name
                if filterer and not filterer(canon):
                    continue

                files[canon] += (
                    file_attrs(
                        name,
                        canon,
                        path=node[s.path] + SEP + name,
                        abs_path=node[s.abs_path] + SEP + name,
                        parent_path=node[s.path],
                        root=root,
                        pos=node[s.pos]
                    )
                ,)
        except OSError as e:
            yield node[s.canon], (
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
        for pos, f in enumerate(roots or ()) if f
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


def flattern_bfs(orphans, max_depth=None, depth=0):
    '''
    Flattern list_dirs using breadth-first search

    orphans: Iterable[Iterable[tuple[Iterable[file_attrs], Iterable[children]]]]
    depth: int of current depth
    max_depth: int of max depth

    returns: Iterable[tuple[depth, name, Iterable[file_attrs]]]
    '''
    orphans_children = ()
    for iterator in orphans:
        for name, files, children in iterator:
            yield depth, name, files, None
            orphans_children += (children,)
    if orphans_children:
        yield from flattern_bfs(orphans_children, max_depth, depth + 1)


def flattern(iterator, max_depth=None, parents=None, depth=None):
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
        yield depth, name, files, parents
        if max_depth != depth:
            yield from flattern(children, max_depth, files, depth + 1)


def fil_empty_spaces(trunks, branchs):
    base = branchs[0]
    name = base[ATTRS.canon]
    current = { f[ATTRS.pos]: f for f in branchs }
    return {
        t[ATTRS.pos]: current.get(
            t[ATTRS.pos],
            file_attrs(
                name,
                name,
                root=t,
                pos=t[ATTRS.pos]
            )
        )
        for t in trunks if t
    }


def dirs_first(iterator):
    after = ()
    for item in iterator:
        if item[1][0][ATTRS.type] == DIR:
            yield item
        else:
            after += (item,)
    yield from after


if __name__ == '__main__':
    import sys
    # roots = [
    #     '.',
    #     '.'
    # ]
    roots = [
        '../netlify-cms',
        '../netlify-cms-again'
    ]
    if 'dirs_recursion_sort' in sys.argv:
        # for 52k files * 2
        # 1.62user 0.57system 0:02.20elapsed 99%CPU 15mb
        for depth, name, files, parent in flattern_bfs((list_dirs(roots),)):
            print(depth, name, files[0][s.path])

    elif 'dirs_recursion' in sys.argv:
        # for 52k files * 2
        # 1.38user 0.54system 0:01.94elapsed 14mb
        for depth, name, files, parent in flattern(list_dirs(roots)):
            print(depth, name, files[0][s.path])
    else:
        # for 0 files
        # 0.02user 0.00system 0:00.03elapsed 97%CPU 8MB
        pass


__all__ = [
    'ATTRS', 'dirs_recursion', 'flattern', 'flattern_bfs', 'list_dirs',
    'fil_empty_spaces', 'dirs_first',
    'DIR', 'CHR', 'BLK', 'REG', 'LNK', 'FIFO', 'SOCK', 'S_IFMT']
