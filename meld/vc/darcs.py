# -*- coding: utf-8 -*- 

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
#Copyright (c) 2005 Ali Afshar <aafshar@gmail.com>

#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:

#The above copyright notice and this permission notice shall be included in
#all copies or substantial portions of the Software.

#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

import errno
import os
import shutil
import subprocess
import tempfile

from . import _vc


class Vc(_vc.CachedVc):

    CMD = "darcs"
    NAME = "Darcs"
    VC_DIR = "_darcs"
    state_map = {
        "a": _vc.STATE_NONE,
        "A": _vc.STATE_NEW,
        "M": _vc.STATE_MODIFIED,
        "C": _vc.STATE_CONFLICT,
        "R": _vc.STATE_REMOVED,
    }

    def commit_command(self, message):
        return [self.CMD, "record",
                "--skip-long-comment",
                "--repodir=%s" % self.root,
                "-a",
                "-m", message]

    def update_command(self):
        # This will not work while passing the files parameter after it
        # This hack allows you to update in the root directory
        return [self.CMD, "pull", "-a", "-p"]

    def add_command(self):
        return [self.CMD, "add"]

    def remove_command(self, force=0):
        return [self.CMD, "remove"]
 
    def revert_command(self):
        # will not work, since darcs needs interaction it seems
        return [self.CMD, "revert", "-a"]

    def resolved_command(self):
        # untested
        return [self.CMD, "resolve"]

    def valid_repo(self):
        if _vc.call([self.CMD, "query", "tags"], cwd=self.root):
            return False
        else:
            return True

    def get_working_directory(self, workdir):
        return self.root

    def get_path_for_repo_file(self, path, commit=None):
        if commit is not None:
            raise NotImplementedError()

        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")
        path = path[len(self.root) + 1:]

        process = subprocess.Popen([self.CMD, "show", "contents",
                                    "--repodir=" + self.root, path],
                                   cwd=self.root, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        vc_file = process.stdout

        # Error handling here involves doing nothing; in most cases, the only
        # sane response is to return an empty temp file.

        with tempfile.NamedTemporaryFile(prefix='meld-tmp', delete=False) as f:
            shutil.copyfileobj(vc_file, f)
        return f.name

    def _get_dirsandfiles(self, directory, dirs, files):
        whatsnew = self._get_tree_cache(directory)
        retfiles, retdirs = (self._get_statuses(whatsnew, files, _vc.File),
                             self._get_statuses(whatsnew, dirs, _vc.Dir))
        return retfiles, retdirs

    def _lookup_tree_cache(self, rootdir):
        non_boring = self._get_whatsnew()
        boring = self._get_whatsnew(boring=True)
        for path in boring:
            if not path in non_boring:
                non_boring[path] = _vc.STATE_IGNORED
        return non_boring

    def _get_whatsnew(self, boring=False):
        whatsnew = {}
        commandline = [self.CMD, "whatsnew", "--summary", "-l", "--repodir=" + self.root]
        if boring:
            commandline.append("--boring")
        while 1:
            try:
                p = _vc.popen(commandline)
                break
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise
        for line in p:
            if line.startswith('No changes!'):
                continue
            elements = line.split()
            if len(elements) > 1:
                if elements[1] == '->':
                    status = _vc.STATE_NEW
                    filename = elements.pop()
                else:
                    status = self.state_map[elements.pop(0)]
                    filename = elements.pop(0)
                filepath = os.path.join(self.root,
                                        os.path.normpath(filename))
                whatsnew[filepath] = status
        return whatsnew

    def _get_statuses(self, whatsnew, files, fstype):
        rets = []
        for filename, path in files:
            state = _vc.STATE_NORMAL
            if path in whatsnew:
                state = whatsnew[path]
            vcfile = fstype(path, filename, state)
            if filename != self.VC_DIR:
                rets.append(vcfile)
        return rets
