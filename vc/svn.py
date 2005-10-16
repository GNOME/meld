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
import tree
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
                    state = tree.STATE_NORMAL
                else:
                    state = tree.STATE_MISSING
                # svn adds the directory reported to the status list we get.
                if name != directory:
                    retdirs.append( _vc.Dir(path,name,state) )
            else:
                state = { "?": tree.STATE_NONE,
                          "A": tree.STATE_NEW,
                          " ": tree.STATE_NORMAL,
                          "!": tree.STATE_MISSING,
                          "I": tree.STATE_IGNORED,
                          "M": tree.STATE_MODIFIED,
                          "C": tree.STATE_CONFLICT }.get(match[1], tree.STATE_NONE)
                retfiles.append( _vc.File(path, name, state, rev, tag, options) )

        return retdirs, retfiles
