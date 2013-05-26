# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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

from . import _vc


class Vc(_vc.CachedVc):

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

    def commit_command(self, message):
        return [self.CMD, "commit", "-m", message]

    def update_command(self):
        return [self.CMD, "update"]

    def add_command(self):
        return [self.CMD, "add"]

    def remove_command(self, force=0):
        return [self.CMD, "rm"]

    def revert_command(self):
        return [self.CMD, "revert"]

    def valid_repo(self):
        if _vc.call([self.CMD, "root"], cwd=self.root):
            return False
        else:
            return True

    def get_working_directory(self, workdir):
        if workdir.startswith("/"):
            return self.root
        else:
            return ''

    def get_path_for_repo_file(self, path, commit=None):
        if commit is not None:
            raise NotImplementedError()

        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")
        path = path[len(self.root) + 1:]

        process = subprocess.Popen([self.CMD, "cat", path], cwd=self.root,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)

        with tempfile.NamedTemporaryFile(prefix='meld-tmp', delete=False) as f:
            shutil.copyfileobj(process.stdout, f)
        return f.name

    def _update_tree_state_cache(self, path, tree_state):
        """ Update the state of the file(s) at tree_state['path'] """
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
            # was it was previously modified, and now has been edited
            # so that it is un-modified.  This will result in an empty
            # 'entries' list, and tree_state['path'] will still contain stale
            # data.  When this corner case occurs we force tree_state['path']
            # to STATE_NORMAL.
            tree_state[path] = _vc.STATE_NORMAL
        else:
            # There are 1 or more modified files, parse their state
            for entry in entries:
                # we might have a space in file name, it should be ignored
                statekey, name = entry.split(" ", 1)
                path = os.path.join(self.location, name.strip())
                state = self.state_map.get(statekey.strip(), _vc.STATE_NONE)
                tree_state[path] = state

    def _lookup_tree_cache(self, rootdir):
        # Get a list of all files in rootdir, as well as their status
        tree_state = {}
        self._update_tree_state_cache("./", tree_state)

        return tree_state

    def update_file_state(self, path):
        tree_state = self._get_tree_cache(os.path.dirname(path))
        self._update_tree_state_cache(path, tree_state)

    def _get_dirsandfiles(self, directory, dirs, files):

        tree = self._get_tree_cache(directory)

        retfiles = []
        retdirs = []
        for name, path in files:
            state = tree.get(path, _vc.STATE_NORMAL)
            retfiles.append(_vc.File(path, name, state))
        for name, path in dirs:
            # mercurial does not operate on dirs, just files
            retdirs.append(_vc.Dir(path, name, _vc.STATE_NORMAL))
        for path, state in tree.items():
            # removed files are not in the filesystem, so must be added here
            if state in (_vc.STATE_REMOVED, _vc.STATE_MISSING):
                folder, name = os.path.split(path)
                if folder == directory:
                    retfiles.append(_vc.File(path, name, state))
        return retdirs, retfiles
