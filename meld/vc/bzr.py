# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2005 Aaron Bentley <aaron.bentley@utoronto.ca>
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
import re
from collections import defaultdict

from . import _vc


class Vc(_vc.Vc):

    CMD = "bzr"
    CMDARGS = ["--no-aliases", "--no-plugins"]
    NAME = "Bazaar"
    VC_DIR = ".bzr"
    PATCH_INDEX_RE = "^=== modified file '(.*)' (.*)$"
    CONFLICT_RE = "conflict in (.*)$"
    RENAMED_RE = "^(.*) => (.*)$"

    commit_statuses = (
        _vc.STATE_MODIFIED, _vc.STATE_RENAMED, _vc.STATE_NEW, _vc.STATE_REMOVED
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
        "R": _vc.STATE_RENAMED,   # File renamed
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

    state_3_map = {
        " ": None,
        "*": _vc.STATE_MODIFIED,
        "/": _vc.STATE_MODIFIED,
        "@": _vc.STATE_MODIFIED,
    }

    valid_status_re = r'[%s][%s][%s]\s*' % (''.join(state_1_map.keys()),
                                            ''.join(state_2_map.keys()),
                                            ''.join(state_3_map.keys()),)

    def add(self, runner, files):
        fullcmd = [self.CMD] + self.CMDARGS
        command = [fullcmd, 'add']
        runner(command, files, refresh=True, working_dir=self.root)

    def commit(self, runner, files, message):
        fullcmd = [self.CMD] + self.CMDARGS
        command = [fullcmd, 'commit', '-m', message]
        runner(command, [], refresh=True, working_dir=self.root)

    def revert(self, runner, files):
        runner(
            [self.CMD] + self.CMDARGS + ["revert"] + files, [], refresh=True,
            working_dir=self.root)

    def push(self, runner):
        runner(
            [self.CMD] + self.CMDARGS + ["push"], [], refresh=True,
            working_dir=self.root)

    def update(self, runner):
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

    @classmethod
    def valid_repo(cls, path):
        return not _vc.call([cls.CMD, "root"], cwd=path)

    def get_files_to_commit(self, paths):
        files = []
        for p in paths:
            if os.path.isdir(p):
                for path, status in self._tree_cache.items():
                    if status in self.commit_statuses and path.startswith(p):
                        files.append(os.path.relpath(path, self.root))
            else:
                files.append(os.path.relpath(p, self.root))
        return sorted(list(set(files)))

    def _update_tree_state_cache(self, path):
        # FIXME: This actually clears out state information, because the
        # current API doesn't have any state outside of _tree_cache.
        branch_root = _vc.popen(
            [self.CMD] + self.CMDARGS + ["root", path],
            cwd=self.location).read().rstrip('\n')
        entries = []
        while 1:
            try:
                proc = _vc.popen([self.CMD] + self.CMDARGS +
                                 ["status", "-S", "--no-pending", branch_root])
                entries = proc.read().split("\n")[:-1]
                break
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise

        tree_cache = defaultdict(set)
        tree_meta_cache = defaultdict(list)
        self._rename_cache = rename_cache = {}
        self._reverse_rename_cache = {}
        # Files can appear twice in the list if they conflict and were renamed
        # at once.
        for entry in entries:
            meta = []
            old_name = None
            state_string, name = entry[:3], entry[4:].strip()
            if not re.match(self.valid_status_re, state_string):
                continue

            state1 = self.state_1_map.get(state_string[0])
            state2 = self.state_2_map.get(state_string[1])
            state3 = self.state_3_map.get(state_string[2])

            states = {state1, state2, state3} - {None}

            if _vc.STATE_CONFLICT in states:
                real_path_match = re.search(self.CONFLICT_RE, name)
                if real_path_match is not None:
                    name = real_path_match.group(1)

            if _vc.STATE_RENAMED in states:
                real_path_match = re.search(self.RENAMED_RE, name)
                if real_path_match is not None:
                    old_name = real_path_match.group(1)
                    name = real_path_match.group(2)
                    meta.append("%s ➡ %s" % (old_name, name))

            path = os.path.join(branch_root, name)
            if old_name:
                old_path = os.path.join(branch_root, old_name)
                rename_cache[old_path] = path

            if state3 and state3 is _vc.STATE_MODIFIED:
                # line = _vc.popen(self.diff_command() + [path]).readline()
                line = _vc.popen(['bzr', 'diff', path]).readline()
                executable_match = re.search(self.PATCH_INDEX_RE, line)
                if executable_match:
                    meta.append(executable_match.group(2))

            path = path[:-1] if path.endswith('/') else path
            tree_cache[path].update(states)
            tree_meta_cache[path].extend(meta)
            # Bazaar entries will only be REMOVED in the second state column
            self._add_missing_cache_entry(path, state2)

        # Handle any renames now
        for old, new in rename_cache.items():
            if old in tree_cache:
                tree_cache[new].update(tree_cache[old])
                tree_meta_cache[new].extend(tree_meta_cache[old])
                del tree_cache[old]
                del tree_meta_cache[old]
            self._reverse_rename_cache[new] = old

        self._tree_cache.update(
            dict((x, max(y)) for x, y in tree_cache.items()))
        self._tree_meta_cache = dict(tree_meta_cache)

    def get_path_for_repo_file(self, path, commit=None):
        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")

        path = path[len(self.root) + 1:]
        suffix = os.path.splitext(path)[1]

        args = [self.CMD, "cat", path]
        if commit:
            args.append("-r%s" % commit)

        return _vc.call_temp_output(args, cwd=self.root, suffix=suffix)

    def get_path_for_conflict(self, path, conflict):
        if path in self._reverse_rename_cache and not \
                conflict == _vc.CONFLICT_MERGED:
            path = self._reverse_rename_cache[path]
        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")

        # bzr paths are all temporary files
        return "%s%s" % (path, self.conflict_map[conflict]), False
