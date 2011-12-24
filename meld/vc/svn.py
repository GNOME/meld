### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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
import errno
import _vc
import xml.etree.ElementTree as ElementTree


class Vc(_vc.CachedVc):

    CMD = "svn"
    NAME = "Subversion"
    VC_DIR = ".svn"
    VC_ROOT_WALK = False
    PATCH_INDEX_RE = "^Index:(.*)$"
    state_map = {
        "unversioned": _vc.STATE_NONE,
        "added": _vc.STATE_NEW,
        "normal": _vc.STATE_NORMAL,
        "missing": _vc.STATE_MISSING,
        "ignored": _vc.STATE_IGNORED,
        "modified": _vc.STATE_MODIFIED,
        "deleted": _vc.STATE_REMOVED,
        "conflicted": _vc.STATE_CONFLICT,
    }

    def commit_command(self, message):
        return [self.CMD,"commit","-m",message]
    def diff_command(self):
        if hasattr(self, "external_diff"):
            return [self.CMD, "diff", "--diff-cmd", self.external_diff]
        else:
            return [self.CMD, "diff"]

    def update_command(self):
        return [self.CMD,"update"]
    def add_command(self, binary=0):
        return [self.CMD,"add"]
    def remove_command(self, force=0):
        return [self.CMD,"rm","--force"]
    def revert_command(self):
        return [self.CMD,"revert"]
    def resolved_command(self):
        return [self.CMD,"resolved"]
    def valid_repo(self):
        if _vc.call([self.CMD, "info"], cwd=self.root):
            return False
        else:
            return True

    def switch_to_external_diff(self):
        self.external_diff = "diff"

    def _update_tree_state_cache(self, path, tree_state):
        while 1:
            try:
                status_cmd = [self.CMD, "status", "-v", "--xml", path]
                tree = ElementTree.parse(_vc.popen(status_cmd))
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise

        for target in tree.findall("target") + tree.findall("changelist"):
            for entry in (t for t in target.getchildren() if t.tag == "entry"):
                path = entry.attrib["path"]
                if path == "":
                    continue
                for status in (e for e in entry.getchildren() \
                               if e.tag == "wc-status"):
                    item = status.attrib["item"]
                    if item == "":
                        continue
                    rev = None
                    if "revision" in status.attrib:
                        rev = status.attrib["revision"]
                    mydir, name = os.path.split(path)
                    if mydir not in tree_state:
                        tree_state[mydir] = {}
                    tree_state[mydir][name] = (item, rev)

    def _lookup_tree_cache(self, rootdir):
        # Get a list of all files in rootdir, as well as their status
        tree_state = {}
        self._update_tree_state_cache(rootdir, tree_state)
        return tree_state

    def update_file_state(self, path):
        tree_state = self._get_tree_cache(os.path.dirname(path))
        self._update_tree_state_cache(path, tree_state)

    def _get_dirsandfiles(self, directory, dirs, files):
        tree = self._get_tree_cache(directory)

        if not directory in tree:
            return [], []

        retfiles = []
        retdirs = []

        dirtree = tree[directory]

        for name in sorted(dirtree.keys()):
            svn_state, rev = dirtree[name]
            path = os.path.join(directory, name)

            isdir = os.path.isdir(path)
            options = ""
            if isdir:
                if os.path.exists(path):
                    state = _vc.STATE_NORMAL
                else:
                    state = _vc.STATE_MISSING
                # svn adds the directory reported to the status list we get.
                if name != directory:
                    retdirs.append( _vc.Dir(path,name,state) )
            else:
                state = self.state_map.get(svn_state, _vc.STATE_NONE)
                retfiles.append( _vc.File(path, name, state, rev, "", options) )

        return retdirs, retfiles
