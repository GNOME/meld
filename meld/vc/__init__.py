# -*- coding: utf-8 -*-
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

import importlib
from . import _null

# FIXME: This is a horrible hack to help cx_Freeze pick up these plugins when
# freezing the distributable package.
from . import git, mercurial, bzr, svn, darcs

# Tuple with module name and vc.NAME field, ordered according to best-guess
# as to which VC a user is likely to want by default in a multiple-VC situation
vc_names = (
    "git",
    "mercurial",
    "bzr",
    "svn",
    "darcs",
)

_plugins = [importlib.import_module("." + vc, __package__) for vc in vc_names]


def get_plugins_metadata():
    ret = []
    for p in _plugins:
        # Some plugins have VC_DIR=None until instantiated
        if p.Vc.VC_DIR:
            ret.append(p.Vc.VC_DIR)
        # Most plugins have VC_METADATA=None
        if p.Vc.VC_METADATA:
            ret.extend(p.Vc.VC_METADATA)
    return ret


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
    max_depth = 0
    for plugin in _plugins:
        root, location = plugin.Vc.is_in_repo(location)
        if not root:
            continue

        # Choose the deepest root we find, unless it's from a VC that
        # doesn't walk; these can be spurious as the real root may be
        # much higher up in the tree.
        depth = len(root)
        if depth > max_depth and plugin.Vc.VC_ROOT_WALK:
            vcs, max_depth = [], depth
        if depth >= max_depth:
            vcs.append(plugin.Vc)

    if not vcs:
        # No plugin recognized that location, fallback to _null
        return [_null.Vc]

    return vcs
