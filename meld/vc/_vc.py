# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010, 2012-2015 Kai Willadsen <kai.willadsen@gmail.com>

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
# OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import collections
import itertools
import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import ClassVar

from gi.repository import Gio, GLib

from meld.conf import _
from meld.misc import get_hide_window_startupinfo

log = logging.getLogger(__name__)

# ignored, new, normal, ignored changes,
# error, placeholder, vc added
# vc modified, vc renamed, vc conflict, vc removed
# locally removed, end
(STATE_IGNORED, STATE_NONE, STATE_NORMAL, STATE_NOCHANGE,
    STATE_ERROR, STATE_EMPTY, STATE_NEW,
    STATE_MODIFIED, STATE_RENAMED, STATE_CONFLICT, STATE_REMOVED,
    STATE_MISSING, STATE_NONEXIST, STATE_SPINNER, STATE_MAX) = list(range(15))

# VC conflict types
(CONFLICT_MERGED, CONFLICT_BASE, CONFLICT_LOCAL,
    CONFLICT_REMOTE, CONFLICT_MAX) = list(range(5))
# These names are used by BZR, and are logically identical.
CONFLICT_OTHER = CONFLICT_REMOTE
CONFLICT_THIS = CONFLICT_LOCAL

conflicts = [_("Merged"), _("Base"), _("Local"), _("Remote")]
assert len(conflicts) == CONFLICT_MAX


# Lifted from the itertools recipes section
def partition(pred, iterable):
    t1, t2 = itertools.tee(iterable)
    return (list(itertools.ifilterfalse(pred, t1)),
            list(itertools.ifilter(pred, t2)))


class Entry:
    # These are labels for possible states of version controlled files;
    # not all states have a label to avoid visual clutter.
    state_names = {
        STATE_IGNORED: _("Ignored"),
        STATE_NONE: _("Unversioned"),
        STATE_NORMAL: "",
        STATE_NOCHANGE: "",
        STATE_ERROR: _("Error"),
        STATE_EMPTY: "",
        STATE_NEW: _("Newly added"),
        STATE_MODIFIED: _("Modified"),
        STATE_RENAMED: _("Renamed"),
        STATE_CONFLICT: "<b>%s</b>" % _("Conflict"),
        STATE_REMOVED: _("Removed"),
        STATE_MISSING: _("Missing"),
        STATE_NONEXIST: _("Not present"),
        STATE_SPINNER: _("Scanning…"),
    }

    def __init__(self, path, name, state, isdir, options=None):
        self.path = path
        self.name = name
        self.state = state
        self.isdir = isdir
        if isinstance(options, list):
            options = ','.join(options)
        self.options = options

    def __str__(self):
        return "<%s:%s %s>" % (self.__class__.__name__, self.path,
                               self.get_status() or "Normal")

    def __repr__(self):
        return "%s(%r, %r, %r)" % (self.__class__.__name__, self.name,
                                   self.path, self.state)

    def get_status(self):
        return self.state_names[self.state]

    def is_present(self):
        """Should this Entry actually be present on the file system"""
        return self.state not in (STATE_REMOVED, STATE_MISSING)

    @staticmethod
    def is_modified(entry):
        return entry.state >= STATE_NEW or (
            entry.isdir and (entry.state > STATE_NONE))

    @staticmethod
    def is_normal(entry):
        return entry.state == STATE_NORMAL

    @staticmethod
    def is_nonvc(entry):
        return entry.state == STATE_NONE or (
            entry.isdir and (entry.state > STATE_IGNORED))

    @staticmethod
    def is_ignored(entry):
        return entry.state == STATE_IGNORED or entry.isdir


