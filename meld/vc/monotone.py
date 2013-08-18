# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2005 Daniel Thompson <daniel@redfelineninja.org.uk>

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
# OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import errno
import logging
import os
import shutil
import subprocess
import tempfile

from . import _vc


class Vc(_vc.CachedVc):
    CMD = "mtn"
    NAME = "Monotone"
    VC_DIR = "_MTN"

    state_map_6 = {
        'added known rename_source'         : _vc.STATE_NEW,
        'added known'                       : _vc.STATE_NEW,
        'added missing'                     : _vc.STATE_EMPTY,
        'dropped'                           : _vc.STATE_REMOVED,
        'dropped unknown'                   : _vc.STATE_REMOVED,
        'known'                             : _vc.STATE_NORMAL,
        'known rename_target'               : _vc.STATE_MODIFIED,
        'missing'                           : _vc.STATE_MISSING,
        'missing rename_target'             : _vc.STATE_MISSING,
        'ignored'                           : _vc.STATE_IGNORED,
        'unknown'                           : _vc.STATE_NONE,
        'rename_source'                     : _vc.STATE_NONE, # the rename target is what we now care about
        'rename_source unknown'             : _vc.STATE_NONE,
        'known rename_target'               : _vc.STATE_MODIFIED,
        'known rename_source rename_target' : _vc.STATE_MODIFIED,
    }

    state_map_old = {
        '   ' : _vc.STATE_NORMAL,   # unchanged
        '  P' : _vc.STATE_MODIFIED, # patched (contents changed)
        '  U' : _vc.STATE_NONE,     # unknown (exists on the filesystem but not tracked)
        '  I' : _vc.STATE_IGNORED,  # ignored (exists on the filesystem but excluded by lua hook)
        '  M' : _vc.STATE_MISSING,  # missing (exists in the manifest but not on the filesystem)

        # Added files are not consistantly handled by all releases:
        #   0.28: although documented as invalid added files are tagged ' A '.
        #   0.26, 0.27: ???
        #   0.25: added files are tagged ' AP'.
        ' A ' : _vc.STATE_NEW,      # added (invalid, add should have associated patch)
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
        'RRM' : _vc.STATE_MISSING,  # rename source and target and target missing
    }

    def commit_command(self, message):
        return [self.CMD, "commit", "-m", message]

    def update_command(self):
        return [self.CMD, "update"]

    def add_command(self):
        return [self.CMD, "add"]

    def remove_command(self, force=0):
        return [self.CMD, "drop"]

    def revert_command(self):
        return [self.CMD, "revert"]

    def resolved_command(self):
        return [self.CMD, "resolved"]

    @classmethod
    def valid_repo(cls, path):
        return not _vc.call([cls.CMD, "list", "tags"], cwd=path)

    def get_working_directory(self, workdir):
        return self.root

    def get_path_for_repo_file(self, path, commit=None):
        if commit is None:
            commit = ""

        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")
        path = path[len(self.root) + 1:]

        command = [self.CMD, "cat", path]
        if commit:
            command.extend(["--revision", commit])

        process = subprocess.Popen(command,
                                   cwd=self.root, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        vc_file = process.stdout

        with tempfile.NamedTemporaryFile(prefix='meld-tmp', delete=False) as f:
            shutil.copyfileobj(vc_file, f)
        return f.name

    def _lookup_tree_cache(self, rootdir):
        log = logging.getLogger(__name__)

        while 1:
            try:
                entries = _vc.popen([self.CMD, "automate", "inventory"],
                                    cwd=self.root).read().split("\n")[:-1]
                break
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise

        # This handles interface versions from 6.0 to 9.0
        interface_version = float(
            _vc.popen([self.CMD, "automate", "interface_version"]).read())
        if interface_version < 6.0 or interface_version > 9.0:
            log.error("Unsupported monotone interface version; please "
                      "report any problems to the Meld mailing list.")

        # Terminate the final stanza, since basic stanzas are blank line
        # seperated with no blank line at the beginning or end.
        entries.append('')

        tree_state = {}
        stanza = {}
        for entry in entries:
            if entry != '':
                # This is part of a stanza and is structured:
                #     '   word "value1" "value2"'
                # We convert this into a dictionary of lists:
                #     stanza['word'] = [ 'value1', 'value2' ]
                entry = entry.strip().split()
                tag = entry[0]
                values = [i.strip('"') for i in entry[1:]]
                stanza[tag] = values
            else:
                fname = stanza['path'][0]
                if stanza['fs_type'][0] == 'directory':
                    fname = fname + '/'

                mstate = ' '.join(sorted(stanza['status']))
                if mstate in self.state_map_6:
                    if 'changes' in stanza:
                        state = _vc.STATE_MODIFIED
                    else:
                        state = self.state_map_6[mstate]
                        if state == _vc.STATE_ERROR:
                            log.warning("Invalid state '%s' reported for "
                                        "%s", mstate, fname)
                else:
                    state = _vc.STATE_ERROR
                    log.warning("Invalid state '%s' reported for %s "
                                "(version skew?)", mstate, fname)

                tree_state[os.path.join(self.root, fname)] = state

                # Clear the stanza ready for next iteration
                stanza = {}

        return tree_state

    def _get_dirsandfiles(self, directory, dirs, files):
        log = logging.getLogger(__name__)

        tree = self._get_tree_cache(directory)

        retfiles = []
        retdirs = []
        vcfiles = {}

        for path, state in tree.items():
            mydir, name = os.path.split(path)
            if path.endswith('/'):
                mydir, name = os.path.split(mydir)
            if mydir != directory:
                continue
            if path.endswith('/'):
                retdirs.append(_vc.Dir(path[:-1], name, state))
            else:
                retfiles.append(_vc.File(path, name, state))
            vcfiles[name] = 1
        for f, path in files:
            if f not in vcfiles:
                # if the ignore MT filter is not enabled these will crop up
                ignorelist = ['format', 'log', 'options', 'revision', 'work',
                              'debug', 'inodeprints']

                if f not in ignorelist:
                    log.warning("'%s' was not listed", f)

                # If not in the inventory it's not under version control.
                state = _vc.STATE_NONE
                retfiles.append(_vc.File(path, f, state))
        for d, path in dirs:
            if d not in vcfiles:
                # if the ignore MT filter is not enabled these will crop up
                ignorelist = ['MT']
                if d in ignorelist:
                    state = _vc.STATE_NONE
                else:
                    # monotone does not version (or inventory) directories
                    # so these are always normal
                    state = _vc.STATE_NORMAL
                retdirs.append(_vc.Dir(path, d, state))
        return retdirs, retfiles
