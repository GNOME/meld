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

# ignored, new, normal, ignored changes,
# error, placeholder, vc added
# vc modified, vc conflict, vc removed
# locally removed, end
STATE_IGNORED, STATE_NONE, STATE_NORMAL, STATE_NOCHANGE, \
STATE_ERROR, STATE_EMPTY, STATE_NEW, \
STATE_MODIFIED, STATE_CONFLICT, STATE_REMOVED, \
STATE_MISSING, STATE_MAX = range(12)

class Entry(object):
    # These are the possible states of files. Be sure to get the colons correct.
    states = _("Ignored:Unversioned:::Error::Newly added:Modified:<b>Conflict</b>:Removed:Missing").split(":")
    assert len(states)==STATE_MAX
    def __str__(self):
        return "<%s:%s %s>\n" % (self.__class__, self.name, (self.path, self.state))
    def __repr__(self):
        return "%s %s\n" % (self.name, (self.path, self.state))
    def get_status(self):
        return self.states[self.state]

class Dir(Entry):
    def __init__(self, path, name, state):
        self.path = path
        self.parent, self.name = os.path.split(path[:-1])
        self.state = state
        self.isdir = 1
        self.rev = ""
        self.tag = ""
        self.options = ""

class File(Entry):
    def __init__(self, path, name, state, rev="", tag="", options=""):
        assert path[-1] != "/"
        self.path = path
        self.parent, self.name = os.path.split(path)
        self.state = state
        self.isdir = 0
        self.rev = rev
        self.tag = tag
        self.options = options

class Vc(object):

    PATCH_STRIP_NUM = 0

    def __init__(self, location):
        pass

    def commit_command(self, message):
        raise NotImplementedError()
    def diff_command(self):
        raise NotImplementedError()
    def update_command(self):
        raise NotImplementedError()
    def add_command(self, binary=0):
        raise NotImplementedError()
    def remove_command(self, force=0):
        raise NotImplementedError()
    def revert_command(self):
        raise NotImplementedError()
    def patch_command(self, workdir):
        return ["patch","--strip=%i"%self.PATCH_STRIP_NUM,"--reverse","--directory=%s" % workdir]

    def lookup_files(self, cdirs, cfiles):
        raise NotImplementedError()

    def get_working_directory(self, workdir):
        return workdir

    def listdir(self, start):
        if start=="": start="."
        if start[-1] != "/": start+="/"
        cfiles = []
        cdirs = []
        try:
            entries = os.listdir(start)
            entries.sort()
        except OSError:
            entries = []
        for f in [f for f in entries if f[0]!="." and f!="CVS" and f!=".svn"]:
            fname = start + f
            lname = fname
            if os.path.isdir(fname):
                cdirs.append( (f, lname) )
            else:
                cfiles.append( (f, lname) )
        dirs, files = self.lookup_files(cdirs, cfiles)
        return dirs+files

