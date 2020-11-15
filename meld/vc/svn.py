# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2011-2013, 2015 Kai Willadsen <kai.willadsen@gmail.com>

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

import errno
import glob
import os
import xml.etree.ElementTree as ElementTree

from meld.conf import _
from . import _vc

#: Simple enum constants for differentiating conflict cases.
CONFLICT_TYPE_MERGE, CONFLICT_TYPE_UPDATE = 1, 2


class Vc(_vc.Vc):

    CMD = "svn"
    NAME = "Subversion"
    VC_DIR = ".svn"

    state_map = {
        "unversioned": _vc.STATE_NONE,
        "added": _vc.STATE_NEW,
        "normal": _vc.STATE_NORMAL,
        "missing": _vc.STATE_MISSING,
        "ignored": _vc.STATE_IGNORED,
        "modified": _vc.STATE_MODIFIED,
        "deleted": _vc.STATE_REMOVED,
        "conflicted": _vc.STATE_CONFLICT,
    }

    def commit(self, runner, files, message):
        command = [self.CMD, 'commit', '-m', message]
        runner(command, files, refresh=True, working_dir=self.root)

    def update(self, runner):
        command = [self.CMD, 'update']
        runner(command, [], refresh=True, working_dir=self.root)

    def remove(self, runner, files):
        command = [self.CMD, 'rm', '--force']
        runner(command, files, refresh=True, working_dir=self.root)

    def revert(self, runner, files):
        command = [self.CMD, 'revert']
        runner(command, files, refresh=True, working_dir=self.root)

    def resolve(self, runner, files):
        command = [self.CMD, 'resolve', '--accept=working']
        runner(command, files, refresh=True, working_dir=self.root)

    def get_path_for_repo_file(self, path, commit=None):
        if commit is None:
            commit = "BASE"
        else:
            raise NotImplementedError()

        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")
        path = path[len(self.root) + 1:]

        suffix = os.path.splitext(path)[1]
        args = [self.CMD, "cat", "-r", commit, path]
        return _vc.call_temp_output(args, cwd=self.root, suffix=suffix)

    def get_path_for_conflict(self, path, conflict=None):
        """
        SVN has two types of conflicts:
        Merge conflicts, which give 3 files:
           .left.r* (THIS)
           .working (BASE... although this is a bit debatable)
           .right.r* (OTHER)
        Update conflicts which give 3 files:
           .mine (THIS)
           .r* (lower - BASE)
           .r* (higher - OTHER)
        """
        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")

        # If this is merged, we just return the merged output
        if conflict == _vc.CONFLICT_MERGED:
            return path, False

        # First fine what type of conflict this is by looking at the base
        # we can possibly return straight away!
        conflict_type = None
        base = glob.glob('%s.working' % path)
        if len(base) == 1:
            # We have a merge conflict
            conflict_type = CONFLICT_TYPE_MERGE
        else:
            base = glob.glob('%s.mine' % path)
            if len(base) == 1:
                # We have an update conflict
                conflict_type = CONFLICT_TYPE_UPDATE

        if conflict_type is None:
            raise _vc.InvalidVCPath(self, path, "No known conflict type found")

        if conflict == _vc.CONFLICT_BASE:
            return base[0], False
        elif conflict == _vc.CONFLICT_THIS:
            if conflict_type == CONFLICT_TYPE_MERGE:
                return glob.glob('%s.merge-left.r*' % path)[0], False
            else:
                return glob.glob('%s.r*' % path)[0], False
        elif conflict == _vc.CONFLICT_OTHER:
            if conflict_type == CONFLICT_TYPE_MERGE:
                return glob.glob('%s.merge-right.r*' % path)[0], False
            else:
                return glob.glob('%s.r*' % path)[-1], False

        raise KeyError("Conflict file does not exist")

    def add(self, runner, files):
        # SVN < 1.7 needs to add folders from their immediate parent
        dirs = [s for s in files if os.path.isdir(s)]
        files = [s for s in files if os.path.isfile(s)]
        command = [self.CMD, 'add']
        for path in dirs:
            runner(command, [path], refresh=True,
                   working_dir=os.path.dirname(path))
        if files:
            runner(command, files, refresh=True, working_dir=self.location)

    @classmethod
    def _repo_version_support(cls, version):
        return version >= 12

    @classmethod
    def valid_repo(cls, path):
        if _vc.call([cls.CMD, "info"], cwd=path):
            return False

        root, location = cls.is_in_repo(path)
        vc_dir = os.path.join(root, cls.VC_DIR)

        # Check for repository version, trusting format file then entries file
        repo_version = None
        for filename in ("format", "entries"):
            path = os.path.join(vc_dir, filename)
            if os.path.exists(path):
                with open(path) as f:
                    repo_version = int(f.readline().strip())
                break

        if not repo_version and os.path.exists(os.path.join(vc_dir, "wc.db")):
            repo_version = 12

        return cls._repo_version_support(repo_version)

    def _update_tree_state_cache(self, path):
        while 1:
            try:
                # "svn --xml" outputs utf8, even with Windows non-utf8 locale
                proc = _vc.popen(
                    [self.CMD, "status", "-v", "--xml", path],
                    cwd=self.location, use_locale_encoding=False)
                tree = ElementTree.parse(proc)
                break
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise

        for target in tree.findall("target") + tree.findall("changelist"):
            for entry in target.iter(tag="entry"):
                path = entry.attrib["path"]
                if not path:
                    continue
                if not os.path.isabs(path):
                    path = os.path.abspath(os.path.join(self.location, path))
                for status in entry.iter(tag="wc-status"):
                    item = status.attrib["item"]
                    if item == "":
                        continue
                    state = self.state_map.get(item, _vc.STATE_NONE)
                    self._tree_cache[path] = state

                    rev = status.attrib.get("revision")
                    rev_label = _("Rev %s") % rev if rev is not None else ''
                    self._tree_meta_cache[path] = rev_label
                    self._add_missing_cache_entry(path, state)
