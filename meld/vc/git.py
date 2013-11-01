# -*- coding: utf-8 -*-
# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2005 Aaron Bentley <aaron.bentley@utoronto.ca>
# Copyright (C) 2007 José Fonseca <j_r_fonseca@yahoo.co.uk>
# Copyright (C) 2010-2013 Kai Willadsen <kai.willadsen@gmail.com>

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
import shutil
import subprocess
import tempfile

from gettext import gettext as _, ngettext

from . import _vc


class Vc(_vc.CachedVc):

    CMD = "git"
    NAME = "Git"
    VC_DIR = ".git"
    GIT_DIFF_FILES_RE = ":(\d+) (\d+) [a-z0-9]+ [a-z0-9]+ ([XADMTU])\t(.*)"

    VC_COLUMNS = (_vc.DATA_NAME, _vc.DATA_STATE, _vc.DATA_OPTIONS)

    conflict_map = {
        # These are the arguments for git-show
        # CONFLICT_MERGED has no git-show argument unfortunately.
        _vc.CONFLICT_BASE: 1,
        _vc.CONFLICT_LOCAL: 2,
        _vc.CONFLICT_REMOTE: 3,
    }

    state_map = {
        "X": _vc.STATE_NONE,      # Unknown
        "A": _vc.STATE_NEW,       # New
        "D": _vc.STATE_REMOVED,   # Deleted
        "M": _vc.STATE_MODIFIED,  # Modified
        "T": _vc.STATE_MODIFIED,  # Type-changed
        "U": _vc.STATE_CONFLICT,  # Unmerged
    }

    def __init__(self, location):
        super(Vc, self).__init__(location)
        self.diff_re = re.compile(self.GIT_DIFF_FILES_RE)
        self._tree_cache = {}
        self._tree_meta_cache = {}

    def check_repo_root(self, location):
        # Check exists instead of isdir, since .git might be a git-file
        if not os.path.exists(os.path.join(location, self.VC_DIR)):
            raise ValueError
        return location

    def commit_command(self, message):
        return [self.CMD, "commit", "-m", message]

    def add_command(self):
        return [self.CMD, "add"]

    # Prototyping VC interface version 2

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

    def get_commits_to_push_summary(self):
        branch_refs = self.get_commits_to_push()
        unpushed_branches = len([v for v in branch_refs.values() if v])
        unpushed_commits = sum(len(v) for v in branch_refs.values())
        if unpushed_commits:
            if unpushed_branches > 1:
                # Translators: First %s is replaced by translated "%d unpushed
                # commits", second %s is replaced by translated "%d branches"
                label = _("%s in %s") % (
                    ngettext("%d unpushed commit", "%d unpushed commits",
                             unpushed_commits) % unpushed_commits,
                    ngettext("%d branch", "%d branches",
                             unpushed_branches) % unpushed_branches)
            else:
                # Translators: These messages cover the case where there is
                # only one branch, and are not part of another message.
                label = ngettext("%d unpushed commit", "%d unpushed commits",
                                 unpushed_commits) % (unpushed_commits)
        else:
            label = ""
        return label

    def get_commits_to_push(self):
        proc = _vc.popen([self.CMD, "for-each-ref",
                          "--format=%(refname:short) %(upstream:short)",
                          "refs/heads"], cwd=self.location)
        branch_remotes = proc.read().split("\n")[:-1]

        branch_revisions = {}
        for line in branch_remotes:
            try:
                branch, remote = line.split()
            except ValueError:
                continue

            proc = _vc.popen([self.CMD, "rev-list", branch, "^" + remote],
                             cwd=self.location)
            revisions = proc.read().split("\n")[:-1]
            branch_revisions[branch] = revisions
        return branch_revisions

    def get_files_to_commit(self, paths):
        files = []
        for p in paths:
            if os.path.isdir(p):
                entries = self._get_modified_files(p)
                names = [self.diff_re.search(e).groups()[3] for e in entries]
                files.extend(names)
            else:
                files.append(os.path.relpath(p, self.root))
        return sorted(list(set(files)))

    def get_commit_message_prefill(self):
        """This will be inserted into the commit dialog when commit is run"""
        commit_path = os.path.join(self.root, ".git", "MERGE_MSG")
        if os.path.exists(commit_path):
            # If I have to deal with non-ascii, non-UTF8 pregenerated commit
            # messages, I'm taking up pig farming.
            with open(commit_path) as f:
                message = f.read().decode('utf8')
            return "\n".join(
                (l for l in message.splitlines() if not l.startswith("#")))
        return None

    def update(self, runner, files):
        command = [self.CMD, 'pull']
        runner(command, [], refresh=True, working_dir=self.root)

    def push(self, runner):
        command = [self.CMD, 'push']
        runner(command, [], refresh=True, working_dir=self.root)

    def remove(self, runner, files):
        command = [self.CMD, 'rm', '-r']
        runner(command, files, refresh=True, working_dir=self.root)

    def revert(self, runner, files):
        exists = [f for f in files if os.path.exists(f)]
        missing = [f for f in files if not os.path.exists(f)]
        if exists:
            command = [self.CMD, 'checkout']
            runner(command, exists, refresh=True, working_dir=self.root)
        if missing:
            command = [self.CMD, 'checkout', 'HEAD']
            runner(command, missing, refresh=True, working_dir=self.root)

    def get_path_for_conflict(self, path, conflict):
        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")

        if conflict == _vc.CONFLICT_MERGED:
            # Special case: no way to get merged result from git directly
            return path, False

        path = path[len(self.root) + 1:]
        if os.name == "nt":
            path = path.replace("\\", "/")

        args = ["git", "show", ":%s:%s" % (self.conflict_map[conflict], path)]
        process = subprocess.Popen(args,
                                   cwd=self.location, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        vc_file = process.stdout

        # Error handling here involves doing nothing; in most cases, the only
        # sane response is to return an empty temp file.

        prefix = 'meld-tmp-%s-' % _vc.conflicts[conflict]
        with tempfile.NamedTemporaryFile(prefix=prefix, delete=False) as f:
            shutil.copyfileobj(vc_file, f)
        return f.name, True

    def get_path_for_repo_file(self, path, commit=None):
        if commit is None:
            commit = "HEAD"
        else:
            raise NotImplementedError()

        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")
        path = path[len(self.root) + 1:]
        if os.name == "nt":
            path = path.replace("\\", "/")

        obj = commit + ":" + path
        process = subprocess.Popen([self.CMD, "cat-file", "blob", obj],
                                   cwd=self.root, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        vc_file = process.stdout

        # Error handling here involves doing nothing; in most cases, the only
        # sane response is to return an empty temp file.

        with tempfile.NamedTemporaryFile(prefix='meld-tmp', delete=False) as f:
            shutil.copyfileobj(vc_file, f)
        return f.name

    def valid_repo(self):
        # TODO: On Windows, this exit code is wrong under the normal shell; it
        # appears to be correct under the default git bash shell however.
        if _vc.call([self.CMD, "branch"], cwd=self.root):
            return False
        else:
            return True

    def get_working_directory(self, workdir):
        if workdir.startswith("/"):
            return self.root
        else:
            return ''

    def _get_modified_files(self, path):
        # Update the index before getting status, otherwise we could
        # be reading stale status information
        _vc.call([self.CMD, "update-index", "--refresh"],
                 cwd=self.location)

        # Get the status of files that are different in the "index" vs
        # the HEAD of the git repository
        proc = _vc.popen([self.CMD, "diff-index",
                          "--cached", "HEAD", path], cwd=self.location)
        entries = proc.read().split("\n")[:-1]

        # Get the status of files that are different in the "index" vs
        # the files on disk
        proc = _vc.popen([self.CMD, "diff-files",
                          "-0", path], cwd=self.location)
        entries += (proc.read().split("\n")[:-1])

        # An unmerged file or a file that has been modified, added to
        # git's index, then modified again would result in the file
        # showing up in both the output of "diff-files" and
        # "diff-index".  The following command removes duplicate
        # file entries.
        entries = list(set(entries))

        return entries

    def _update_tree_state_cache(self, path, tree_state):
        """ Update the state of the file(s) at tree_state['path'] """
        while 1:
            try:
                entries = self._get_modified_files(path)

                # Identify ignored files
                proc = _vc.popen([self.CMD, "ls-files", "--others",
                                  "--ignored", "--exclude-standard", path],
                                 cwd=self.location)
                ignored_entries = proc.read().split("\n")[:-1]

                # Identify unversioned files
                proc = _vc.popen([self.CMD, "ls-files", "--others",
                                  "--exclude-standard", path],
                                 cwd=self.location)
                unversioned_entries = proc.read().split("\n")[:-1]

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
                columns = self.diff_re.search(entry).groups()
                old_mode, new_mode, statekey, name = columns
                if os.name == 'nt':
                    # Git returns unix-style paths on Windows
                    name = os.path.normpath(name.strip())
                path = os.path.join(self.root, name.strip())
                state = self.state_map.get(statekey.strip(), _vc.STATE_NONE)
                tree_state[path] = state
                if old_mode != new_mode:
                    msg = _("Mode changed from %s to %s" %
                            (old_mode, new_mode))
                    self._tree_meta_cache[path] = msg

            for entry in ignored_entries:
                path = os.path.join(self.location, entry.strip())
                tree_state[path] = _vc.STATE_IGNORED

            for entry in unversioned_entries:
                path = os.path.join(self.location, entry.strip())
                tree_state[path] = _vc.STATE_NONE

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
            meta = self._tree_meta_cache.get(path, "")
            retfiles.append(_vc.File(path, name, state, options=meta))
        for name, path in dirs:
            # git does not operate on dirs, just files
            retdirs.append(_vc.Dir(path, name, _vc.STATE_NORMAL))
        for path, state in tree.items():
            # removed files are not in the filesystem, so must be added here
            if state in (_vc.STATE_REMOVED, _vc.STATE_MISSING):
                folder, name = os.path.split(path)
                if folder == directory:
                    retfiles.append(_vc.File(path, name, state))
        return retdirs, retfiles
