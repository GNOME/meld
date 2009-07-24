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
import subprocess
from gettext import gettext as _

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
    def __init__(self, path, name, state):
        self.path = path
        self.state = state
        self.parent, self.name = os.path.split(path.rstrip("/"))
    def __str__(self):
        return "<%s:%s %s>\n" % (self.__class__, self.name, (self.path, self.state))
    def __repr__(self):
        return "%s %s\n" % (self.name, (self.path, self.state))
    def get_status(self):
        return self.states[self.state]

class Dir(Entry):
    def __init__(self, path, name, state):
        Entry.__init__(self, path, name, state)
        self.isdir = 1
        self.rev = ""
        self.tag = ""
        self.options = ""

class File(Entry):
    def __init__(self, path, name, state, rev="", tag="", options=""):
        assert path[-1] != "/"
        Entry.__init__(self, path, name, state)
        self.isdir = 0
        self.rev = rev
        self.tag = tag
        self.options = options

class Vc(object):

    PATCH_STRIP_NUM = 0
    PATCH_INDEX_RE = ''
    VC_DIR = None
    VC_ROOT_WALK = True
    VC_METADATA = None

    def __init__(self, location):
        if self.VC_ROOT_WALK:
            self.root = self.find_repo_root(location)
        else:
            self.root = self.check_repo_root(location)

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
    def resolved_command(self):
        raise NotImplementedError()
    def patch_command(self, workdir):
        return ["patch","--strip=%i"%self.PATCH_STRIP_NUM,"--reverse","--directory=%s" % workdir]

    def check_repo_root(self, location):
        if not os.path.isdir(os.path.join(location, self.VC_DIR)):
            raise ValueError
        return location

    def find_repo_root(self, location):
        while True:
            try:
                return self.check_repo_root(location)
            except ValueError:
                pass
            tmp = os.path.dirname(location)
            if tmp == location:
                break
            location = tmp
        raise ValueError()

    def get_working_directory(self, workdir):
        return workdir

    def cache_inventory(self, topdir):
        pass

    def uncache_inventory(self):
        pass

    def get_patch_files(self, patch):
        regex = re.compile(self.PATCH_INDEX_RE, re.M)
        return [f.strip() for f in regex.findall(patch)]

    def listdir_filter(self, entries):
        return [f for f in entries if f != self.VC_DIR]

    def listdir(self, start):
        if start=="": start="."
        cfiles = []
        cdirs = []
        try:
            entries = os.listdir(start)
            entries.sort()
        except OSError:
            entries = []
        for f in self.listdir_filter(entries):
            fname = os.path.join(start, f)
            lname = fname
            if os.path.isdir(fname):
                cdirs.append( (f, lname) )
            else:
                cfiles.append( (f, lname) )
        dirs, files = self.lookup_files(cdirs, cfiles)
        return dirs+files

    def lookup_files(self, dirs, files):
        "Assume all files are in the same dir, files is an array of (name, path) tuples."
        directory = self._get_directoryname(files, dirs)
        if directory is None:
            return [], []
        else:
            return self._get_dirsandfiles(directory, dirs, files)

    def _get_directoryname(self, dirs, files):
        directory = None
        if len(files):
            directory = os.path.dirname(files[0][1])
        elif len(dirs):
            directory = os.path.dirname(dirs[0][1])
        return directory

    def _get_dirsandfiles(self, directory, dirs, files):
        raise NotImplementedError()


class CachedVc(Vc):

    def __init__(self, location):
        super(CachedVc, self).__init__(location)
        self._tree_cache = None

    def cache_inventory(self, directory):
        self._tree_cache = self._lookup_tree_cache(directory)

    def uncache_inventory(self):
        self._tree_cache = None

    def _lookup_tree_cache(self, directory):
        raise NotImplementedError()

    def _get_tree_cache(self, directory):
        if self._tree_cache is None:
            self.cache_inventory(directory)
        return self._tree_cache

def popen(cmd, cwd=None):
    return subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE).stdout

