### Copyright (C) 2002-2008 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2010, 2013 Kai Willadsen <kai.willadsen@gmail.com>

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

import os

import gtk

import meld.paths

# Import support module to get all builder-constructed widgets in the namespace
from meld.ui import gladesupport

# FIXME: duplicate defn in bin/meld
locale_domain = "meld"

def ui_file(filename):
    return os.path.join(meld.paths._share_dir, "ui", filename)


class Component(object):
    """Base class for all gtk.Builder created objects

    This class loads the UI file, autoconnects signals, and makes
    widgets available as attributes. The toplevel widget is stored as
    'self.widget'.

    The python object can be accessed from the widget itself via
    widget.get_data("pygobject"), which is sadly sometimes necessary.
    """

    def __init__(self, filename, root, extra=None):
        """Load the widgets from the node 'root' in file 'filename'"""
        self.builder = gtk.Builder()
        self.builder.set_translation_domain(locale_domain)
        objects = [root] + extra if extra else [root]
        filename = ui_file(filename)
        self.builder.add_objects_from_file(filename, objects)
        self.builder.connect_signals(self)
        self.widget = getattr(self, root)
        self.widget.set_data("pyobject", self)

    def __getattr__(self, key):
        """Allow UI builder widgets to be accessed as self.widgetname"""
        widget = self.builder.get_object(key)
        if widget:
            setattr(self, key, widget)
            return widget
        raise AttributeError(key)

    def map_widgets_into_lists(self, widgetnames):
        """Put sequentially numbered widgets into lists.

        Given an object with widgets self.button0, self.button1, ...,
        after a call to object.map_widgets_into_lists(["button"])
        object.button == [self.button0, self.button1, ...]
        """
        for item in widgetnames:
            i, lst = 0, []
            while 1:
                key = "%s%i" % (item, i)
                try:
                    val = getattr(self, key)
                except AttributeError:
                    break
                lst.append(val)
                i += 1
            setattr(self, item, lst)
