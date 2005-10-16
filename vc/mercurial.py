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
import re
import time
import tree
import misc
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
        return [self.CMD,"commit","-m",message]
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
            "?": tree.STATE_NONE,
            "A": tree.STATE_NEW,
            " ": tree.STATE_NORMAL,
            "!": tree.STATE_MISSING,
            "I": tree.STATE_IGNORED,
            "M": tree.STATE_MODIFIED,
            "C": tree.STATE_CONFLICT }
        hgfiles = {}
        for statekey, name in [ (entry[0], entry[2:]) for entry in entries if entry.find("/")==-1 ]:
            path = os.path.join(directory, name)
            rev, date, options, tag = "","","",""
            state = statemap.get(statekey, tree.STATE_NONE)
            retfiles.append( _vc.File(path, name, state, rev, tag, options) )
            hgfiles[name] = 1
        for f,path in files:
            if f not in hgfiles:
                #state = ignore_re.match(f) == None and tree.STATE_NONE or tree.STATE_IGNORED
                state = tree.STATE_NORMAL
                retfiles.append( _vc.File(path, f, state, "") )
        for d,path in dirs:
            if d not in hgfiles:
                #state = ignore_re.match(f) == None and tree.STATE_NONE or tree.STATE_IGNORED
                state = tree.STATE_NORMAL
                retdirs.append( _vc.Dir(path, d, state) )

        return retdirs, retfiles


