### Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>

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

import _vc
import svn

class Vc(svn.Vc):

    CMD = "cdv"
    NAME = "Codeville"
    VC_DIR = ".cdv"
    PATCH_INDEX_RE = "^[+]{3} (.+)$"
    state_map = {"M": _vc.STATE_MODIFIED,}

    def get_working_directory(self, workdir):
        return self.root

    def _get_matches(self, directory):
        entries = _vc.popen([self.CMD, "status"], cwd=directory).read()
        for line in entries.split("\n")[1:-1]:
            yield line[3:], line[0], ""
