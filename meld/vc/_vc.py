# -*- coding: utf-8 -*-
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
import subprocess

from gi.repository import Gio

from meld.conf import _

# ignored, new, normal, ignored changes,
# error, placeholder, vc added
# vc modified, vc renamed, vc conflict, vc removed
# locally removed, end
(STATE_IGNORED, STATE_NONE, STATE_NORMAL, STATE_NOCHANGE,
    STATE_ERROR, STATE_EMPTY, STATE_NEW,
    STATE_MODIFIED, STATE_RENAMED, STATE_CONFLICT, STATE_REMOVED,
    STATE_MISSING, STATE_NONEXIST, STATE_MAX) = list(range(14))

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


class Entry(object):
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
    }

    def __init__(self, path, name, state, isdir, options=None):
        self.path = path
        self.state = state
        self.parent, self.name = os.path.split(path.rstrip("/"))
        self.isdir = isdir
        self.options = options

    def __str__(self):
        return "<%s:%s %s>" % (self.__class__.__name__, self.path,
                               self.get_status() or "Normal")

    def __repr__(self):
        return "%s(%r, %r, %r)" % (self.__class__.__name__, self.name,
                                   self.path, self.state)

    def get_status(self):
        return self.state_names[self.state]


class Vc(object):

    VC_DIR = None
    VC_ROOT_WALK = True
    VC_METADATA = None

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

    def add(self, runner, files):
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

    def get_working_directory(self, workdir):
        return workdir

    def _get_tree_cache(self):
        if not self._tree_cache:
            self._update_tree_state_cache("./")
        return self._tree_cache

    def update_file_state(self, path):
        """Update the cached version control state of the given path.

        After a file has been modified and saved, for example by
        editing in the file comparison view, its state may be out of
        date and require updating. The method updates the version
        control object's internal cache of file state.
        """
        self._update_tree_state_cache(path)

    def listdir(self, path):
        parent = Gio.File.new_for_path(path)
        enumerator = parent.enumerate_children(
            'standard::*', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)

        entries = []
        for file_info in enumerator:
            if file_info.get_name() == self.VC_DIR:
                continue
            gfile = enumerator.get_child(file_info)
            entries.append((gfile, file_info))

        return self.lookup_files(entries, path)

    def lookup_files(self, files, base):
        # All dirs and files must be direct children of same directory.
        # dirs and files are lists of (name, path) tuples.
        tree = self._get_tree_cache()
        meta_tree = self._tree_meta_cache

        def make_entry(gfile, file_info):
            path = gfile.get_path()
            name = file_info.get_display_name()
            state = tree.get(path, STATE_NORMAL)
            meta = meta_tree.get(path, "")
            isdir = file_info.get_file_type() == Gio.FileType.DIRECTORY
            if isinstance(meta, list):
                meta = ','.join(meta)
            return Entry(path, name, state, isdir, options=meta)

        retfiles = [make_entry(gfile, file_info) for gfile, file_info in files]

        # Removed entries are not in the filesystem, so must be added here
        for path, state in tree.items():
            if state in (STATE_REMOVED, STATE_MISSING):
                folder, name = os.path.split(path)
                if folder == base:
                    # TODO: Ideally we'd know whether this was a folder
                    # or a file. Since it's gone however, only the VC
                    # knows, and may or may not tell us.
                    entry = make_entry(name, path, Gio.FileType.UNKNOWN)
                    retfiles.append(entry)

        return retfiles

    def get_entry(self, path):
        """Return the entry associated with the given path in this VC

        If the given path does not correspond to any entry in the VC, this
        method returns return None.
        """
        gfile = Gio.File.new_for_path(path)
        info = gfile.query_info(
            'standard::*', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
        parent = gfile.get_parent().get_path()

        vc_files = self.lookup_files((gfile, info), parent)
        vc_file = [x for x in vc_files if x.path == path]
        if not vc_file:
            return None
        return vc_file[0]

    @classmethod
    def is_installed(cls):
        try:
            call([cls.CMD])
            return True
        except:
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


# Return the stdout output of a given command
def popen(cmd, cwd=None):
    return subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE).stdout


# Return the return value of a given command
def call(cmd, cwd=None):
    NULL = open(os.devnull, "wb")
    return subprocess.call(cmd, cwd=cwd, stdout=NULL, stderr=NULL)
