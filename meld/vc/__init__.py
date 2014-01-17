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
import glob
from . import _null
from ._vc import DATA_NAME, DATA_STATE, DATA_REVISION, DATA_OPTIONS


def load_plugins():
    _vcdir = os.path.dirname(os.path.abspath(__file__))
    ret = []
    for plugin in sorted(glob.glob(os.path.join(_vcdir, "[a-z]*.py"))):
        modname = "meld.vc.%s" % os.path.basename(os.path.splitext(plugin)[0])
        ret.append( __import__(modname, globals(), locals(), "*") )
    return ret
_plugins = load_plugins()

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

vc_sort_order = (
    "Git",
    "Bazaar",
    "Mercurial",
    "Fossil",
    "Monotone",
    "Darcs",
    "SVK",
    "Subversion",
    "Subversion 1.7",
    "CVS",
)

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
    for plugin in _plugins:
        try:
            vc = plugin.Vc(location)
        except ValueError:
            continue
        vcs.append(vc)

    # Choose the deepest root we find, unless it's from a VC that
    # doesn't walk; these can be spurious as the real root may be
    # much higher up in the tree.
    root_walk_lengths = [len(vc.root) for vc in vcs if vc.VC_ROOT_WALK]
    max_depth = max(root_walk_lengths or [0])
    vcs = [vc for vc in vcs if not vc.VC_ROOT_WALK or
           (len(vc.root) == max_depth and vc.VC_ROOT_WALK)]

    if not vcs:
        return [_null.Vc(location)]

    vc_sort_key = lambda v: vc_sort_order.index(v.NAME)
    vcs.sort(key=vc_sort_key)

    return vcs
