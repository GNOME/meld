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
import _vc

class Vc(_vc.Vc):

    CMD = "echo"
    NAME = "Null"

    def __init__(self, location):
        pass

    def commit_command(self, message):
        return [self.CMD,"commit","-m",message]
    def diff_command(self):
        return [self.CMD,"diff","-u"]
    def update_command(self):
        return [self.CMD,"update"]
    def add_command(self, binary=0):
        if binary:
            return [self.CMD,"add","-kb"]
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm","-f"]
    def revert_command(self):
        return [self.CMD,"update","-C"]

    def lookup_files(self, dirs, files):
        "files is array of (name, path). assume all files in same dir"
        if len(files) == 0 and len(dirs) == 0:
            return [],[]

        d = map(lambda x: _vc.Dir(x[1],x[0], _vc.STATE_NONE), dirs)
        f = map(lambda x: _vc.File(x[1],x[0], _vc.STATE_NONE, None), files)
        return d,f
