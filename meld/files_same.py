import os
import stat
from collections import namedtuple
from decimal import Decimal
from meld.listdirs import ATTRS

CacheResult = namedtuple('CacheResult', 'stats result')


def all_same(lst):
    """Return True if all elements of the list are equal"""
    return not lst or lst.count(lst[0]) == len(lst)


class StatItem(namedtuple('StatItem', 'mode size time')):
    __slots__ = ()

    @classmethod
    def _make(cls, stat_result):
        return StatItem(stat.S_IFMT(stat_result.st_mode),
                        stat_result.st_size, stat_result.st_mtime)

    def shallow_equal(self, other, time_resolution_ns):
        if self.size != other.size:
            return False

        # Shortcut to avoid expensive Decimal calculations. 2 seconds is our
        # current accuracy threshold (for VFAT), so should be safe for now.
        if abs(self.time - other.time) > 2:
            return False

        dectime1 = Decimal(self.time).scaleb(Decimal(9)).quantize(1)
        dectime2 = Decimal(other.time).scaleb(Decimal(9)).quantize(1)
        mtime1 = dectime1 // time_resolution_ns
        mtime2 = dectime2 // time_resolution_ns

        return mtime1 == mtime2


_cache = {}
Same, SameFiltered, DodgySame, DodgyDifferent, Different, FileError = \
    list(range(6))
# TODO: Get the block size from os.stat
CHUNK_SIZE = 4096

def remove_blank_lines(text):
    splits = text.splitlines()
    lines = text.splitlines(True)
    blanks = set([i for i, l in enumerate(splits) if not l])
    lines = [l for i, l in enumerate(lines) if i not in blanks]
    return b''.join(lines)


def files_same(files, regexes, comparison_args, file_stats=None):
    """Determine whether a list of files are the same.

    Possible results are:
      Same: The files are the same
      SameFiltered: The files are identical only after filtering with 'regexes'
      DodgySame: The files are superficially the same (i.e., type, size, mtime)
      DodgyDifferent: The files are superficially different
      FileError: There was a problem reading one or more of the files
    """


    if all_same(files):
        return Same

    files = tuple(files)
    regexes = tuple(regexes)
    if file_stats:
        stats = tuple([StatItem._make(s) for s in file_stats])
    else:
        stats = tuple([StatItem._make(os.stat(f)) for f in files])

    shallow_comparison = comparison_args['shallow-comparison']
    time_resolution_ns = comparison_args['time-resolution']
    ignore_blank_lines = comparison_args['ignore_blank_lines']

    need_contents = comparison_args['apply-text-filters']

    # If all entries are directories, they are considered to be the same
    if all([stat.S_ISDIR(s.mode) for s in stats]):
        return Same

    # If any entries are not regular files, consider them different
    if not all([stat.S_ISREG(s.mode) for s in stats]):
        return Different

    # Compare files superficially if the options tells us to
    if shallow_comparison:
        all_same_timestamp = all(
            s.shallow_equal(stats[0], time_resolution_ns) for s in stats[1:]
        )
        return DodgySame if all_same_timestamp else Different

    # If there are no text filters, unequal sizes imply a difference
    if not need_contents and not all_same([s.size for s in stats]):
        return Different

    # Check the cache before doing the expensive comparison
    cache_key = (files, need_contents, regexes, ignore_blank_lines)
    cache = _cache.get(cache_key)
    if cache and cache.stats == stats:
        return cache.result

    # Open files and compare bit-by-bit
    contents = [[] for f in files]
    result = None

    try:
        handles = [open(f, "rb") for f in files]
        try:
            data = [h.read(CHUNK_SIZE) for h in handles]

            # Rough test to see whether files are binary. If files are guessed
            # to be binary, we don't examine contents for speed and space.
            if any(b"\0" in d for d in data):
                need_contents = False

            while True:
                if all_same(data):
                    if not data[0]:
                        break
                else:
                    result = Different
                    if not need_contents:
                        break

                if need_contents:
                    for i in range(len(data)):
                        contents[i].append(data[i])

                data = [h.read(CHUNK_SIZE) for h in handles]

        # Files are too large; we can't apply filters
        except (MemoryError, OverflowError):
            result = DodgySame if all_same(stats) else DodgyDifferent
        finally:
            for h in handles:
                h.close()
    except IOError:
        # Don't cache generic errors as results
        return FileError

    if result is None:
        result = Same

    if result == Different and need_contents:
        contents = [b"".join(c) for c in contents]
        # For probable text files, discard newline differences to match
        # file comparisons.
        contents = [b"\n".join(c.splitlines()) for c in contents]

        #contents = [misc.apply_text_filters(c, regexes) for c in contents]

        if ignore_blank_lines:
            contents = [remove_blank_lines(c) for c in contents]
        result = SameFiltered if all_same(contents) else Different

    _cache[cache_key] = CacheResult(stats, result)
    return result


def branch_content_is_same(branch_path, files, regexes, comparison_args):
    existing_files = [f for f in files if f[ATTRS.stat]]
    files_paths = [f[ATTRS.abs_path] for f in existing_files]
    files_stats = [f[ATTRS.stat] for f in existing_files]
    print(files_paths)
    state = files_same(files_paths, regexes, comparison_args, files_stats)
    return (branch_path, files, state)