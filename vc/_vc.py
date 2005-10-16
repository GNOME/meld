### Copyright (C) 2002-2004 Stephen Kennedy <stevek@gnome.org>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import os
import tree

class Entry(object):
    # These are the possible states of files. Be sure to get the colons correct.
    states = _("Ignored:Unversioned:::Error::Newly added:Modified:<b>Conflict</b>:Removed:Missing").split(":")
    assert len(states)==tree.STATE_MAX
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

