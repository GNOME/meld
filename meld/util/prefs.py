### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2011-2012 Kai Willadsen <kai.willadsen@gmail.com>

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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
### USA.

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
# settings are persistent
p.color = "blue"

"""

import ast
import os
import sys

import glib


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

# types of values allowed
BOOL = "bool"
INT = "int"
STRING = "string"
FLOAT = "float"
LIST = "list"


class GConfPreferences(object):
    """Persistent preferences object that handles preferences via gconf.

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
            gval = self._gconf.get_without_default("%s/%s" % (rootkey, key))
            if gval is not None:
                if value.type == LIST:
                    # We only use/support str lists at the moment
                    val_tuple = getattr(gval, "get_%s" % value.type)()
                    value.current = [v.get_string() for v in val_tuple]
                else:
                    value.current = getattr(gval, "get_%s" % value.type)()

    def __getattr__(self, attr):
        return self._prefs[attr].current

    def get_default(self, attr):
        return self._prefs[attr].default

    def __setattr__(self, attr, val):
        value = self._prefs[attr]
        if value.current != val:
            value.current = val
            setfunc = getattr(self._gconf, "set_%s" % value.type)
            if value.type == LIST:
                # We only use/support str lists at the moment
                setfunc("%s/%s" % (self._rootkey, attr), gconf.VALUE_STRING,
                        val)
            else:
                setfunc("%s/%s" % (self._rootkey, attr), val)
            try:
                for l in self._listeners:
                    l(attr, val)
            except StopIteration:
                pass

    def _on_preference_changed(self, client, timestamp, entry, extra):
        attr = entry.key[entry.key.rfind("/") + 1:]
        try:
            value = self._prefs[attr]
        # Changes for unknown keys are ignored
        except KeyError:
            pass
        else:
            if entry.value is not None:
                val = getattr(entry.value, "get_%s" % value.type)()
                if value.type == LIST:
                    # We only use/support str lists at the moment
                    val = [v.get_string() for v in val]
                setattr(self, attr, val)
            # Setting a value to None deletes it and uses the default value
            else:
                setattr(self, attr, value.default)

    def notify_add(self, callback):
        """Register a callback to be called when a preference changes.

        callback : a callable object which take two parameters, 'attr' the
                   name of the attribute changed and 'val' the new value.
        """
        self._listeners.append(callback)

    def __str__(self):
        prefs_entries = []
        for k, v in self._prefs.items():
            prefs_entries.append("%s %s %s" % (k, v.type, str(v.current)))
        return "\n".join(prefs_entries)


class ConfigParserPreferences(object):
    """Persistent preferences object that handles preferences via ConfigParser.

    This preferences implementation is provided as a fallback for gconf-less
    platforms. The ConfigParser library is included in Python and should be
    available everywhere. The biggest drawbacks to this backend are lack of
    access to desktop-wide settings, and lack of external change notification.
    """

    def __init__(self, rootkey, initial):
        """Create a preferences object.

        Settings are initialised with 'initial' and then overriden
        from values in the ConfigParser database if available.

        rootkey : unused (retained for compatibility with existing gconf API)
        initial : a dictionary of string to Value objects.
        """
        self.__dict__["_parser"] = configparser.SafeConfigParser()
        self.__dict__["_listeners"] = []
        self.__dict__["_prefs"] = initial
        self.__dict__["_type_mappings"] = {
            BOOL: self._parser.getboolean,
            INT: self._parser.getint,
            STRING: self._parser.get,
            FLOAT: self._parser.getfloat,
            LIST: self._parser.get,
        }

        if sys.platform == "win32":
            config_dir = glib.get_user_config_dir().decode('utf8')
            pref_dir = os.path.join(config_dir, "Meld")
        else:
            pref_dir = os.path.join(glib.get_user_config_dir(), "meld")

        if not os.path.exists(pref_dir):
            os.makedirs(pref_dir)

        self.__dict__["_file_path"] = os.path.join(pref_dir, "meldrc.ini")

        try:
            config_file = open(self._file_path, "r")
            try:
                self._parser.readfp(config_file)
            finally:
                config_file.close()
        except IOError:
            # One-way move of old preferences
            old_path = os.path.join(os.path.expanduser("~"), ".meld")
            old_file_path = os.path.join(old_path, "meldrc.ini")
            if os.path.exists(old_file_path):
                try:
                    config_file = open(old_file_path, "r")
                    try:
                        self._parser.readfp(config_file)
                    finally:
                        config_file.close()
                    new_config_file = open(self._file_path, "w")
                    try:
                        self._parser.write(new_config_file)
                    finally:
                        new_config_file.close()
                except IOError:
                    pass

        for key, value in self._prefs.items():
            if self._parser.has_option("DEFAULT", key):
                val = self._type_mappings[value.type]("DEFAULT", key)
                if value.type == "list":
                    value.current = ast.literal_eval(val)
                else:
                    value.current = val

    def __getattr__(self, attr):
        return self._prefs[attr].current

    def get_default(self, attr):
        return self._prefs[attr].default

    def __setattr__(self, attr, val):
        value = self._prefs[attr]
        if value.current != val:
            value.current = val
            self._parser.set(None, attr, str(val))

            try:
                fp = open(self._file_path, "w")
                try:
                    self._parser.write(fp)
                finally:
                    fp.close()
            except IOError:
                pass

            try:
                for l in self._listeners:
                    l(attr, val)
            except StopIteration:
                pass

    def notify_add(self, callback):
        """Register a callback to be called when a preference changes.

        callback : a callable object which take two parameters, 'attr' the
                   name of the attribute changed and 'val' the new value.
        """
        self._listeners.append(callback)

    def __str__(self):
        prefs_entries = []
        for k, v in self._prefs.items():
            prefs_entries.append("%s %s %s" % (k, v.type, str(v.current)))
        return "\n".join(prefs_entries)


force_ini = os.path.exists(
    os.path.join(glib.get_user_config_dir(), 'meld', 'use-rc-prefs'))
skip_gconf = sys.platform == 'win32' or force_ini
# Prefer gconf, falling back to configparser
try:
    if skip_gconf:
        raise ImportError
    import gconf
    # Verify that gconf is actually working (bgo#666136)
    client = gconf.client_get_default()
    key = '/apps/meld/gconf-test'
    client.set_int(key, os.getpid())
    client.unset(key)
    Preferences = GConfPreferences
except (ImportError, glib.GError):
    try:
        import configparser
    except ImportError:
        import ConfigParser as configparser
    Preferences = ConfigParserPreferences
