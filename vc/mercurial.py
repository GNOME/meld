### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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

    CMD = "hg"
    NAME = "Mercurial"
    PATCH_STRIP_NUM = 1
    PATCH_INDEX_RE = "^diff(.*)$"

    def __init__(self, location):
        while location != "/":
            if os.path.isdir( "%s/.hg" % location):
                self.root = location
                return
            location = os.path.dirname(location)
        raise ValueError()

    def commit_command(self, message):
        return [self.CMD,"commit","-t",message]
    def diff_command(self):
        return [self.CMD,"diff"]
    def update_command(self):
        return [self.CMD,"update"]
    def add_command(self, binary=0):
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm"]
    def revert_command(self):
        return [self.CMD,"revert"]
    def get_working_directory(self, workdir):
        return self.root

    def lookup_files(self, dirs, files):
        "files is array of (name, path). assume all files in same dir"
        if len(files):
            directory = os.path.dirname(files[0][1])
        elif len(dirs):
            directory = os.path.dirname(dirs[0][1])
        else:
            return [],[]

        while 1:
            try:
                entries = os.popen("cd %s && hg status "%directory).read().split("\n")[:-1]
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise

        retfiles = []
        retdirs = []
        statemap = {
            "?": _vc.STATE_NONE,
            "A": _vc.STATE_NEW,
            " ": _vc.STATE_NORMAL,
            "!": _vc.STATE_MISSING,
            "I": _vc.STATE_IGNORED,
            "M": _vc.STATE_MODIFIED,
            "C": _vc.STATE_CONFLICT }
        hgfiles = {}
        for statekey, name in [ (entry[0], entry[2:]) for entry in entries if entry.find("/")==-1 ]:
            path = os.path.join(directory, name)
            rev, date, options, tag = "","","",""
            state = statemap.get(statekey, _vc.STATE_NONE)
            retfiles.append( _vc.File(path, name, state, rev, tag, options) )
            hgfiles[name] = 1
        for f,path in files:
            if f not in hgfiles:
                #state = ignore_re.match(f) == None and _vc.STATE_NONE or _vc.STATE_IGNORED
                state = _vc.STATE_NORMAL
                retfiles.append( _vc.File(path, f, state, "") )
        for d,path in dirs:
            if d not in hgfiles:
                #state = ignore_re.match(f) == None and _vc.STATE_NONE or _vc.STATE_IGNORED
                state = _vc.STATE_NORMAL
                retdirs.append( _vc.Dir(path, d, state) )

        return retdirs, retfiles


