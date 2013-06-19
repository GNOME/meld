### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2005 Aaron Bentley <aaron.bentley@utoronto.ca>

### Redistribution and use in source and binary forms, with or without
### modification, are permitted provided that the following conditions
### are met:
### 
### 1. Redistributions of source code must retain the above copyright
###    notice, this list of conditions and the following disclaimer.
### 2. Redistributions in binary form must reproduce the above copyright
###    notice, this list of conditions and the following disclaimer in the
###    documentation and/or other materials provided with the distribution.

### THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
### IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
### OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
### IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
### INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
### NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
### DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
### THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
### (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
### THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import errno
import os
import re
import shutil
import subprocess
import tempfile

from . import _vc


class Vc(_vc.CachedVc):

    CMD = "bzr"
    CMDARGS = ["--no-aliases", "--no-plugins"]
    NAME = "Bazaar"
    VC_DIR = ".bzr"
    CONFLICT_RE = "conflict in (.*)$"

    commit_statuses = (
        _vc.STATE_MODIFIED, _vc.STATE_NEW, _vc.STATE_REMOVED
    )

    conflict_map = {
        _vc.CONFLICT_BASE: '.BASE',
        _vc.CONFLICT_OTHER: '.OTHER',
        _vc.CONFLICT_THIS: '.THIS',
        _vc.CONFLICT_MERGED: '',
    }

    # We use None here to indicate flags that we don't deal with or care about
    state_1_map = {
        " ": None,                # First status column empty
        "+": None,                # File versioned
        "-": None,                # File unversioned
        "R": None,                # File renamed
        "?": _vc.STATE_NONE,      # File unknown
        "X": None,                # File nonexistent (and unknown to bzr)
        "C": _vc.STATE_CONFLICT,  # File has conflicts
        "P": None,                # Entry for a pending merge (not a file)
    }

    state_2_map = {
        " ": _vc.STATE_NORMAL,    # Second status column empty
        "N": _vc.STATE_NEW,       # File created
        "D": _vc.STATE_REMOVED,   # File deleted
        "K": None,                # File kind changed
        "M": _vc.STATE_MODIFIED,  # File modified
    }

    valid_status_re = r'[%s][%s][\*\s]\s*' % (''.join(state_1_map.keys()),
                                              ''.join(state_2_map.keys()))

    def commit_command(self, message):
        return [self.CMD] + self.CMDARGS + ["commit", "-m", message]

    def add_command(self):
        return [self.CMD] + self.CMDARGS + ["add"]

    def revert(self, runner, files):
        runner(
            [self.CMD] + self.CMDARGS + ["revert"] + files, [], refresh=True,
            working_dir=self.root)

    def push(self, runner):
        runner(
            [self.CMD] + self.CMDARGS + ["push"], [], refresh=True,
            working_dir=self.root)

    def update(self, runner, files):
        # TODO: Handle checkouts/bound branches by calling
        # update instead of pull. For now we've replicated existing
        # functionality, as update will not work for unbound branches.
        runner(
            [self.CMD] + self.CMDARGS + ["pull"], [], refresh=True,
            working_dir=self.root)

    def resolve(self, runner, files):
        runner(
            [self.CMD] + self.CMDARGS + ["resolve"] + files, [], refresh=True,
            working_dir=self.root)

    def remove(self, runner, files):
        runner(
            [self.CMD] + self.CMDARGS + ["rm"] + files, [], refresh=True,
            working_dir=self.root)

    def valid_repo(self):
        if _vc.call([self.CMD, "root"], cwd=self.root):
            return False
        else:
            return True

    def get_working_directory(self, workdir):
        return self.root

    def get_files_to_commit(self, paths):
        files = []
        for p in paths:
            if os.path.isdir(p):
                entries = self._lookup_tree_cache(p)
                names = [
                    x for x, y in entries.items() if y in self.commit_statuses]
                files.extend(names)
            else:
                files.append(os.path.relpath(p, self.root))
        return sorted(list(set(files)))

    def _lookup_tree_cache(self, rootdir):
        branch_root = _vc.popen(
            [self.CMD] + self.CMDARGS + ["root", rootdir]).read().rstrip('\n')
        while 1:
            try:
                proc = _vc.popen([self.CMD] + self.CMDARGS +
                                 ["status", "-S", "--no-pending", branch_root])
                entries = proc.read().split("\n")[:-1]
                break
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise

        tree_state = {}
        for entry in entries:
            state_string, name = entry[:3], entry[4:].strip()
            if not re.match(self.valid_status_re, state_string):
                continue
            # TODO: We don't do anything with exec bit changes.
            state = self.state_1_map.get(state_string[0], None)
            if state is None:
                state = self.state_2_map.get(state_string[1], _vc.STATE_NORMAL)
            elif state == _vc.STATE_CONFLICT:
                real_path_match = re.search(self.CONFLICT_RE, name)
                if real_path_match is None:
                    continue
                name = real_path_match.group(1)

            path = os.path.join(branch_root, name)
            tree_state[path] = state

        return tree_state

    def _get_dirsandfiles(self, directory, dirs, files):
        tree = self._get_tree_cache(directory)

        retfiles = []
        retdirs = []
        bzrfiles = {}
        for path, state in tree.items():
            mydir, name = os.path.split(path)
            if path.endswith('/'):
                mydir, name = os.path.split(mydir)
            if mydir != directory:
                continue
            if path.endswith('/'):
                retdirs.append(_vc.Dir(path[:-1], name, state))
            else:
                retfiles.append(_vc.File(path, name, state))
            bzrfiles[name] = 1
        for f, path in files:
            if f not in bzrfiles:
                state = _vc.STATE_NORMAL
                retfiles.append(_vc.File(path, f, state))
        for d, path in dirs:
            if d not in bzrfiles:
                state = _vc.STATE_NORMAL
                retdirs.append(_vc.Dir(path, d, state))
        return retdirs, retfiles

    def get_path_for_repo_file(self, path, commit=None):
        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")

        path = path[len(self.root) + 1:]

        args = [self.CMD, "cat", path]
        if commit:
            args.append("-r%s" % commit)

        process = subprocess.Popen(args,
                                   cwd=self.root, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        vc_file = process.stdout

        # Error handling here involves doing nothing; in most cases, the only
        # sane response is to return an empty temp file.

        with tempfile.NamedTemporaryFile(prefix='meld-tmp', delete=False) as f:
            shutil.copyfileobj(vc_file, f)
        return f.name

    def get_path_for_conflict(self, path, conflict):
        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")

        # bzr paths are all temporary files
        return "%s%s" % (path, self.conflict_map[conflict]), False

    # Sensitivity button mappings.
    def update_actions_for_paths(self, path_states, actions):
        states = path_states.values()

        actions["VcCompare"] = bool(path_states)
        # TODO: We can't disable this for NORMAL, because folders don't
        # inherit any state from their children, but committing a folder with
        # modified children is expected behaviour.
        actions["VcCommit"] = all(s not in (
            _vc.STATE_NONE, _vc.STATE_IGNORED) for s in states)

        actions["VcUpdate"] = True
        # TODO: We can't do this; this shells out for each selection change...
        # actions["VcPush"] = bool(self.get_commits_to_push())
        actions["VcPush"] = True

        actions["VcAdd"] = all(s not in (
            _vc.STATE_NORMAL, _vc.STATE_REMOVED) for s in states)
        actions["VcResolved"] = all(s == _vc.STATE_CONFLICT for s in states)
        actions["VcRemove"] = (all(s not in (
            _vc.STATE_NONE, _vc.STATE_IGNORED,
            _vc.STATE_REMOVED) for s in states) and
            self.root not in path_states.keys())
        actions["VcRevert"] = all(s not in (
            _vc.STATE_NONE, _vc.STATE_NORMAL,
            _vc.STATE_IGNORED) for s in states)
