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
    VC_DIR = ".svn"
    VC_ROOT_WALK = False
    PATCH_INDEX_RE = "^Index:(.*)$"
    state_map = {
        "?": _vc.STATE_NONE,
        "A": _vc.STATE_NEW,
        " ": _vc.STATE_NORMAL,
        "!": _vc.STATE_MISSING,
        "I": _vc.STATE_IGNORED,
        "M": _vc.STATE_MODIFIED,
        "D": _vc.STATE_REMOVED,
        "C": _vc.STATE_CONFLICT,
    }

    re_status_moved = re.compile(r'^(A) +[+] +- +([?]) +[?] +([^ ].*)$')
    re_status_vc = re.compile(r'^(.) +\d+ +(\?|(?:\d+)) +[^ ]+ +([^ ].*)$')
    re_status_non_vc = re.compile(r'^([?]) +([^ ].*)$')
    re_status_tree_conflict = re.compile(r'^ +> +.*')

    def commit_command(self, message):
        return [self.CMD,"commit","-m",message]
    def diff_command(self):
        return [self.CMD,"diff"]
    def update_command(self):
        return [self.CMD,"update"]
    def add_command(self, binary=0):
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm","--force"]
    def revert_command(self):
        return [self.CMD,"revert"]

    def _get_matches(self, directory):
        """return a list of tuples (file_path, status_code, revision)"""

        while 1:
            try:
                entries = os.popen("%s status -Nv %s" % (self.CMD, directory))
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise

        matches = []

        for line in entries:
            # svn-1.6.x changed 'status' command output
            # adding tree-conflict lines, c.f.:
            # http://subversion.tigris.org/svn_1.6_releasenotes.html
            m = self.re_status_tree_conflict.match(line)
            if m:
                # skip this line
                continue
            # A svn moved file
            m = self.re_status_moved.match(line)
            if m:
                matches.append((m.group(3), m.group(1), m.group(2)))
                continue
            # A svn controlled file
            m = self.re_status_vc.match(line)
            if m:
                matches.append((m.group(3), m.group(1), m.group(2)))
                continue
            # A new file, unknown to svn
            m = self.re_status_non_vc.match(line)
            if m:
                matches.append((m.group(2), m.group(1), ""))
                continue

        matches.sort()
        return matches

    def _get_dirsandfiles(self, directory, dirs, files):
        retfiles = []
        retdirs = []

        for match in self._get_matches(directory):
            name = match[0]
            isdir = os.path.isdir(name)
            path = os.path.join(directory, name)
            rev = match[2]
            options = ""
            if isdir:
                if os.path.exists(path):
                    state = _vc.STATE_NORMAL
                else:
                    state = _vc.STATE_MISSING
                # svn adds the directory reported to the status list we get.
                if name != directory:
                    retdirs.append( _vc.Dir(path,name,state) )
            else:
                state = self.state_map.get(match[1], _vc.STATE_NONE)
                retfiles.append( _vc.File(path, name, state, rev, "", options) )

        return retdirs, retfiles
