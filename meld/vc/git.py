# -*- coding: utf-8 -*- 

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:

### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2005 Aaron Bentley <aaron.bentley@utoronto.ca>
### Copyright (C) 2007 José Fonseca <j_r_fonseca@yahoo.co.uk>
### Copyright (C) 2010-2012 Kai Willadsen <kai.willadsen@gmail.com>

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

from . import _vc


class Vc(_vc.CachedVc):

    CMD = "git"
    NAME = "Git"
    VC_DIR = ".git"
    PATCH_STRIP_NUM = 1
    PATCH_INDEX_RE = "^diff --git [ac]/(.*) [bw]/.*$"
    GIT_DIFF_FILES_RE = ":(\d+) (\d+) [a-z0-9]+ [a-z0-9]+ ([ADMU])\t(.*)"

    state_map = {
        "X": _vc.STATE_NONE,     # Unknown
        "A": _vc.STATE_NEW,      # New
        "D": _vc.STATE_REMOVED,  # Deleted
        "M": _vc.STATE_MODIFIED, # Modified
        "T": _vc.STATE_MODIFIED, # Type-changed
        "U": _vc.STATE_CONFLICT, # Unmerged
    }

    def __init__(self, location):
        super(Vc, self).__init__(location)
        self.diff_re = re.compile(self.GIT_DIFF_FILES_RE)
        self._tree_meta_cache = {}

    def check_repo_root(self, location):
        # Check exists instead of isdir, since .git might be a git-file
        if not os.path.exists(os.path.join(location, self.VC_DIR)):
            raise ValueError
        return location

    def commit_command(self, message):
        return [self.CMD,"commit","-m",message]
    def diff_command(self):
        return [self.CMD, "diff", "--relative", "HEAD"]
    def update_command(self):
        return [self.CMD,"pull"]
    def add_command(self):
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm"]
    def revert_command(self):
        return [self.CMD,"checkout"]
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

    def _update_tree_state_cache(self, path, tree_state):
        """ Update the state of the file(s) at tree_state['path'] """
        while 1:
            try:
                # Update the index before getting status, otherwise we could
                # be reading stale status information
                _vc.popen(["git", "update-index", "--refresh"],
                          cwd=self.location)

                # Get the status of files that are different in the "index" vs
                # the HEAD of the git repository
                proc = _vc.popen([self.CMD, "diff-index", \
                    "--cached", "HEAD", path], cwd=self.location)
                entries = proc.read().split("\n")[:-1]

                # Get the status of files that are different in the "index" vs
                # the files on disk
                proc = _vc.popen([self.CMD, "diff-files", \
                    "-0", path], cwd=self.location)
                entries += (proc.read().split("\n")[:-1])

                # Identify ignored files
                proc = _vc.popen([self.CMD, "ls-files", "--others", \
                    "--ignored", "--exclude-standard", path], cwd=self.location)
                ignored_entries = proc.read().split("\n")[:-1]

                # Identify unversioned files
                proc = _vc.popen([self.CMD, "ls-files", "--others", \
                    "--exclude-standard", path], cwd=self.location)
                unversioned_entries = proc.read().split("\n")[:-1]

                # An unmerged file or a file that has been modified, added to
                # git's index, then modified again would result in the file
                # showing up in both the output of "diff-files" and
                # "diff-index".  The following command removes duplicate
                # file entries.
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
                columns = self.diff_re.search(entry).groups()
                old_mode, new_mode, statekey, name = columns
                if os.name == 'nt':
                    # Git returns unix-style paths on Windows
                    name = os.path.normpath(name.strip())
                path = os.path.join(self.root, name.strip())
                state = self.state_map.get(statekey.strip(), _vc.STATE_NONE)
                tree_state[path] = state
                if old_mode != new_mode:
                    msg = _("Mode changed from %s to %s" % \
                            (old_mode, new_mode))
                    self._tree_meta_cache[path] = msg

            for entry in ignored_entries:
                path = os.path.join(self.root, entry.strip())
                tree_state[path] = _vc.STATE_IGNORED

            for entry in unversioned_entries:
                path = os.path.join(self.root, entry.strip())
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
        for name,path in files:
            state = tree.get(path, _vc.STATE_NORMAL)
            meta = self._tree_meta_cache.get(path, "")
            retfiles.append(_vc.File(path, name, state, options=meta))
        for name,path in dirs:
            # git does not operate on dirs, just files
            retdirs.append( _vc.Dir(path, name, _vc.STATE_NORMAL))
        for path, state in tree.iteritems():
            # removed files are not in the filesystem, so must be added here
            if state is _vc.STATE_REMOVED:
                folder, name = os.path.split(path)
                if folder == directory:
                    retfiles.append( _vc.File(path, name, state) )
        return retdirs, retfiles

    def clean_patch(self, patch):
        """Remove extended header lines from the provided patch
        
        This removes any of Git's extended header information, being lines
        giving 'index', 'mode', 'new file' or 'deleted file' metadata. If
        there is no patch content other than this header information (e.g., if
        a file has had a mode change and nothing else) then an empty patch is
        returned, to avoid a non-applyable patch. Anything that doesn't look
        like a Git format patch is returned unchanged.
        """
        if not re.match(self.PATCH_INDEX_RE, patch, re.M):
            return patch

        patch_lines = patch.splitlines(True)
        for i, line in enumerate(patch_lines):
            # A bit loose, but this marks the start of a standard format patch
            if line.startswith("--- "):
                break
        else:
            return ""
        return "".join([patch_lines[0]] + patch_lines[i:])

