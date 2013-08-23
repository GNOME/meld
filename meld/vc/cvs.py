# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2013 Kai Willadsen <kai.willadsen@gmail.com>

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

import logging
import os
import re
import shutil
import tempfile
import time

from meld import misc
from . import _vc

log = logging.getLogger(__name__)


class FakeErrorStream(object):
    def error(self, error):
        pass


class Vc(_vc.Vc):
    CMD = "cvs"
    # CVSNT is a drop-in replacement for CVS; if found, it is used instead
    ALT_CMD = "cvsnt"
    NAME = "CVS"
    VC_DIR = "CVS"
    VC_ROOT_WALK = False
    PATCH_STRIP_NUM = 0
    PATCH_INDEX_RE = "^Index:(.*)$"

    VC_COLUMNS = (_vc.DATA_NAME, _vc.DATA_STATE, _vc.DATA_REVISION,
                  _vc.DATA_OPTIONS)

    def __init__(self, location):
        super(Vc, self).__init__(location)
        if not _vc.call(["which", self.ALT_CMD]):
            self.CMD = self.ALT_CMD

    def commit_command(self, message):
        return [self.CMD, "commit", "-m", message]

    def update_command(self):
        return [self.CMD, "update"]

    def remove_command(self, force=0):
        return [self.CMD, "rm", "-f"]

    def revert_command(self):
        return [self.CMD, "update", "-C"]

    @classmethod
    def valid_repo(cls, path):
        return os.path.exists(os.path.join(path, cls.VC_DIR, "Entries"))

    def get_path_for_repo_file(self, path, commit=None):
        if commit is not None:
            raise NotImplementedError

        if not path.startswith(self.root + os.path.sep):
            raise _vc.InvalidVCPath(self, path, "Path not in repository")
        path = path[len(self.root) + 1:]

        diffiter = misc.read_pipe_iter([self.CMD, "diff", "-u", path],
                                       FakeErrorStream(), workdir=self.root)
        patch = None
        while patch is None:
            patch = next(diffiter)
        status = next(diffiter)

        tmpdir = tempfile.mkdtemp("-meld")
        destfile = os.path.join(tmpdir, os.path.basename(path))

        try:
            shutil.copyfile(os.path.join(self.root, path), destfile)
        except IOError:
            # For missing files, create a new empty file
            open(destfile, "w").close()

        patchcmd = ["patch", "-R", "-d", tmpdir]
        try:
            with open(os.devnull, "w") as NULL:
                result = misc.write_pipe(patchcmd, patch, error=NULL)
                assert result == 0

            with open(destfile) as patched_file:
                with tempfile.NamedTemporaryFile(prefix='meld-tmp',
                                                 delete=False) as temp_file:
                    shutil.copyfileobj(patched_file, temp_file)

            return temp_file.name
        except (OSError, AssertionError):
            return
        finally:
            if os.path.exists(destfile):
                os.remove(destfile)
            if os.path.exists(destfile):
                os.rmdir(tmpdir)

    def add(self, runner, files):
        # CVS needs to add folders from their immediate parent
        dirs = [s for s in files if os.path.isdir(s)]
        files = [s for s in files if os.path.isfile(s)]
        command = [self.CMD, 'add']
        for path in dirs:
            runner(command, [path], refresh=True,
                   working_dir=os.path.dirname(path))
        if files:
            runner(command, files, refresh=True)

    def _get_dirsandfiles(self, directory, dirs, files):
        vc_path = os.path.join(directory, self.VC_DIR)

        try:
            with open(os.path.join(vc_path, "Entries")) as f:
                entries = f.read()
            # poor mans universal newline
            entries = entries.replace("\r", "\n").replace("\n\n", "\n")
         # No CVS directory
        except IOError as e:
            d = [_vc.Dir(x[1], x[0], _vc.STATE_NONE) for x in dirs]
            f = [_vc.File(x[1], x[0], _vc.STATE_NONE) for x in files]
            return d, f

        try:
            with open(os.path.join(vc_path, "Entries.Log")) as f:
                logentries = f.read()
        except IOError as e:
            pass
        else:
            matches = re.findall("^([AR])\s*(.+)$(?m)", logentries)
            toadd = []
            for match in matches:
                if match[0] == "A":
                    toadd.append(match[1])
                elif match[0] == "R":
                    try:
                        toadd.remove(match[1])
                    except ValueError:
                        pass
                else:
                    log.warning("Unknown Entries.Log line '%s'", match[0])
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
            if isdir:
                if os.path.exists(path):
                    state = _vc.STATE_NORMAL
                else:
                    state = _vc.STATE_MISSING
                retdirs.append(_vc.Dir(path, name, state))
            else:
                if rev.startswith("-"):
                    state = _vc.STATE_REMOVED
                elif date == "dummy timestamp":
                    if rev[0] == "0":
                        state = _vc.STATE_NEW
                    else:
                        state = _vc.STATE_ERROR
                elif date == "dummy timestamp from new-entry":
                    state = _vc.STATE_MODIFIED
                else:
                    date_sub = lambda x: "%3i" % int(x.group())
                    date = re.sub(r"\s*\d+", date_sub, date, 1)
                    plus = date.find("+")
                    if plus >= 0:
                        state = _vc.STATE_CONFLICT
                        try:
                            txt = open(path, "U").read()
                        except IOError:
                            pass
                        else:
                            if txt.find("\n=======\n") == -1:
                                state = _vc.STATE_MODIFIED
                    else:
                        try:
                            mtime = os.stat(path).st_mtime
                        except OSError:
                            state = _vc.STATE_MISSING
                        else:
                            if time.asctime(time.gmtime(mtime)) == date:
                                state = _vc.STATE_NORMAL
                            else:
                                state = _vc.STATE_MODIFIED
                retfiles.append(_vc.File(path, name, state, rev, options))
        # known
        cvsfiles = [x[1] for x in matches]
        # ignored
        try:
            with open(os.path.join(os.environ["HOME"], ".cvsignore")) as f:
                ignored = f.read().split()
        except (IOError, KeyError):
            ignored = []
        try:
            with open(os.path.join(directory, ".cvsignore")) as f:
                ignored += f.read().split()
        except IOError:
            pass

        if len(ignored):
            try:
                regexes = [misc.shell_to_regex(i)[:-1] for i in ignored]
                ignore_re = re.compile("(" + "|".join(regexes) + ")")
            except re.error as err:
                log.warning(
                    "Error converting %s to a regular expression: %s'" %
                    (",".join(ignored), err))
        else:
            class dummy(object):
                def match(self, *args):
                    return None
            ignore_re = dummy()

        for f, path in files:
            if f not in cvsfiles:
                state = (ignore_re.match(f) is None and _vc.STATE_NONE or
                         _vc.STATE_IGNORED)
                retfiles.append(_vc.File(path, f, state))
        for d, path in dirs:
            if d not in cvsfiles:
                state = (ignore_re.match(d) is None and _vc.STATE_NONE or
                         _vc.STATE_IGNORED)
                retdirs.append(_vc.Dir(path, d, state))

        return retdirs, retfiles
