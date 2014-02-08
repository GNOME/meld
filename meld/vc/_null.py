# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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

import shutil
import tempfile

from meld.vc import _vc


class Vc(_vc.Vc):

    CMD = None
    NAME = ""
    VC_DIR = "."

    def lookup_files(self, dirs, files, directory=None):
        dirs = [_vc.Dir(d[1], d[0], _vc.STATE_NONE) for d in dirs]
        files = [_vc.File(f[1], f[0], _vc.STATE_NONE) for f in files]
        return dirs, files

    def get_path_for_repo_file(self, path, commit=None):
        with tempfile.NamedTemporaryFile(prefix='meld-tmp', delete=False) as f:
            with open(path, 'r') as vc_file:
                shutil.copyfileobj(vc_file, f)
        return f.name
