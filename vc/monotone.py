### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2005 Daniel Thompson <daniel@redfelineninja.org.uk>

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
import time
import _vc


class Vc(_vc.Vc):
    CMD = "monotone"
    NAME = "Monotone"
    PATCH_STRIP_NUM = 0
    PATCH_INDEX_RE = "^[+]{3,3} ([^  ]*)\t[0-9a-f]{40,40}$"

    def __init__(self, location):
        self._tree_cache = None
        while location != "/":
            if os.path.isdir( "%s/MT" % location):
                self.root = location
                return
            location = os.path.dirname(location)
        raise ValueError

    def commit_command(self, message):
        return [self.CMD,"commit","-m",message]
    def diff_command(self):
        return [self.CMD,"diff"]
    def update_command(self):
        return [self.CMD,"update"]
    def add_command(self, binary=0):
        #if binary:
        #    return [self.CMD,"add","-kb"]
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"drop"]
    def revert_command(self):
        return [self.CMD,"revert"]
    def get_working_directory(self, workdir):
        return self.root

    def cache_inventory(self, rootdir):
        self._tree_cache = self.lookup_tree()

    def uncache_inventory(self):
        self._tree_cache = None

    def lookup_tree(self):
        while 1:
            try:
                entries = os.popen("monotone automate inventory").read().split("\n")[:-1]
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise

        statemap = {
            '   ' : _vc.STATE_NORMAL,   # unchanged
            '  P' : _vc.STATE_MODIFIED, # patched (contents changed)
            '  U' : _vc.STATE_NONE,     # unknown (exists on the filesystem but not tracked)
            '  I' : _vc.STATE_IGNORED,  # ignored (exists on the filesystem but excluded by lua hook)
            '  M' : _vc.STATE_MISSING,  # missing (exists in the manifest but not on the filesystem)

            ' A ' : _vc.STATE_ERROR,    # added (invalid, add should have associated patch)
            ' AP' : _vc.STATE_NEW,      # added and patched
            ' AU' : _vc.STATE_ERROR,    # added but unknown (invalid)
            ' AI' : _vc.STATE_ERROR,    # added but ignored (seems invalid, but may be possible)
            ' AM' : _vc.STATE_EMPTY,    # added but missing from the filesystem

            ' R ' : _vc.STATE_NORMAL,   # rename target
            ' RP' : _vc.STATE_MODIFIED, # rename target and patched
            ' RU' : _vc.STATE_ERROR,    # rename target but unknown (invalid)
            ' RI' : _vc.STATE_ERROR,    # rename target but ignored (seems invalid, but may be possible?)
            ' RM' : _vc.STATE_MISSING,  # rename target but missing from the filesystem

            'D  ' : _vc.STATE_REMOVED,  # dropped
            'D P' : _vc.STATE_ERROR,    # dropped and patched (invalid)
            'D U' : _vc.STATE_REMOVED,  # dropped and unknown (still exists on the filesystem)
            'D I' : _vc.STATE_ERROR,    # dropped and ignored (seems invalid, but may be possible?)
            'D M' : _vc.STATE_ERROR,    # dropped and missing (invalid)

            'DA ' : _vc.STATE_ERROR,    # dropped and added (invalid, add should have associated patch)
            'DAP' : _vc.STATE_NEW,      # dropped and added and patched
            'DAU' : _vc.STATE_ERROR,    # dropped and added but unknown (invalid)
            'DAI' : _vc.STATE_ERROR,    # dropped and added but ignored (seems invalid, but may be possible?)
            'DAM' : _vc.STATE_MISSING,  # dropped and added but missing from the filesystem

            'DR ' : _vc.STATE_NORMAL,   # dropped and rename target
            'DRP' : _vc.STATE_MODIFIED, # dropped and rename target and patched
            'DRU' : _vc.STATE_ERROR,    # dropped and rename target but unknown (invalid)
            'DRI' : _vc.STATE_ERROR,    # dropped and rename target but ignored (invalid)
            'DRM' : _vc.STATE_MISSING,  # dropped and rename target but missing from the filesystem

            'R  ' : _vc.STATE_REMOVED,  # rename source
            'R P' : _vc.STATE_ERROR,    # rename source and patched (invalid)
            'R U' : _vc.STATE_REMOVED,  # rename source and unknown (still exists on the filesystem)
            'R I' : _vc.STATE_ERROR,    # rename source and ignored (seems invalid, but may be possible?)
            'R M' : _vc.STATE_ERROR,    # rename source and missing (invalid)

            'RA ' : _vc.STATE_ERROR,    # rename source and added (invalid, add should have associated patch)
            'RAP' : _vc.STATE_NEW,      # rename source and added and patched
            'RAU' : _vc.STATE_ERROR,    # rename source and added but unknown (invalid)
            'RAI' : _vc.STATE_ERROR,    # rename source and added but ignored (seems invalid, but may be possible?)
            'RAM' : _vc.STATE_MISSING,  # rename source and added but missing from the filesystem

            'RR ' : _vc.STATE_NEW,      # rename source and target
            'RRP' : _vc.STATE_MODIFIED, # rename source and target and target patched
            'RRU' : _vc.STATE_ERROR,    # rename source and target and target unknown (invalid)
            'RRI' : _vc.STATE_ERROR,    # rename source and target and target ignored (seems invalid, but may be possible?)
            'RRM' : _vc.STATE_MISSING   # rename source and target and target missing
        }

        tree_state = {}
        for entry in entries:
            mstate = entry[0:3]
            rename_tracking = entry[4:7] # unused
            fname = entry[8:]

            if mstate in statemap:
                state = statemap[mstate]
                if state == _vc.STATE_ERROR:
                    print "WARNING: invalid state ('%s') reported by 'automate inventory'" % mstate
            else:
                state = _vc.STATE_ERROR
                print "WARNING: impossible state ('%s') reported by 'automate inventory' (version skew?)" % mstate

            tree_state[os.path.join(self.root, fname)] = state;

        return tree_state

    def get_tree(self):
        if self._tree_cache is None:
            return self.lookup_tree()
        else:
            return self._tree_cache

    def lookup_files(self, dirs, files):
        "files is array of (name, path). assume all files in same dir"
        tree = self.get_tree()
        if len(files):
            directory = os.path.dirname(files[0][1])
        elif len(dirs):
            directory = os.path.dirname(dirs[0][1])
        else:
            return [],[]


        retfiles = []
        retdirs = []
        vcfiles = {}

        for path,state in tree.iteritems():
            mydir, name = os.path.split(path)
            if path.endswith('/'):
                mydir, name = os.path.split(mydir)
            if mydir != directory:
                continue
            rev, date, options, tag = "","","",""
            if path.endswith('/'):
                retdirs.append( _vc.Dir(path[:-1], name, state))
            else:
                retfiles.append( _vc.File(path, name, state, rev, tag, options) )
            vcfiles[name] = 1
        for f,path in files:
            if f not in vcfiles:
                # if the ignore MT filter is not enabled these will crop up
                ignorelist = [ 'log', 'options', 'revision', 'work' ]

                if f not in ignorelist:
                    print "WARNING: '%s' was not listed by 'automate inventory'" % f

                # if it ain't listed by the inventory it's not under version
                # control
                state = _vc.STATE_NONE
                retfiles.append( _vc.File(path, f, state, "") )
        for d,path in dirs:
            if d not in vcfiles:
                # if the ignore MT filter is not enabled these will crop up
                ignorelist = [ 'MT' ]
                if d in ignorelist:
                    state = _vc.STATE_NONE
                else:
                    # monotone does not version (or inventory) directories
                    # so these are always normal
                    state = _vc.STATE_NORMAL
                retdirs.append( _vc.Dir(path, d, state) )
        return retdirs, retfiles
