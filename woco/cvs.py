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
        self.root = os.path.abspath(root)
        
    def listdir(self, relpath):
        """Return list of <dirs>+<files> at relpath.
        
        """
        directory = os.path.join(self.root, relpath)
        try:
            cvs_entries_file = self._read_cvs_entries(directory)
        except IOError, e: # no cvs dir
            cvs_entries = []
        else:
            cvs_entries, cvs_dict = self._parse_cvs_entries_file(directory, cvs_entries_file)

        print "**",relpath, "**",directory,"**",cvs_entries
        return cvs_entries
        ret = self._merge_local(directory, cvs_entries, cvs_dict)
        print ret
        return ret


    #
    # Internal
    #

    def _read_cvs_entries(self, directory):
        """Read contents of CVS/Entries as one big string
        """
        # CVS/Entries contains main info
        cvsntries = open( os.path.join(directory, "CVS/Entries"), "U").read()

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
            cvsentries += "\n".join(extras)
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
                entry.isdir = True
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
        return retdirs + retfiles, knowndict

    def _get_cvs_ignore_func(self, directory):
        """Return a function to test whether a file is ignored.
        """
        ignored = ["CVS"]
        try:
            ignored += open("%s/.cvsignore" % os.environ["HOME"]).read().split()
        except (IOError,KeyError):
            pass
        try:
            ignored += open( os.path.join(directory, ".cvsignore") ).read().split()
        except IOError:
            pass
        print ignored

        if len(ignored):
            regexes = [ woco.shell_to_regex(i, extended=False)[:-1] for i in ignored ]
            try:
                return lambda x : re.compile( "(" + "|".join(regexes) + ")" ).match(x) != None
            except re.error:
                pass
        return lambda x : False


    def _merge_local(self, directory, cvs_entries, cvs_dict):
        """Merge the local entries into the cvs entries.
        """
        return cvs_entries
        pathto = lambda d : os.path.join(directory,d)
        cvs_ignored = self._get_cvs_ignore_func(directory)

        local = os.listdir(directory)
        local.sort()
        for e in local:
            if not d in knowndict and not cvs_ignored(d):
                dirs.append( woco.Entry(pathto(d)) )

        #    e in local if isdir(e) ]:

        files= [ e for e in entries if not isdir(e) ]
        return dirs, files
        local_dirs, local_files = local_entries
        cvs_files += [woco.Entry(pathto(f)) for f in local_files if not cvs_ignored(f) and f not in versiondict]

        # ignored
        return dirs + files
