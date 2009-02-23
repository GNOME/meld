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
import _null

def load_plugins():
    _vcdir = os.path.dirname(os.path.abspath(__file__))
    ret = []
    for plugin in glob.glob("%s/[a-z]*.py" % _vcdir):
        modname = "vc.%s" % os.path.basename(plugin)[:-3]
        ret.append( __import__(modname, globals(), locals(), "*") )
    return ret
_plugins = load_plugins()

def default_plugin_order(vcs):
    # Pick the Vc with the longest repo root
    return max(vcs, key=lambda repo: len(repo.root))

def Vc(location, ordering_func = default_plugin_order):
    vcs = []
    for plugin in _plugins:
        try:
            vcs.append(plugin.Vc(location))
        except ValueError:
            pass

    if not vcs:
        # No plugin recognized that location, fallback to _null
        vc = _null.Vc(location)
    elif len(vcs) == 1:
        # No need to launch a potentially GUI/interactive chooser
        vc = vcs[0]
    else:
        # User gets to pick one, eventually
        vc = ordering_func(vcs)

    return vc
