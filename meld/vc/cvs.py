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
import shutil

from . import _vc


class Vc(_vc.Vc):

    # CVSNT is a drop-in replacement for CVS; if found, it is used instead
    CMD = "cvsnt" if shutil.which("cvsnt") else "cvs"
    NAME = "CVS"
    VC_DIR = "CVS"
    VC_ROOT_WALK = False

    # According to the output of the 'status' command
    state_map = {
        "Unknown":          _vc.STATE_NONE,
        "Locally Added":    _vc.STATE_NEW,
        "Up-to-date":       _vc.STATE_NORMAL,
        "!":                _vc.STATE_MISSING,
        "I":                _vc.STATE_IGNORED,
        "Locally Modified": _vc.STATE_MODIFIED,
        "Locally Removed":  _vc.STATE_REMOVED,
    }

    def commit(self, runner, files, message):
        command = [self.CMD, 'commit', '-m', message]
        runner(command, files, refresh=True, working_dir=self.root)

    def update(self, runner):
        command = [self.CMD, 'update']
        runner(command, [], refresh=True, working_dir=self.root)

    def add(self, runner, afiles):
        # CVS needs to add files together with all the parents
        # (if those are Unversioned yet)
        relfiles = [
            os.path.relpath(s, self.root)
            for s in afiles if os.path.isfile(s)
        ]
        command = [self.CMD, 'add']

        relargs = []
        for f1 in relfiles:
            positions = [i for i, ch in enumerate(f1 + os.sep) if ch == os.sep]
            arg1 = [f1[:pos] for pos in positions]
            relargs += arg1

        absargs = [os.path.join(self.root, a1) for a1 in relargs]
        runner(command, absargs, refresh=True, working_dir=self.root)

    def remove(self, runner, files):
        command = [self.CMD, 'remove', '-f']
        runner(command, files, refresh=True, working_dir=self.root)

    def revert(self, runner, files):
        command = [self.CMD, 'update', '-C']
        runner(command, files, refresh=True, working_dir=self.root)

    @classmethod
    def valid_repo(cls, path):
        return not _vc.call([cls.CMD, 'ls'], cwd=path)

    def get_path_for_repo_file(self, path, commit=None):
        if commit is not None:
            raise NotImplementedError()

        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")
        path = path[len(self.root) + 1:]

        suffix = os.path.splitext(path)[1]
        args = [self.CMD, "-q", "update", "-p", path]
        return _vc.call_temp_output(args, cwd=self.root, suffix=suffix)

    def _find_files(self, path):
        relfiles = []
        loc = os.path.join(self.location, path)
        for step in os.walk(loc):
            if not step[0].endswith(self.VC_DIR):
                ff = [os.path.join(step[0], f1) for f1 in step[2]]
                relfiles += [os.path.relpath(ff1, loc) for ff1 in ff]
        return relfiles

    def _update_tree_state_cache(self, path):
        """ Update the state of the file(s) at self._tree_cache['path'] """
        while 1:
            try:
                # Get the status of files

                path_isdir = os.path.isdir(path)
                files = self._find_files(path) if path_isdir else [path]

                # Should suppress stderr here
                proc = _vc.popen(
                    [self.CMD, "-Q", "status"] + files,
                    cwd=self.location,
                )
                entries = [
                    li for li in proc.read().splitlines()
                    if li.startswith('File:')
                ]
                break
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise

        if len(entries) == 0 and os.path.isfile(path):
            # If we're just updating a single file there's a chance that
            # it was previously modified, and now has been edited so that
            # it is un-modified.  This will result in an empty 'entries' list,
            # and self._tree_cache['path'] will still contain stale data.
            # When this corner case occurs we force self._tree_cache['path']
            # to STATE_NORMAL.
            self._tree_cache[path] = _vc.STATE_NORMAL
        else:
            # There are 1 or more [modified] files, parse their state
            for entry in zip(files, entries):
                statekey = entry[1].split(':')[-1].strip()
                name = entry[0].strip()

                if os.path.basename(name) not in entry[1]:
                    # ? The short filename got from
                    # 'cvs -Q status <path/file>' does not match <file>
                    raise

                path = os.path.join(self.location, name)
                state = self.state_map.get(statekey, _vc.STATE_NONE)
                self._tree_cache[path] = state
                self._add_missing_cache_entry(path, state)

        """
        # Setting the state of dirs also might be relevant, but not sure
        # Heuristic to find out the state ('CVS' subdir exists or not)
        for entry in zip(dirs, [os.path.isdir(os.path.join(d1, self.VC_DIR))
                                for d1 in dirs]):
            path = os.path.join(self.location, entry[0])
            state = _vc.STATE_NORMAL if entry[1] else _vc.STATE_NONE
            self._tree_cache[path] = state
            self._add_missing_cache_entry(path, state)
        """
