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
import re
import errno
import _vc

class Vc(_vc.Vc):

    CMD = "svn"
    NAME = "Subversion"
    PATCH_INDEX_RE = "^Index:(.*)$"

    def __init__(self, location):
        if not os.path.exists("%s/.svn"%location):
            raise ValueError()

    def commit_command(self, message):
        return [self.CMD,"commit","-m",message]
    def diff_command(self):
        return [self.CMD,"diff"]
    def update_command(self):
        return [self.CMD,"update"]
    def add_command(self, binary=0):
        if binary:
            return [self.CMD,"add","-kb"]
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm","-f"]
    def revert_command(self):
        return [self.CMD,"revert"]

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
                entries = os.popen("svn status -Nv "+directory).read()
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise

        retfiles = []
        retdirs = []
        matches = re.findall("^(.)....\s*\d*\s*(\d*)\s*\w*\s*(.*?)$(?m)", entries)
        matches = [ (m[2].split()[-1],m[0],m[1]) for m in matches]
        matches.sort()

        for match in matches:
            name = match[0]
            if(match[1] == "!" or match[1] == "A"):
                # for new or missing files, the findall expression
                # does not supply the correct name 
                name = re.sub(r'^[?]\s*(.*)$', r'\1', name)
            isdir = os.path.isdir(name)
            path = os.path.join(directory, name)
            rev = match[2]
            options = ""
            tag = ""
            if tag:
                tag = tag[1:]
            if isdir:
                if os.path.exists(path):
                    state = _vc.STATE_NORMAL
                else:
                    state = _vc.STATE_MISSING
                # svn adds the directory reported to the status list we get.
                if name != directory:
                    retdirs.append( _vc.Dir(path,name,state) )
            else:
                state = { "?": _vc.STATE_NONE,
                          "A": _vc.STATE_NEW,
                          " ": _vc.STATE_NORMAL,
                          "!": _vc.STATE_MISSING,
                          "I": _vc.STATE_IGNORED,
                          "M": _vc.STATE_MODIFIED,
                          "C": _vc.STATE_CONFLICT }.get(match[1], _vc.STATE_NONE)
                retfiles.append( _vc.File(path, name, state, rev, tag, options) )

        return retdirs, retfiles
