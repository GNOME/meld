# Copyright (C) 2010-2015 Kai Willadsen <kai.willadsen@gmail.com>
# Copyright (C)      2016 Guillaume Hoffmann <guillaumh@gmail.com>
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
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict

from . import _vc


class Vc(_vc.Vc):

    # Requires Darcs version >= 2.10.3
    # TODO implement get_commits_to_push_summary using `darcs push --dry-run`
    # Currently `darcs whatsnew` (as of v2.10.3) does not report conflicts
    # see http://bugs.darcs.net/issue2138

    CMD = "darcs"
    NAME = "Darcs"
    VC_DIR = "_darcs"

    state_map = {
        "a": _vc.STATE_NONE,
        "A": _vc.STATE_NEW,
        "M": _vc.STATE_MODIFIED,
        "M!": _vc.STATE_CONFLICT,
        "R": _vc.STATE_REMOVED,
        "F": _vc.STATE_NONEXIST,  # previous name of file
        "T": _vc.STATE_RENAMED,   # new name of file
    }

    @classmethod
    def is_installed(cls):
        try:
            proc = _vc.popen([cls.CMD, '--version'])
            # check that version >= 2.10.3
            (x, y, z) = proc.read().split(" ", 1)[0].split(".", 2)[:3]
            assert (x, y, z) >= (2, 10, 3)
            return True
        except Exception:
            return False

    def commit(self, runner, files, message):
        command = [self.CMD, 'record', '-a', '-m', message]
        runner(command, [], refresh=True, working_dir=self.root)

    def update(self, runner):
        command = [self.CMD, 'pull', '-a']
        runner(command, [], refresh=True, working_dir=self.root)

    def push(self, runner):
        command = [self.CMD, 'push', '-a']
        runner(command, [], refresh=True, working_dir=self.root)

    def add(self, runner, files):
        command = [self.CMD, 'add', '-r']
        runner(command, files, refresh=True, working_dir=self.root)

    def remove(self, runner, files):
        command = [self.CMD, 'remove', '-r']
        runner(command, files, refresh=True, working_dir=self.root)

    def revert(self, runner, files):
        command = [self.CMD, 'revert', '-a']
        runner(command, files, refresh=True, working_dir=self.root)

    def get_path_for_repo_file(self, path, commit=None):
        if commit is not None:
            raise NotImplementedError()

        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")

        # `darcs show contents` needs the path before rename
        if path in self._reverse_rename_cache:
            path = self._reverse_rename_cache[path]

        path = path[len(self.root) + 1:]
        suffix = os.path.splitext(path)[1]
        process = subprocess.Popen(
            [self.CMD, "show", "contents", path], cwd=self.root,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        with tempfile.NamedTemporaryFile(prefix='meld-tmp',
                                         suffix=suffix, delete=False) as f:
            shutil.copyfileobj(process.stdout, f)
        return f.name

    @classmethod
    def valid_repo(cls, path):
        return not _vc.call([cls.CMD, "show", "repo", "--no-files"], cwd=path)

    def _update_tree_state_cache(self, path):
        # FIXME: currently ignoring 'path' due to darcs's bad
        #        behaviour (= fails) when given "" argument
        """ Update the state of the file(s) at self._tree_cache['path'] """
        while 1:
            try:
                proc = _vc.popen(
                    [self.CMD, "whatsnew", "-sl", "--machine-readable"],
                    cwd=self.location)
                lines = proc.read().split("\n")[:-1]
                break
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise

        # Files can appear twice in the list if were modified and renamed
        # at once. Darcs first show file moves then modifications.
        if len(lines) == 0 and os.path.isfile(path):
            # If we're just updating a single file there's a chance that it
            # was it was previously modified, and now has been edited so that
            # it is un-modified.  This will result in an empty 'entries' list,
            # and self._tree_cache['path'] will still contain stale data.
            # When this corner case occurs we force self._tree_cache['path']
            # to STATE_NORMAL.
            self._tree_cache[path] = _vc.STATE_NORMAL
        else:
            tree_cache = defaultdict(int)
            tree_meta_cache = defaultdict(list)
            self._rename_cache = rename_cache = {}
            self._reverse_rename_cache = {}
            old_name = None
            for line in lines:
                # skip empty lines and line starting with "What's new in foo"
                if (not line.strip()) or line.startswith("What"):
                    continue
                statekey, name = line.split(" ", 1)
                name = os.path.normpath(name)
                if statekey == "F":
                    old_name = name

                path = os.path.join(self.location, name)

                if statekey == "T" and old_name:
                    old_path = os.path.join(self.location, old_name)
                    rename_cache[old_path] = path
                    old_name = None

                state = self.state_map.get(statekey.strip(), _vc.STATE_NONE)
                tree_cache[path] = state

            for old, new in rename_cache.items():
                self._reverse_rename_cache[new] = old
                old_name = old[len(self.root) + 1:]
                new_name = new[len(self.root) + 1:]
                tree_meta_cache[new] = ("%s ➡ %s" % (old_name, new_name))

            self._tree_cache.update(
                dict((x, y) for x, y in tree_cache.items()))
            self._tree_meta_cache = dict(tree_meta_cache)
