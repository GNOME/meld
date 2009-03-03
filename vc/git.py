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

class Vc(_vc.Vc):

    CMD = "git"
    NAME = "Git"
    VC_DIR = ".git"
    PATCH_STRIP_NUM = 1
    PATCH_INDEX_RE = "^diff --git a/(.*) b/.*$"

    def __init__(self, location):
        self._tree_cache = None
        try:
            _vc.Vc.__init__(self, location)
        except ValueError:
            gitdir = os.environ.get("GIT_DIR")
            if gitdir and os.path.isdir(gitdir):
                self.root = gitdir
                return
            raise ValueError()

    def commit_command(self, message):
        return [self.CMD,"commit","-m",message]
    def diff_command(self):
        return [self.CMD,"diff","HEAD"]
    def update_command(self):
        return [self.CMD,"pull"]
    def add_command(self, binary=0):
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm"]
    def revert_command(self):
        return [self.CMD,"checkout"]

    def cache_inventory(self, topdir):
        self._tree_cache = self.lookup_tree()

    def uncache_inventory(self):
        self._tree_cache = None

    def lookup_tree(self):
        while 1:
            try:
                proc = os.popen("cd %s && git status --untracked-files" % self.root)
                entries = proc.read().split("\n")[:-1]
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise
        statemap = {
            "unknown": _vc.STATE_NONE,
            "new file": _vc.STATE_NEW,
            "deleted": _vc.STATE_REMOVED,
            "modified": _vc.STATE_MODIFIED,
            "typechange": _vc.STATE_NORMAL,
            "unmerged": _vc.STATE_CONFLICT }
        tree_state = {}
        for entry in entries:
            if not entry.startswith("#\t"):
                continue
            try:
                statekey, name = entry[2:].split(":", 2)
            except ValueError:
                # untracked
                name = entry[2:]
                path = os.path.join(self.root, name.strip())
                tree_state[path] = _vc.STATE_NONE
            else:
                statekey = statekey.strip()
                name = name.strip()
                try:
                    src, dst = name.split(" -> ", 2)
                except ValueError:
                    path = os.path.join(self.root, name.strip())
                    state = statemap.get(statekey, _vc.STATE_NONE)
                    tree_state[path] = state
                else:
                    # copied, renamed
                    if statekey == "renamed":
                        tree_state[os.path.join(self.root, src)] = _vc.STATE_REMOVED
                    tree_state[os.path.join(self.root, dst)] = _vc.STATE_NEW
        return tree_state

    def get_tree(self):
        if self._tree_cache is None:
            return self.lookup_tree()
        else:
            return self._tree_cache

    def _get_dirsandfiles(self, directory, dirs, files):

        tree = self.get_tree()

        retfiles = []
        retdirs = []
        for name,path in files:
            state = tree.get(path, _vc.STATE_IGNORED)
            retfiles.append( _vc.File(path, name, state) )
        for name,path in dirs:
            # git does not operate on dirs, just files
            retdirs.append( _vc.Dir(path, name, _vc.STATE_NORMAL))
        for path, state in tree.iteritems():
            # removed files are not in the filesystem, so must be added here
            if state is _vc.STATE_REMOVED:
                dir, name = os.path.split(path)
                if dir == directory:
                    retfiles.append( _vc.File(path, name, state) )
        return retdirs, retfiles

    def listdir_filter(self, entries):
        return [f for f in entries if f!=".git"]
