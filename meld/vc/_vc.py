# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010, 2012-2013 Kai Willadsen <kai.willadsen@gmail.com>

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

import itertools
import os
import re
import subprocess
from gettext import gettext as _

# ignored, new, normal, ignored changes,
# error, placeholder, vc added
# vc modified, vc conflict, vc removed
# locally removed, end
(STATE_IGNORED, STATE_NONE, STATE_NORMAL, STATE_NOCHANGE,
    STATE_ERROR, STATE_EMPTY, STATE_NEW,
    STATE_MODIFIED, STATE_CONFLICT, STATE_REMOVED,
    STATE_MISSING, STATE_NONEXIST, STATE_MAX) = list(range(13))

# VC conflict types
(CONFLICT_MERGED, CONFLICT_BASE, CONFLICT_LOCAL,
    CONFLICT_REMOTE, CONFLICT_MAX) = list(range(5))
# These names are used by BZR, and are logically identical.
CONFLICT_OTHER = CONFLICT_REMOTE
CONFLICT_THIS = CONFLICT_LOCAL

conflicts = [_("Merged"), _("Base"), _("Local"), _("Remote")]
assert len(conflicts) == CONFLICT_MAX

DATA_NAME, DATA_STATE, DATA_REVISION, DATA_OPTIONS = list(range(4))


# Lifted from the itertools recipes section
def partition(pred, iterable):
    t1, t2 = itertools.tee(iterable)
    return (list(itertools.ifilterfalse(pred, t1)),
            list(itertools.ifilter(pred, t2)))


class Entry(object):
    # These are the possible states of files. Be sure to get the colons correct.
    states = _("Ignored:Unversioned:::Error::Newly added:Modified:Conflict:Removed:Missing:Not present").split(":")
    states[STATE_CONFLICT] = "<b>%s</b>" % states[STATE_CONFLICT]
    assert len(states) == STATE_MAX

    def __init__(self, path, name, state):
        self.path = path
        self.state = state
        self.parent, self.name = os.path.split(path.rstrip("/"))

    def __str__(self):
        return "<%s:%s %s>" % (self.__class__.__name__, self.path,
                               self.get_status() or "Normal")

    def __repr__(self):
        return "%s(%r, %r, %r)" % (self.__class__.__name__, self.name,
                                   self.path, self.state)

    def get_status(self):
        return self.states[self.state]


class Dir(Entry):
    def __init__(self, path, name, state):
        Entry.__init__(self, path, name, state)
        self.isdir = 1
        self.rev = ""
        self.options = ""


class File(Entry):
    def __init__(self, path, name, state, rev="", options=""):
        assert path[-1] != "/"
        Entry.__init__(self, path, name, state)
        self.isdir = 0
        self.rev = rev
        self.options = options


class Vc(object):

    VC_DIR = None
    VC_ROOT_WALK = True
    VC_METADATA = None

    VC_COLUMNS = (DATA_NAME, DATA_STATE)

    def __init__(self, location):
        # Save the requested comparison location. The location may be a
        # sub-directory of the repository we are diffing and can be useful in
        # limiting meld's output to the requested location.
        #
        # If the location requested is a file (e.g., a single-file command line
        # comparison) then the location is set to the containing directory.
        if not os.path.isdir(location):
            location = os.path.dirname(location)
        self.location = location

        if self.VC_ROOT_WALK:
            self.root = self.find_repo_root(self.location)
        else:
            self.root = self.check_repo_root(self.location)

    def commit_command(self, message):
        raise NotImplementedError()

    def update_command(self):
        raise NotImplementedError()

    def add_command(self):
        raise NotImplementedError()

    def remove_command(self, force=0):
        raise NotImplementedError()

    def revert_command(self):
        raise NotImplementedError()

    def resolved_command(self):
        raise NotImplementedError()

    # Prototyping VC interface version 2

    def get_files_to_commit(self, paths):
        raise NotImplementedError()

    def get_commit_message_prefill(self):
        return None

    def update(self, runner, files):
        raise NotImplementedError()

    def push(self, runner):
        raise NotImplementedError()

    def revert(self, runner, files):
        raise NotImplementedError()
    
    def get_commits_to_push_summary(self):
        raise NotImplementedError()

    def remove(self, runner, files):
        raise NotImplementedError()

    def resolve(self, runner, files):
        raise NotImplementedError()

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

    def check_repo_root(self, location):
        if not os.path.isdir(os.path.join(location, self.VC_DIR)):
            raise ValueError
        return location

    def find_repo_root(self, location):
        while True:
            try:
                return self.check_repo_root(location)
            except ValueError:
                pass
            tmp = os.path.dirname(location)
            if tmp == location:
                break
            location = tmp
        raise ValueError()

    def get_working_directory(self, workdir):
        return workdir

    def cache_inventory(self, topdir):
        pass

    def uncache_inventory(self):
        pass

    def update_file_state(self, path):
        """ Update the state of a specific file.  For example after a file
        has been modified and saved, its state may be out of date and require
        updating.  This can be implemented for Vc plugins that cache file
        states, eg 'git' an 'bzr' so that the top-level file status is always
        accurate.
        """
        pass

    # Determine if a directory is a valid git/svn/hg/cvs/etc repository
    def valid_repo(self):
        return True

    def listdir(self, path="."):
        try:
            entries = sorted(e for e in os.listdir(path) if e != self.VC_DIR)
        except OSError:
            entries = []
        full_entries = [(f, os.path.join(path, f)) for f in entries]
        cfiles, cdirs = partition(lambda e: os.path.isdir(e[1]), full_entries)
        dirs, files = self.lookup_files(cdirs, cfiles, path)
        return dirs + files

    def lookup_files(self, dirs, files, directory=None):
        # Assumes that all files are in the same directory. files is an array
        # of (name, path) tuples.
        if len(dirs):
            directory = os.path.dirname(dirs[0][1])
        elif len(files):
            directory = os.path.dirname(files[0][1])
        return self._get_dirsandfiles(directory, dirs, files)

    def _get_dirsandfiles(self, directory, dirs, files):
        raise NotImplementedError()

    def get_entry(self, path):
        """Return the entry associated with the given path in this VC

        If the given path does not correspond to any entry in the VC, this
        method returns return None.
        """
        vc_files = [
            x for x in
            self.lookup_files(
                [], [(os.path.basename(path), path)])[1]
            if x.path == path
        ]
        if not vc_files:
            return None
        return vc_files[0]


class CachedVc(Vc):

    def __init__(self, location):
        super(CachedVc, self).__init__(location)
        self._tree_cache = None

    def cache_inventory(self, directory):
        self._tree_cache = self._lookup_tree_cache(directory)

    def uncache_inventory(self):
        self._tree_cache = None

    def _lookup_tree_cache(self, directory):
        raise NotImplementedError()

    def _get_tree_cache(self, directory):
        if self._tree_cache is None:
            self.cache_inventory(directory)
        return self._tree_cache


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


# Return the stdout output of a given command
def popen(cmd, cwd=None):
    return subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE).stdout


# Return the return value of a given command
def call(cmd, cwd=None):
    NULL = open(os.devnull, "wb")
    return subprocess.call(cmd, cwd=cwd, stdout=NULL, stderr=NULL)
