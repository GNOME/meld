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

import os
import errno
import _vc

class Vc(_vc.Vc):

    CMD = "bzr"
    NAME = "Bazaar-NG"
    PATCH_STRIP_NUM = 0
    PATCH_INDEX_RE = "^=== modified file '(.*)'$"

    def __init__(self, location):
        self._tree_cache = None
        while location != "/":
            if os.path.isdir( "%s/.bzr" % location):
                self.root = location
                return
            location = os.path.dirname(location)
        raise ValueError()

    def commit_command(self, message):
        return [self.CMD,"commit","-m",message]
    def diff_command(self):
        return [self.CMD,"diff"]
    def update_command(self):
        return [self.CMD,"pull"]
    def add_command(self, binary=0):
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm"]
    def revert_command(self):
        return [self.CMD,"revert"]
    def get_working_directory(self, workdir):
        return self.root

    def cache_inventory(self, rootdir):
        self._tree_cache = self.lookup_tree()

    def uncache_inventory(self):
        self._tree_cache = None

    def lookup_tree(self):
        while 1:
            try:
                entries = os.popen("bzr status --all").read().split("\n")[:-1]
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise
        statemap = {
            "unknown:": _vc.STATE_NONE,
            "added:": _vc.STATE_NEW,
            "unchanged:": _vc.STATE_NORMAL,
            "removed:": _vc.STATE_REMOVED,
            "ignored:": _vc.STATE_IGNORED,
            "modified:": _vc.STATE_MODIFIED,
            "conflicts:": _vc.STATE_CONFLICT }
        tree_state = {}
        for entry in entries:
            if entry in statemap:
                cur_state = statemap[entry]
            else:
                if entry.startswith("  "):
                    tree_state[os.path.join(self.root, entry[2:])] = cur_state
        return tree_state

    def get_tree(self):
        if self._tree_cache is None:
            return self.lookup_tree()
        else:
            return self._tree_cache
        
    def lookup_files(self, dirs, files):
        "files is array of (name, path). assume all files in same dir"
        tree = self.get_tree()
        if len(files):
            directory = os.path.dirname(files[0][1])
        elif len(dirs):
            directory = os.path.dirname(dirs[0][1])
        else:
            return [],[]


        retfiles = []
        retdirs = []
        bzrfiles = {}
        for path,state in tree.iteritems():
            mydir, name = os.path.split(path)
            if path.endswith('/'):
                mydir, name = os.path.split(mydir)
            if mydir != directory:
                continue
            rev, date, options, tag = "","","",""
            if path.endswith('/'):
                retdirs.append( _vc.Dir(path[:-1], name, state))
            else:
                retfiles.append( _vc.File(path, name, state, rev, tag, options) )
            bzrfiles[name] = 1
        for f,path in files:
            if f not in bzrfiles:
                #state = ignore_re.match(f) == None and _vc.STATE_NONE or _vc.STATE_IGNORED
                state = _vc.STATE_NORMAL
                retfiles.append( _vc.File(path, f, state, "") )
        for d,path in dirs:
            if d not in bzrfiles:
                #state = ignore_re.match(f) == None and _vc.STATE_NONE or _vc.STATE_IGNORED
                state = _vc.STATE_NORMAL
                retdirs.append( _vc.Dir(path, d, state) )
        return retdirs, retfiles

