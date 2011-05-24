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
from gettext import gettext as _
import re
import time
from meld import misc
import _vc

class Vc(_vc.Vc):
    CMD = "cvs"
    # CVSNT is a drop-in replacement for CVS; if found, it is used instead
    ALT_CMD = "cvsnt"
    NAME = "CVS"
    VC_DIR = "CVS"
    VC_ROOT_WALK = False
    PATCH_INDEX_RE = "^Index:(.*)$"

    def __init__(self, location):
        super(Vc, self).__init__(location)
        if not _vc.call(["which", self.ALT_CMD]):
            self.CMD = self.ALT_CMD

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
    def valid_repo(self):
        if _vc.call([self.CMD, "version"], cwd=self.root):
            return False
        else:
            return True

    def _get_dirsandfiles(self, directory, dirs, files):

        try:
            entries = open(os.path.join(directory, self.VC_DIR, "Entries")).read()
            # poor mans universal newline
            entries = entries.replace("\r","\n").replace("\n\n","\n")
        except IOError, e: # no cvs dir
            d = map(lambda x: _vc.Dir(x[1],x[0], _vc.STATE_NONE), dirs)
            f = map(lambda x: _vc.File(x[1],x[0], _vc.STATE_NONE, None), files)
            return d,f

        try:
            logentries = open(os.path.join(directory, self.VC_DIR, "Entries.Log")).read()
        except IOError, e:
            pass
        else:
            matches = re.findall("^([AR])\s*(.+)$(?m)", logentries)
            toadd = []
            for match in matches:
                if match[0] == "A":
                    toadd.append( match[1] )
                elif match[0] == "R":
                    try:
                        toadd.remove( match[1] )
                    except ValueError:
                        pass
                else:
                    print "Unknown Entries.Log line '%s'" % match[0]
            entries += "\n".join(toadd)

        retfiles = []
        retdirs = []
        matches = re.findall("^(D?)/([^/]+)/(.+)$(?m)", entries)
        matches.sort()

        for match in matches:
            isdir = match[0]
            name = match[1]
            path = os.path.join(directory, name)
            rev, date, options, tag = match[2].split("/")
            if tag:
                tag = tag[1:]
            if isdir:
                if os.path.exists(path):
                    state = _vc.STATE_NORMAL
                else:
                    state = _vc.STATE_MISSING
                retdirs.append( _vc.Dir(path,name,state) )
            else:
                if rev.startswith("-"):
                    state = _vc.STATE_REMOVED
                elif date=="dummy timestamp":
                    if rev[0] == "0":
                        state = _vc.STATE_NEW
                    else:
                        print "Revision '%s' not understood" % rev
                elif date=="dummy timestamp from new-entry":
                    state = _vc.STATE_MODIFIED
                else:
                    date = re.sub(r"\s*\d+", lambda x : "%3i" % int(x.group()), date, 1)
                    plus = date.find("+")
                    if plus >= 0:
                        state = _vc.STATE_CONFLICT
                        try:
                            txt = open(path, "U").read()
                        except IOError:
                            pass
                        else:
                            if txt.find("\n=======\n") == -1:
                                state = _vc.STATE_MODIFIED
                    else:
                        try:
                            mtime = os.stat(path).st_mtime
                        except OSError:
                            state = _vc.STATE_MISSING
                        else:
                            if time.asctime(time.gmtime(mtime))==date:
                                state = _vc.STATE_NORMAL
                            else:
                                state = _vc.STATE_MODIFIED
                retfiles.append( _vc.File(path, name, state, rev, tag, options) )
        # known
        cvsfiles = map(lambda x: x[1], matches)
        # ignored
        try:
            ignored = open(os.path.join(os.environ["HOME"], ".cvsignore")).read().split()
        except (IOError, KeyError):
            ignored = []
        try:
            ignored += open( os.path.join(directory, ".cvsignore")).read().split()
        except IOError:
            pass

        if len(ignored):
            try:
                regexes = [ misc.shell_to_regex(i)[:-1] for i in ignored ]
                ignore_re = re.compile( "(" + "|".join(regexes) + ")" )
            except re.error, e:
                misc.run_dialog(_("Error converting to a regular expression\n"
                                  "The pattern was '%s'\n"
                                  "The error was '%s'") % (",".join(ignored), e))
        else:
            class dummy(object):
                def match(self, *args): return None
            ignore_re = dummy()

        for f,path in files:
            if f not in cvsfiles:
                state = ignore_re.match(f) is None and _vc.STATE_NONE or _vc.STATE_IGNORED
                retfiles.append( _vc.File(path, f, state, "") )
        for d,path in dirs:
            if d not in cvsfiles:
                state = ignore_re.match(d) is None and _vc.STATE_NONE or _vc.STATE_IGNORED
                retdirs.append( _vc.Dir(path, d, state) )

        return retdirs, retfiles