class Vc:

    VC_DIR: ClassVar[str]

    #: Whether to walk the current location's parents to find a
    #: repository root. Only used in legacy version control systems
    #: (e.g., old SVN, CVS, RCS).
    VC_ROOT_WALK: ClassVar[bool] = True

    def __init__(self, path):
        # Save the requested comparison location. The location may be a
        # sub-directory of the repository we are diffing and can be useful in
        # limiting meld's output to the requested location.
        #
        # If the location requested is a file (e.g., a single-file command line
        # comparison) then the location is set to the containing directory.
        self.root, self.location = self.is_in_repo(path)
        if not self.root:
            raise ValueError
        self._tree_cache = {}
        self._tree_meta_cache = {}
        self._tree_missing_cache = collections.defaultdict(set)

    def run(self, *args, use_locale_encoding=True):
        """Return subprocess running VC with `args` at VC's location

        For example, `git_vc.run('log', '-p')` will run `git log -p`
        and return the subprocess object.

        If use_locale_encoding is True, the return value is a unicode
        text stream with universal newlines. If use_locale_encoding is
        False, the return value is a binary stream.

        Note that this runs at the *location*, not at the *root*.
        """
        cmd = (self.CMD,) + args
        return subprocess.Popen(
            cmd, cwd=self.location, stdout=subprocess.PIPE,
            universal_newlines=use_locale_encoding,
            startupinfo=get_hide_window_startupinfo(),
        )

    def get_files_to_commit(self, paths):
        """Get a list of files that will be committed from paths

        paths is a list of paths under the version control system root,
        which may include directories. The return value must be a list
        of file paths that would actually be committed given the path
        argument; specifically this should exclude unchanged files and
        recursively list files in directories.
        """
        raise NotImplementedError()

    def get_commit_message_prefill(self):
        """Get a version-control defined pre-filled commit message

        This will return a unicode message in situations where the
        version control system has a (possibly partial) pre-filled
        message, or None if no such message exists.

        This method should use pre-filled commit messages wherever
        provided by the version control system, most commonly these are
        given in merging, revert or cherry-picking scenarios.
        """
        return None

    def get_commits_to_push_summary(self):
        """Return a one-line readable description of unpushed commits

        This provides a one-line description of what would be pushed by the
        version control's push action, e.g., "2 unpushed commits in 3
        branches". Version control systems that always only push the current
        branch should not show branch information.
        """
        raise NotImplementedError()

    def get_valid_actions(self, path_states):
        """Get the set of valid actions for paths with version states

        path_states is a list of (path, state) tuples describing paths
        in the version control system. This will return all valid
        version control actions that could reasonably be taken on *all*
        of the paths in path_states.

        If an individual plugin needs special handling, or doesn't
        implement all standard actions, this should be overridden.
        """
        valid_actions = set()
        states = path_states.values()

        if bool(path_states):
            valid_actions.add('compare')
        valid_actions.add('update')
        # TODO: We can't do this; this shells out for each selection change...
        # if bool(self.get_commits_to_push()):
        valid_actions.add('push')

        non_removeable_states = (STATE_NONE, STATE_IGNORED, STATE_REMOVED)
        non_revertable_states = (STATE_NONE, STATE_NORMAL, STATE_IGNORED)

        # TODO: We can't disable this for NORMAL, because folders don't
        # inherit any state from their children, but committing a folder with
        # modified children is expected behaviour.
        if all(s not in (STATE_NONE, STATE_IGNORED) for s in states):
            valid_actions.add('commit')
        if all(s not in (STATE_NORMAL, STATE_REMOVED) for s in states):
            valid_actions.add('add')
        if all(s == STATE_CONFLICT for s in states):
            valid_actions.add('resolve')
        if (all(s not in non_removeable_states for s in states) and
                self.root not in path_states.keys()):
            valid_actions.add('remove')
        if all(s not in non_revertable_states for s in states):
            valid_actions.add('revert')
        return valid_actions

    def get_path_for_repo_file(self, path, commit=None):
        """Returns a file path for the repository path at commit

        If *commit* is given, the path returned will point to a copy of
        the file at *path* at the given commit, as interpreted by the
        VCS. If *commit* is **None**, the current revision is used.

        Even if the VCS maintains an on-disk copy of the given path, a
        temp file with file-at-commit content must be created and its
        path returned, to avoid destructive editing. The VCS plugin
        must **not** delete temp files it creates.
        """
        raise NotImplementedError()

    def get_path_for_conflict(self, path, conflict):
        """Returns a file path for the conflicted repository path

        *conflict* is the side of the conflict to be retrieved, and
        must be one of the CONFLICT_* constants.
        """
        raise NotImplementedError()

    def refresh_vc_state(self, path=None):
        """Update cached version control state

        If a path is provided, for example when a file has been modified
        and saved in the file comparison view and needs its state
        refreshed, then only that path will be updated.

        If no path is provided then the version control tree rooted at
        its `location` will be recursively refreshed.
        """
        if path is None:
            self._tree_cache = {}
            self._tree_missing_cache = collections.defaultdict(set)
            path = './'
        self._update_tree_state_cache(path)

    def get_entries(self, base):
        parent = Gio.File.new_for_path(base)
        try:
            enumerator = parent.enumerate_children(
                'standard::name,standard::display-name,standard::type',
                Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
                None,
            )
        except GLib.Error as err:
            if err.matches(
                Gio.io_error_quark(),
                Gio.IOErrorEnum.PERMISSION_DENIED
            ):
                log.error(f"Failed to scan folder {base!r}; permission denied")
                return
            raise

        for file_info in enumerator:
            if file_info.get_name() == self.VC_DIR:
                continue
            gfile = enumerator.get_child(file_info)

            path = gfile.get_path()
            name = file_info.get_display_name()
            state = self._tree_cache.get(path, STATE_NORMAL)
            meta = self._tree_meta_cache.get(path, "")
            isdir = file_info.get_file_type() == Gio.FileType.DIRECTORY
            yield Entry(path, name, state, isdir, options=meta)

        # Removed entries are not in the filesystem, so must be added here
        for name in self._tree_missing_cache[base]:
            path = os.path.join(base, name)
            state = self._tree_cache.get(path, STATE_NORMAL)
            # TODO: Ideally we'd know whether this was a folder
            # or a file. Since it's gone however, only the VC
            # knows, and may or may not tell us.
            meta = self._tree_meta_cache.get(path, "")
            yield Entry(path, name, state, isdir=False, options=meta)

    def _add_missing_cache_entry(self, path, state):
        if state in (STATE_REMOVED, STATE_MISSING):
            folder, name = os.path.split(path)
            self._tree_missing_cache[folder].add(name)

    def get_entry(self, path):
        """Return the entry associated with the given path in this VC

        If the given path does not correspond to an entry in the VC,
        this method returns an Entry with the appropriate REMOVED or
        MISSING state.
        """
        gfile = Gio.File.new_for_path(path)
        try:
            file_info = gfile.query_info(
                'standard::*', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
            name = file_info.get_display_name()
            isdir = file_info.get_file_type() == Gio.FileType.DIRECTORY
        except GLib.Error as e:
            if e.domain != 'g-io-error-quark':
                raise
            # Handling for non-existent files (or other IO errors)
            name = path
            isdir = False

        path = gfile.get_path()
        state = self._tree_cache.get(path, STATE_NORMAL)
        meta = self._tree_meta_cache.get(path, "")

        return Entry(path, name, state, isdir, options=meta)

    @classmethod
    def is_installed(cls):
        try:
            call([cls.CMD])
            return True
        except Exception:
            return False

    @classmethod
    def is_in_repo(cls, path):
        root = None
        location = path if os.path.isdir(path) else os.path.dirname(path)

        if cls.VC_ROOT_WALK:
            root = cls.find_repo_root(location)
        elif cls.check_repo_root(location):
            root = location
        return root, location

    @classmethod
    def check_repo_root(cls, location):
        return os.path.isdir(os.path.join(location, cls.VC_DIR))

    @classmethod
    def find_repo_root(cls, location):
        while location:
            if cls.check_repo_root(location):
                return location

            location, old = os.path.dirname(location), location
            if location == old:
                break

    @classmethod
    def valid_repo(cls, path):
        """Determine if a directory is a valid repository for this class"""
        raise NotImplementedError


class InvalidVCPath(ValueError):
    """Raised when a VC module is passed an invalid (or not present) path."""

    def __init__(self, vc, path, err):
        self.vc = vc
        self.path = path
        self.error = err

    def __str__(self):
        return "%s: Path %s is invalid or not present\nError: %s\n" % \
            (self.vc.NAME, self.path, self.error)


class InvalidVCRevision(ValueError):
    """Raised when a VC module is passed a revision spec it can't handle."""

    def __init__(self, vc, rev, err):
        self.vc = vc
        self.revision = rev
        self.error = err

    def __str__(self):
        return "%s: Doesn't understand or have revision %s\nError: %s\n" % \
            (self.vc.NAME, self.revision, self.error)


def popen(cmd, cwd=None, use_locale_encoding=True):
    """Return the stdout output of a given command as a stream.

    If use_locale_encoding is True, the output is parsed to unicode
    text stream with universal newlines.
    If use_locale_encoding is False output is treated as binary stream.
    """

    process = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE,
        universal_newlines=use_locale_encoding,
        startupinfo=get_hide_window_startupinfo(),
    )
    return process.stdout


