# -*- coding: utf-8 -*- 

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:

### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2005 Aaron Bentley <aaron.bentley@utoronto.ca>
### Copyright (C) 2007 José Fonseca <j_r_fonseca@yahoo.co.uk>

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

import os
import errno
import _vc

class Vc(_vc.CachedVc):

    CMD = "git"
    NAME = "Git"
    VC_DIR = ".git"
    PATCH_STRIP_NUM = 1
    PATCH_INDEX_RE = "^diff --git [ac]/(.*) [bw]/.*$"
    state_map = {
        "X": _vc.STATE_NONE,     # Unknown
        "A": _vc.STATE_NEW,      # New
        "D": _vc.STATE_REMOVED,  # Deleted
        "M": _vc.STATE_MODIFIED, # Modified
        "T": _vc.STATE_MODIFIED, # Type-changed
        "U": _vc.STATE_CONFLICT, # Unmerged
        "I": _vc.STATE_IGNORED,  # Ignored (made-up status letter)
        "?": _vc.STATE_NONE,     # Unversioned
    }

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
    def add_command(self, binary=0):
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm"]
    def revert_command(self):
        return [self.CMD,"checkout"]
    def valid_repo(self):
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
                proc = _vc.popen([self.CMD, "diff-index", "--name-status", \
                    "--cached", "HEAD", path], cwd=self.location)
                entries = proc.read().split("\n")[:-1]

                # Get the status of files that are different in the "index" vs
                # the files on disk
                proc = _vc.popen([self.CMD, "diff-files", "--name-status", \
                    "-0", path], cwd=self.location)
                entries += (proc.read().split("\n")[:-1])

                # Identify ignored files
                proc = _vc.popen([self.CMD, "ls-files", "--others", \
                    "--ignored", "--exclude-standard", path], cwd=self.location)
                entries += ("I\t%s" % f for f in proc.read().split("\n")[:-1])

                # Identify unversioned files
                proc = _vc.popen([self.CMD, "ls-files", "--others", \
                    "--exclude-standard", path], cwd=self.location)
                entries += ("?\t%s" % f for f in proc.read().split("\n")[:-1])

                # An unmerged file or a file that has been modified, added to
                # git's index, then modified again would result in the file
                # showing up in both the output of "diff-files" and
                # "diff-index".  The following command removes duplicate
                # file entries.
                entries = list(set(entries))
                break
            except OSError, e:
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
                statekey, name = entry.split("\t", 2)
                path = os.path.join(self.root, name.strip())
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
        for name,path in files:
            state = tree.get(path, _vc.STATE_NORMAL)
            retfiles.append( _vc.File(path, name, state) )
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
