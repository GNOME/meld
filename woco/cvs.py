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

import woco
import os
import re
import time

class WorkingCopy:
    """CVS working copy browser.
    """
    
    def __init__(self, root):
        """Open working copy rooted at local path "root"
        """
        self.root = root
        
    def listdir(self, relpath):
        """Return list of <dirs>,<files> at relpath.
        
        Can raise OSError if relpath does not exist.
        """
        directory = os.path.join(self.root, relpath)
        local_entries = self._list_local(directory)
        try:
            cvs_entries_file = self._read_cvs_entries(directory)
        except IOError, e: # no cvs dir
            pathto = lambda d : os.path.join(directory,d)
            dirs, files = local_entries
            return [woco.Entry(pathto(d)) for d in dirs], [woco.Entry(pathto(f)) for f in files]
        cvs_entries = self._parse_cvs_entries_file(directory, cvs_entries_file)
        return self._merge_lists(directory, cvs_entries, local_entries)


    #
    # Internal
    #

    def _list_local(self, directory):
        """List the local directory contents.
        """
        entries = os.listdir(directory)
        pathto = lambda d : os.path.join(directory,d)
        isdir = lambda d : os.path.isdir( os.path.join(directory,d) )
        dirs = [ e for e in entries if isdir(e) ]
        files= [ e for e in entries if not isdir(e) ]
        return dirs, files

    def _read_cvs_entries(self, directory):
        """Read contents of CVS/Entries as one big string
        """
        # CVS/Entries contains main info
        cvsentries = open( os.path.join(directory, "CVS/Entries"), "U").read()

        # CVS/Entries.Log may contain info not yet added to CVS/Entries
        try:
            logentries = open( os.path.join(directory, "CVS/Entries.Log"), "U").read()
        except IOError, e:
            pass
        else:
            matches = re.findall("^([AR])\s*(.+)$(?m)", logentries)
            extras = []
            for match in matches:
                if match[0] == "A":
                    extras.append( match[1] )
                elif match[0] == "R":
                    try:
                        extras.remove( match[1] )
                    except ValueError:
                        pass
                else:
                    print "Unknown Entries.Log line '%s'" % match[0]
            cvsentries = "\n".join(extras)
        return cvsentries

    def _parse_cvs_entries_file(self, directory, cvsentries):
        """Extract versioned entries from cvsenties string.
        """
        pathto = lambda d : os.path.join(directory,d)
        retfiles = []
        retdirs = []
        matches = re.findall("^(D?)/([^/]+)/(.+)$(?m)", cvsentries)
        matches.sort()
        knowndict = {}

        for isdir, name, rest in matches:
            knowndict[name] = 1
            path = os.path.join(directory, name)
            entry = woco.Entry(path)
            rev, date, options, tag = rest.split("/")
            if tag:
                entry.tag = tag[1:]
            if isdir:
                if os.path.exists(path):
                    entry.status = woco.Status.NORMAL
                else:
                    entry.status = woco.Status.MISSING
                retdirs.append( entry )
            else:
                entry.version = rev
                if rev.startswith("-"):
                    entry.status = woco.Status.REMOVED
                elif date=="dummy timestamp":
                    if rev[0] == "0":
                        entry.status = woco.Status.NEW
                    else:
                        print "Revision '%s' not understood" % rev
                elif date=="dummy timestamp from new-entry":
                    entry.status = woco.Status.MODIFIED
                else:
                    plus = date.find("+")
                    if plus >= 0:
                        entry.status = woco.Status.CONFLICT
                    else:
                        try:
                            mtime = os.stat(path).st_mtime
                        except OSError:
                            entry.status = woco.Status.MISSING
                        else:
                            if time.asctime(time.gmtime(mtime))==date:
                                entry.status = woco.Status.NORMAL
                            else:
                                entry.status = woco.Status.MODIFIED
                retfiles.append( entry )
        return retdirs, retfiles

    def _get_cvs_ignore_func(self, directory):
        """Return a function to test whether a file is ignored.
        """
        try:
            ignored = open("%s/.cvsignore" % os.environ["HOME"]).read().split()
        except (IOError,KeyError):
            ignored = []
        try:
            ignored += open( os.path.join(directory, ".cvsignore") ).read().split()
        except IOError:
            pass

        if len(ignored):
            regexes = [ woco.shell_to_regex(i)[:-1] for i in ignored ]
            try:
                return lambda x : re.compile( "(" + "|".join(regexes) + ")" ).match(x) != None
            except re.error:
                pass
        return lambda x : False

    def _merge_lists(self, directory, cvs_entries, local_entries):
        """Merge the local entries into the cvs entries.
        """
        pathto = lambda d : os.path.join(directory,d)
        cvs_ignored = self._get_cvs_ignore_func(directory)
        cvs_dirs, cvs_files = cvs_entries
        versiondict = {}
        for e in cvs_dirs + cvs_files:
            versiondict[ os.path.basename(e.path) ] = 1
        local_dirs, local_files = local_entries
        cvs_dirs  += [woco.Entry(pathto(d)) for d in local_dirs  if not cvs_ignored(d) and d not in versiondict]
        cvs_files += [woco.Entry(pathto(f)) for f in local_files if not cvs_ignored(f) and f not in versiondict]

        # ignored
        return cvs_dirs, cvs_files
