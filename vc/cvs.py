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
    CMD = "cvs"
    NAME = "CVS"
    PATCH_INDEX_RE = "^Index:(.*)$"

    def __init__(self, location):
        if not os.path.exists("%s/CVS"% location):
            raise ValueError

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

        try:
            entries = open( os.path.join(directory, "CVS/Entries")).read()
            # poor mans universal newline
            entries = entries.replace("\r","\n").replace("\n\n","\n")
        except IOError, e: # no cvs dir
            d = map(lambda x: _vc.Dir(x[1],x[0], tree.STATE_NONE), dirs)
            f = map(lambda x: _vc.File(x[1],x[0], tree.STATE_NONE, None), files)
            return d,f

        try:
            logentries = open( os.path.join(directory, "CVS/Entries.Log")).read()
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
                    state = tree.STATE_NORMAL
                else:
                    state = tree.STATE_MISSING
                retdirs.append( _vc.Dir(path,name,state) )
            else:
                if rev.startswith("-"):
                    state = tree.STATE_REMOVED
                elif date=="dummy timestamp":
                    if rev[0] == "0":
                        state = tree.STATE_NEW
                    else:
                        print "Revision '%s' not understood" % rev
                elif date=="dummy timestamp from new-entry":
                    state = tree.STATE_MODIFIED
                else:
                    date = re.sub(r"\s*\d+", lambda x : "%3i" % int(x.group()), date, 1)
                    plus = date.find("+")
                    if plus >= 0:
                        state = tree.STATE_CONFLICT
                        try:
                            txt = open(path, "U").read()
                        except IOError:
                            pass
                        else:
                            if txt.find("\n=======\n") == -1:
                                state = tree.STATE_MODIFIED
                    else:
                        try:
                            mtime = os.stat(path).st_mtime
                        except OSError:
                            state = tree.STATE_MISSING
                        else:
                            if time.asctime(time.gmtime(mtime))==date:
                                state = tree.STATE_NORMAL
                            else:
                                state = tree.STATE_MODIFIED
                retfiles.append( _vc.File(path, name, state, rev, tag, options) )
        # known
        cvsfiles = map(lambda x: x[1], matches)
        # ignored
        try:
            ignored = open( os.path.join(directory, "%s/.cvsignore" % os.environ["HOME"] )).read().split()
        except (IOError,KeyError):
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
                misc.run_dialog(_("Error converting to a regular expression\n" \
                                  "The pattern was '%s'\n" \
                                  "The error was '%s'") % (",".join(ignored), e))
        else:
            class dummy(object):
                def match(*args): return None
            ignore_re = dummy()

        for f,path in files:
            if f not in cvsfiles:
                state = ignore_re.match(f) == None and tree.STATE_NONE or tree.STATE_IGNORED
                retfiles.append( _vc.File(path, f, state, "") )
        for d,path in dirs:
            if d not in cvsfiles:
                state = ignore_re.match(d) == None and tree.STATE_NONE or tree.STATE_IGNORED
                retdirs.append( _vc.Dir(path, d, state) )

        return retdirs, retfiles

