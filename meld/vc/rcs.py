### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>, Oliver Gerlich
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

import os
import _vc

class Vc(_vc.Vc):
    CMD = "rcs"
    NAME = "RCS"
    VC_DIR = "RCS"
    VC_ROOT_WALK = False
    PATCH_INDEX_RE = "^[+]{3} ([^\t]*)\t.*$"

    def commit_command(self, message):
        return ["ci", "-l", "-m%s" % (message,)]

    def diff_command(self):
        return ["rcsdiff", "-u"]

    def add_command(self, binary=0):
        return ["ci", "-l", "-i", "-t-'some file'", "-m'first revision'"]

    def _get_dirsandfiles(self, directory, dirs, files):
        "files is array of (name, path). Assume all files in same dir."

        retfiles = []
        retdirs = [_vc.Dir(x[1], x[0], _vc.STATE_NONE) for x in dirs]
        rcscontents = os.listdir(os.path.join(directory, self.VC_DIR))

        for name, path in files:
            assert path.startswith(directory)

            if name + ",v" not in rcscontents:
                # not versioned
                state = _vc.STATE_NONE
            else:
                cmd = "rcsdiff -q --brief %s > /dev/null 2>&1" % path
                result = os.system(cmd)
                sysresult = (result & 0x00FF)
                cmdresult = (result & 0xFF00) >> 8
                if sysresult != 0:
                    print "Error getting state of file %s (exec error %d)" % (path, sysresult)
                    state = _vc.STATE_ERROR
                elif cmdresult == 0:
                    state = _vc.STATE_NORMAL
                elif cmdresult == 1:
                    state = _vc.STATE_MODIFIED
                else:
                    print "Error getting state of file %s: %d" % (path, result)
                    state = _vc.STATE_ERROR

            retfiles.append(_vc.File(path, name, state, "", "", ""))

        return retdirs, retfiles
