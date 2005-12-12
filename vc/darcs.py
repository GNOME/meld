# -*- coding: utf-8 -*- 

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
#Copyright (c) 2005 Ali Afshar aafshar@gmail.com

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

import os
import errno
import _vc

STATES = {
    "a": _vc.STATE_NONE,
    "A": _vc.STATE_NEW,
    "M": _vc.STATE_MODIFIED,
    "C": _vc.STATE_CONFLICT,
    "R": _vc.STATE_REMOVED
}

class Vc(_vc.Vc):

    CMD = "darcs"
    NAME = "Darcs"
    PATCH_STRIP_NUM = 1
    PATCH_INDEX_RE = "--- old.+?/(.+?)\\t+.*[0-9]{4}$"

    def __init__(self, location):
        self._cachetime = None
        while location != "/":
            if os.path.isdir( "%s/_darcs" % location):
                self.root = location
                return
            location = os.path.dirname(location)
        raise ValueError()

    def commit_command(self, message):
        return [self.CMD, "record",
                "--skip-long-comment",
                "--repodir=%s" % self.root,
                "-a",
                "-m", message]

    def diff_command(self):
        return [self.CMD, "diff", "-u",
                "--repodir=%s" % self.root]

    def update_command(self):
        # This will not work while passing the files parameter after it
        # This hack allows you to update in the root directory
        return [self.CMD, "pull", "-a", "-p"]

    def add_command(self, binary=0):
        return [self.CMD, "add"]

    def remove_command(self, force=0):
        return [self.CMD, "remove"]
 
    def revert_command(self):
        # will not work, since darcs needs interaction it seems
        return [self.CMD, "revert", "-a"]

    def get_working_directory(self, workdir):
        return self.root
 
    def cache_inventory(self, rootdir):
        self._cached_statuses = self._calculate_statuses()

    def uncache_inventory(self):
        self._cached_statuses = None

    def lookup_files(self, dirs, files):
        "files is array of (name, path). assume all files in same dir"
        directory = self._get_directoryname(files, dirs)
        if directory is None:
            return [], []
        else:
            whatsnew = self._get_cached_statuses()
            retfiles, retdirs = (self._get_statuses(whatsnew, files, _vc.File),
                                 self._get_statuses(whatsnew, dirs, _vc.Dir))
            return retfiles, retdirs

    def _get_cached_statuses(self):
        if self._cached_statuses is None:
            self._cached_statuses = self._calculate_statuses()
        return self._cached_statuses
    
    def _calculate_statuses(self):
        non_boring = self._get_whatsnew()
        boring = self._get_whatsnew(boring=True)
        for path in boring:
            if not path in non_boring:
                non_boring[path] = _vc.STATE_IGNORED
        return non_boring

    def _get_whatsnew(self, boring=False):
        whatsnew = {}
        commandline = ('%s whatsnew --summary -l --repodir=%s' %
                      (self.CMD, self.root))
        if boring:
            commandline = '%s --boring' % commandline
        while 1:
            try:
                p = os.popen(commandline)
                break
            except OSError, e:
                if e.errno != errno.EAGAIN:
                    raise
        for line in p:
            elements = line.split()
            if len(elements) > 1:
                if elements[1] == '->':
                    status = _vc.STATE_NEW
                    filename = elements.pop()
                else:
                    status = STATES[elements.pop(0)]
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
            if filename != "_darcs":
                rets.append(vcfile)
        return rets

    def _get_directoryname(self, files, dirs):
        directory = None
        if len(files):
            directory = os.path.dirname(files[0][1])
        elif len(dirs):
            directory = os.path.dirname(dirs[0][1])
        return directory

