# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2015 Kai Willadsen <kai.willadsen@gmail.com>

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

from . import _vc


class Vc(_vc.Vc):

    CMD = "hg"
    NAME = "Mercurial"
    VC_DIR = ".hg"

    state_map = {
        "?": _vc.STATE_NONE,
        "A": _vc.STATE_NEW,
        "C": _vc.STATE_NORMAL,
        "!": _vc.STATE_MISSING,
        "I": _vc.STATE_IGNORED,
        "M": _vc.STATE_MODIFIED,
        "R": _vc.STATE_REMOVED,
    }

    def commit(self, runner, files, message):
        command = [self.CMD, 'commit', '-m', message]
        runner(command, files, refresh=True, working_dir=self.root)

    def update(self, runner):
        command = [self.CMD, 'pull', '-u']
        runner(command, [], refresh=True, working_dir=self.root)

    def add(self, runner, files):
        command = [self.CMD, 'add']
        runner(command, files, refresh=True, working_dir=self.root)

    def remove(self, runner, files):
        command = [self.CMD, 'rm']
        runner(command, files, refresh=True, working_dir=self.root)

    def revert(self, runner, files):
        command = [self.CMD, 'revert']
        runner(command, files, refresh=True, working_dir=self.root)

    @classmethod
    def valid_repo(cls, path):
        return not _vc.call([cls.CMD, "root"], cwd=path)

    def get_path_for_repo_file(self, path, commit=None):
        if commit is not None:
            raise NotImplementedError()

        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")
        path = path[len(self.root) + 1:]

        suffix = os.path.splitext(path)[1]
        args = [self.CMD, "cat", path]
        return _vc.call_temp_output(args, cwd=self.root, suffix=suffix)

    def _update_tree_state_cache(self, path):
        """ Update the state of the file(s) at self._tree_cache['path'] """
        while 1:
            try:
                # Get the status of modified files
                proc = _vc.popen([self.CMD, "status", '-A', path],
                                 cwd=self.location)
                entries = proc.read().split("\n")[:-1]

                # The following command removes duplicate file entries.
                # Just in case.
                entries = list(set(entries))
                break
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise

        if len(entries) == 0 and os.path.isfile(path):
            # If we're just updating a single file there's a chance that it
            # was it was previously modified, and now has been edited so that
            # it is un-modified.  This will result in an empty 'entries' list,
            # and self._tree_cache['path'] will still contain stale data.
            # When this corner case occurs we force self._tree_cache['path']
            # to STATE_NORMAL.
            self._tree_cache[path] = _vc.STATE_NORMAL
        else:
            # There are 1 or more modified files, parse their state
            for entry in entries:
                # we might have a space in file name, it should be ignored
                statekey, name = entry.split(" ", 1)
                path = os.path.join(self.location, name.strip())
                state = self.state_map.get(statekey.strip(), _vc.STATE_NONE)
                self._tree_cache[path] = state
                self._add_missing_cache_entry(path, state)
