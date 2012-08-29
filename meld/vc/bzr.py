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
import re

class Vc(_vc.CachedVc):

    CMD = "bzr"
    CMDARGS = ["--no-aliases", "--no-plugins"]
    NAME = "Bazaar-NG"
    VC_DIR = ".bzr"
    PATCH_INDEX_RE = "^=== modified file '(.*)'.*$"

    # We use None here to indicate flags that we don't deal with or care about
    state_1_map = {
        " ": None,               # First status column empty
        "+": None,               # File versioned
        "-": None,               # File unversioned
        "R": None,               # File renamed
        "?": _vc.STATE_NONE,     # File unknown
        "X": None,               # File nonexistent (and unknown to bzr)
        "C": _vc.STATE_CONFLICT, # File has conflicts
        "P": None,               # Entry for a pending merge (not a file)
    }

    state_2_map = {
        " ": _vc.STATE_NORMAL,   # Second status column empty
        "N": _vc.STATE_NEW,      # File created
        "D": _vc.STATE_REMOVED,  # File deleted
        "K": None,               # File kind changed
        "M": _vc.STATE_MODIFIED, # File modified
    }
    
    valid_status_re = r'[%s][%s][\*\s]\s*' % (''.join(state_1_map.keys()),
                                              ''.join(state_2_map.keys()))

    def commit_command(self, message):
        return [self.CMD] + self.CMDARGS + ["commit", "-m", message]
    def diff_command(self):
        return [self.CMD] + self.CMDARGS + ["diff"]
    def update_command(self):
        return [self.CMD] + self.CMDARGS + ["pull"]
    def add_command(self, binary=0):
        return [self.CMD] + self.CMDARGS + ["add"]
    def remove_command(self, force=0):
        return [self.CMD] + self.CMDARGS + ["rm"]
    def revert_command(self):
        return [self.CMD] + self.CMDARGS + ["revert"]
    def resolved_command(self):
        return [self.CMD] + self.CMDARGS + ["resolve"]
    def valid_repo(self):
        if _vc.call([self.CMD, "status"], cwd=self.root):
            return False
        else:
            return True
    def get_working_directory(self, workdir):
        return self.root

    def _lookup_tree_cache(self, rootdir):
        branch_root = _vc.popen([self.CMD] + self.CMDARGS + ["root", rootdir]).read().rstrip('\n')
        while 1:
            try:
                proc = _vc.popen([self.CMD] + self.CMDARGS +
                                 ["status", "-S", "--no-pending", branch_root])
                entries = proc.read().split("\n")[:-1]
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise
        tree_state = {}
        for entry in entries:
            state_string, name = entry[:3], entry[4:]
            if not re.match(self.valid_status_re, state_string):
                continue
            # TODO: We don't do anything with exec bit changes.
            path = os.path.join(branch_root, name.strip())
            state = self.state_1_map.get(state_string[0], None)
            if state is None:
                state = self.state_2_map.get(state_string[1], _vc.STATE_NORMAL)
            tree_state[path] = state

        return tree_state

    def _get_dirsandfiles(self, directory, dirs, files):
        tree = self._get_tree_cache(directory)

        retfiles = []
        retdirs = []
        bzrfiles = {}
        for path,state in tree.iteritems():
            mydir, name = os.path.split(path)
            if path.endswith('/'):
                mydir, name = os.path.split(mydir)
            if mydir != directory:
                continue
            rev, options, tag = "","",""
            if path.endswith('/'):
                retdirs.append( _vc.Dir(path[:-1], name, state))
            else:
                retfiles.append( _vc.File(path, name, state, rev, tag, options) )
            bzrfiles[name] = 1
        for f,path in files:
            if f not in bzrfiles:
                #state = ignore_re.match(f) is None and _vc.STATE_NONE or _vc.STATE_IGNORED
                state = _vc.STATE_NORMAL
                retfiles.append( _vc.File(path, f, state, "") )
        for d,path in dirs:
            if d not in bzrfiles:
                #state = ignore_re.match(f) is None and _vc.STATE_NONE or _vc.STATE_IGNORED
                state = _vc.STATE_NORMAL
                retdirs.append( _vc.Dir(path, d, state) )
        return retdirs, retfiles