def call_temp_output(cmd, cwd, file_id='', suffix=None):
    """Call `cmd` in `cwd` and write the output to a temporary file

    This returns the name of the temporary file used. It is the
    caller's responsibility to delete this file.

    If `file_id` is provided, it is used as part of the
    temporary file's name, for ease of identification.

    If `suffix` is provided, it is used as the extension
    of the temporary file's name.
    """
    process = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        startupinfo=get_hide_window_startupinfo(),
    )
    vc_file = process.stdout

    # Error handling here involves doing nothing; in most cases, the only
    # sane response is to return an empty temp file.

    prefix = 'meld-tmp' + ('-' + file_id if file_id else '')
    with tempfile.NamedTemporaryFile(prefix=prefix,
                                     suffix=suffix, delete=False) as f:
        shutil.copyfileobj(vc_file, f)
    return f.name


# Return the return value of a given command
def call(cmd, cwd=None):
    devnull = open(os.devnull, "wb")
    return subprocess.call(
        cmd, cwd=cwd, stdout=devnull, stderr=devnull,
        startupinfo=get_hide_window_startupinfo(),
    )


base_re = re.compile(
    br"^<{7}.*?$\r?\n(?P<local>.*?)"
    br"^\|{7}.*?$\r?\n(?P<base>.*?)"
    br"^={7}.*?$\r?\n(?P<remote>.*?)"
    br"^>{7}.*?$\r?\n", flags=re.DOTALL | re.MULTILINE)


def base_from_diff3(merged):
    return base_re.sub(br"==== BASE ====\n\g<base>==== BASE ====\n", merged)
