# Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2012 Kai Willadsen <kai.willadsen@gmail.com>

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

from . import bzr, cvs, darcs, git, mercurial, svn

# Tuple of plugins, ordered according to best-guess as to which VC a
# user is likely to want by default in a multiple-VC situation.
VC_PLUGINS = (git, mercurial, bzr, svn, darcs, cvs)


def get_vcs(location):
    """Pick only the Vcs with the longest repo root

       Some VC plugins search their repository root
       by walking the filesystem upwards its root
       and now that we display multiple VCs in the
       same directory, we must filter those other
       repositories that are located in the search
       path towards "/" as they are not relevant
       to the user.
    """

    vcs = []
    for plugin in VC_PLUGINS:
        root, location = plugin.Vc.is_in_repo(location)
        enabled = root is not None
        vcs.append((plugin.Vc, enabled))

    return vcs
