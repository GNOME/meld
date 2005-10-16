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
        if len(files):
            directory = os.path.dirname(files[0][1])
        elif len(dirs):
            directory = os.path.dirname(dirs[0][1])
        else:
            return [],[]

        d = map(lambda x: _vc.Dir(x[1],x[0], tree.STATE_NONE), dirs)
        f = map(lambda x: _vc.File(x[1],x[0], tree.STATE_NONE, None), files)
        return d,f
