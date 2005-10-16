### Copyright (C) 2002-2004 Stephen Kennedy <stevek@gnome.org>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

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

def Vc(location):
    for plugin in _plugins:
        try:
            return plugin.Vc(location)
        except ValueError:
            pass
    return _null.Vc(location)
