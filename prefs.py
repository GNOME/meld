### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>

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

"""Module to help implement 'instant-apply' preferences.

Usage:

import prefs
defaults = {
    "colour" : prefs.Value(prefs.STRING, "red")
    "size" : prefs.Value(prefs.INT, 10)
}

p = prefs.Preferences("/apps/myapp", defaults)
# use variables as if they were normal attributes.
draw(p.colour, p.size)
# settings are persistent. (saved in gconf)
p.color = "blue"

"""

class Value(object):
    """Represents a settable preference.
    """

    __slots__ = ["type", "default", "current"]

    def __init__(self, t, d):
        """Create a value.

        t : a string : one of ("bool", "int", "string")
        d : the default value, also the initial value
        """
        self.type = t
        self.default = d
        self.current = d

# maybe fall back to ConfigParser if gconf is unavailable.
import gconf

# types of values allowed
BOOL = "bool"
INT = "int"
STRING = "string"
FLOAT = "float"
# LIST = "list"
# PAIR = "pair"

##

class Preferences(object):
    """Persistent preferences object.

    Example:
    import prefs
    defaults = {"spacing": prefs.Value(prefs.INT, 4),
                "font": prefs.Value(prefs.STRING, "monospace") }
    p = prefs.Prefs("myapp", defaults)
    print p.font
    p.font = "sans" # written to gconf too
    p2 = prefs.Prefs("myapp", defaults)
    print p.font # prints "sans"
    """

    def __init__(self, rootkey, initial):
        """Create a preferences object.

        Settings are initialised with 'initial' and then overriden
        from values in the gconf database if available.

        rootkey : the root gconf key where the values will be stored
        initial : a dictionary of string to Value objects.
        """
        self.__dict__["_gconf"] = gconf.client_get_default()
        self.__dict__["_listeners"] = []
        self.__dict__["_rootkey"] = rootkey
        self.__dict__["_prefs"] = initial
        self._gconf.add_dir(rootkey, gconf.CLIENT_PRELOAD_NONE)
        self._gconf.notify_add(rootkey, self._on_preference_changed)
        for key, value in self._prefs.items():
            gval = self._gconf.get_without_default("%s/%s" % (rootkey, key) )
            if gval != None:
                value.current = getattr( gval, "get_%s" % value.type )()

    def __getattr__(self, attr):
        return self._prefs[attr].current

    def get_default(self, attr):
        return self._prefs[attr].default

    def __setattr__(self, attr, val):
        value = self._prefs[attr]
        if value.current != val:
            value.current = val
            setfunc = getattr(self._gconf, "set_%s" % value.type)
            setfunc("%s/%s" % (self._rootkey, attr), val)
            try:
                for l in self._listeners:
                    l(attr,val)
            except StopIteration:
                pass

    def _on_preference_changed(self, client, timestamp, entry, extra):
        attr = entry.key[entry.key.rfind("/") + 1:]
        try:
            valuestruct = self._prefs[attr]
        except KeyError: # unknown key, we don't care about it
            pass
        else:
            if entry.value != None: # value has changed
                newval = getattr(entry.value, "get_%s" % valuestruct.type)()
                setattr( self, attr, newval)
            else: # value has been deleted
                setattr( self, attr, valuestruct.default )

    def notify_add(self, callback):
        """Register a callback to be called when a preference changes.

        callback : a callable object which take two parameters, 'attr' the
                   name of the attribute changed and 'val' the new value.
        """
        self._listeners.append(callback)

    def dump(self):
        """Print all preferences.
        """
        for k,v in self._prefs.items():
            print k, v.type, v.current

