### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2005 Daniel Thompson <daniel@redfelineninja.org.uk>
### Copyright (C) 2011 Jan Danielsson <jan.m.danielsson@gmail.com>

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
import _vc
import errno


class Vc(_vc.CachedVc):

    CMD = "fossil"
    NAME = "Fossil"
    VC_METADATA = [".fslckout", "_FOSSIL_", ".fos"]    # One or the other
    PATCH_INDEX_RE = "^--- (.*)$"

    state_map = {
        'ADDED'       : _vc.STATE_NEW,
        'DELETED'     : _vc.STATE_REMOVED,
        'NOT_A_FILE'  : _vc.STATE_ERROR,
        'UNCHANGED'   : _vc.STATE_NORMAL,
        'EDITED'      : _vc.STATE_MODIFIED,
        'MISSING'     : _vc.STATE_MISSING,
    }

    def commit_command(self, message):
        return [self.CMD, "commit", "-m", message]

    def diff_command(self):
        return [self.CMD, "diff"]

    def update_command(self):
        return [self.CMD, "update"]

    def add_command(self, binary=0):
        return [self.CMD, "add"]

    def remove_command(self, force=0):
        return [self.CMD, "rm"]

    def revert_command(self):
        return [self.CMD, "revert"]

    def valid_repo(self):
        if _vc.call([self.CMD, "info"], cwd=self.root):
            return False
        else:
            return True

    def check_repo_root(self, location):
        # Fossil uses a file -- not a directory
        for metafile in self.VC_METADATA:
            if os.path.isfile(os.path.join(location, metafile)):
                return location
        raise ValueError

    def get_working_directory(self, workdir):
        return self.root

    def _lookup_tree_cache(self, rootdir):
        while 1:
            try:
                entries = _vc.popen([self.CMD, "ls", "-l"],
                                    cwd=self.root).read().split("\n")[:-1]
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise

        tree_state = {}
        for entry in entries:
            mstate = entry.split(' ', 1)[0]
            fname = entry.split(' ', 1)[1].strip()

            if mstate in self.state_map:
                state = self.state_map[mstate]

                # Fossil's 'ls -l' doesn't detect if a newly added file has
                # gone missing, so we handle this special case here.
                if state == _vc.STATE_NEW and not os.path.exists(rootdir +
                      os.sep + fname):
                    state = _vc.STATE_MISSING

                if state == _vc.STATE_ERROR:
                    print "WARNING: unknown state ('%s') reported by " \
                            "'ls -l'" % mstate
            else:
                state = _vc.STATE_ERROR
                print "WARNING: unknown state ('%s') reported by 'ls -l' " \
                        "(version skew?)" % mstate

            tree_state[os.path.join(self.root, fname)] = state

        return tree_state

    def _get_dirsandfiles(self, directory, dirs, files):

        tree = self._get_tree_cache(directory)

        retfiles = []
        retdirs = []
        vcfiles = {}

        for path, state in tree.iteritems():
            mydir, name = os.path.split(path)
            if path.endswith('/'):
                mydir, name = os.path.split(mydir)
            if mydir != directory:
                continue

            rev = ""
            while True:
                try:
                    entries = _vc.popen([self.CMD, "finfo", "-s", path],
                                        cwd=self.root).read().split(" ", 1)
                    # Process entries which have revision numbers.
                    if entries[0] in ['renamed', 'edited', 'deleted',
                                      'unchanged']:
                        rev = entries[1].strip()
                    break
                except OSError, e:
                    if e.errno != errno.EAGAIN:
                        raise

            options, tag = "", ""
            if path.endswith('/'):
                retdirs.append(_vc.Dir(path[:-1], name, state))
            else:
                retfiles.append(_vc.File(path, name, state, rev, tag,
                        options))
            vcfiles[name] = 1

        for f, path in files:
            if f not in vcfiles:
                # Ignore metadata files only if they are in the root of the
                # repository checkout. We ignore the manifest files since they
                # are typically automatically generated.
                # In theory, we can call "fossil settings" and grep for
                # manifest to determine if we should ignore the manifest files.
                if self.location == path.rsplit(os.sep, 1)[0]:
                    ignorelist = self.VC_METADATA + ['manifest',
                                  'manifest.uuid']

                    if f not in ignorelist:
                        print "WARNING: '%s' was not listed by 'ls -l'" % f

                # If it ain't listed by the inventory it's not under version
                # control
                state = _vc.STATE_NONE
                retfiles.append(_vc.File(path, f, state, ""))

        for d, path in dirs:
            if d not in vcfiles:
                # Fossil does not version (or inventory) directories so these
                # are always normal
                state = _vc.STATE_NORMAL
                retdirs.append(_vc.Dir(path, d, state))

        return retdirs, retfiles
