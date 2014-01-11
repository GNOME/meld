# Copyright (C) 2002-2008 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010, 2013 Kai Willadsen <kai.willadsen@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os

from gi.repository import Gtk

import meld.conf


def ui_file(filename):
    return os.path.join(meld.conf.DATADIR, "ui", filename)


class Component(object):
    """Base class for all Gtk.Builder created objects

    This class loads the UI file, autoconnects signals, and makes
    widgets available as attributes. The toplevel widget is stored as
    'self.widget'.

    The python object can be accessed from the widget itself via
    widget.pygobject, which is sadly sometimes necessary.
    """

    def __init__(self, filename, root, extra=None):
        """Load the widgets from the node 'root' in file 'filename'"""
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(meld.conf.__package__)
        objects = [root] + extra if extra else [root]
        filename = ui_file(filename)
        self.builder.add_objects_from_file(filename, objects)
        self.builder.connect_signals(self)
        self.widget = getattr(self, root)
        self.widget.pyobject = self

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
