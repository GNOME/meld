### Copyright (C) 2002-2008 Stephen Kennedy <stevek@gnome.org>

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

"""Utility class for working with glade files.
"""

import gtk
import gtk.glade
import historyentry
import re

class Component(object):
    """Base class for all glade objects.

    This class handles loading the xml glade file and autoconnects
    all signals in the glade file.

    The handle to the xml file is stored in 'self.xml'. The
    toplevel widget is stored in 'self.widget'.

    In addition it calls widget.set_data("pyobject", self) - this
    allows us to get the python object given only the 'raw' gtk+
    object, which is sadly sometimes necessary.
    """

    def __init__(self, filename, root, override={}):
        """Load the widgets from the node 'root' in file 'filename'.
        """
        gtk.glade.set_custom_handler(self.get_custom_handler)
        self.xml = gtk.glade.XML(filename, root, typedict=override)
        self.xml.signal_autoconnect(self)
        self.widget = getattr(self, root)
        self.widget.set_data("pyobject", self)

    def __getattr__(self, key):
        """Allow glade widgets to be accessed as self.widgetname.
        """
        widget = self.xml.get_widget(key)
        if widget: # cache lookups
            setattr(self, key, widget)
            return widget
        raise AttributeError(key)

    def map_widgets_into_lists(self, widgetnames):
        """Put sequentially numbered widgets into lists.
        
        e.g. If an object had widgets self.button0, self.button1, ...,
        then after a call to object._map_widgets_into_lists(["button"])
        object has an attribute self.button == [self.button0, self.button1, ...]."
        """
        for item in widgetnames:
            setattr(self,item, [])
            lst = getattr(self,item)
            i = 0
            while 1:
                key = "%s%i"%(item,i)
                try:
                    val = getattr(self, key)
                except AttributeError:
                    break
                lst.append(val)
                i += 1

    # Taken from the pygtk FAQ
    def get_custom_handler(self, glade, function_name, widget_name,
                           str1, str2, int1, int2):
        """
        Generic handler for creating custom widgets, used to
        enable custom widgets.

        The custom widgets have a creation function specified in design time.
        Those creation functions are always called with str1,str2,int1,int2 as
        arguments, that are values specified in design time.

        This handler assumes that we have a method for every custom widget
        creation function specified in glade.

        If a custom widget has create_foo as creation function, then the
        method named create_foo is called with str1,str2,int1,int2 as arguments.
        """
        if hasattr(self, function_name):
            handler = getattr(self, function_name)
            return handler(str1, str2, int1, int2)
        else:
            return None

    def create_fileentry(self, history_id, dialog_title, is_directory_entry, int2):
        w = historyentry.HistoryFileEntry(history_id, dialog_title)
        w.directory_entry = is_directory_entry
        return w

    def create_entry(self, history_id, str2, int1, int2):
        w = historyentry.HistoryEntry(history_id)
        return w

# Regular expression to match handler method names patterns
# on_widget__signal and after_widget__signal.  Note that we use two
# underscores between the Glade widget name and the signal name.
handler_re = re.compile(r'^(on|after)_(.*)__(.*)$')

def connect_signal_handlers(obj):
    for attr in dir(obj):
        match = handler_re.match(attr)
        if match:
            when, widgetname, signal = match.groups()
            method = getattr(obj, attr)
            assert callable(method)
            try:
                widget = getattr(obj, widgetname)
            except AttributeError:
                print "Widget '%s' not found in %s" % (widgetname, obj)
                continue
            try:
                widget = list(widget)
            except TypeError:
                widget = [widget]
            for w in widget:
                try:
                    if when == 'on':
                        w.connect(signal, method)
                    elif when == 'after':
                        w.connect_after(signal, method)
                except TypeError, e:
                    print e, "in", obj, attr
        elif attr.startswith('on_') or attr.startswith('after_'):
            continue # don't warn until all old code updated
            # Warn about some possible typos like separating
            # widget and signal name with _ instead of __.
            print ('Warning: attribute %r not connected'
                   ' as a signal handler' % (attr,))

def load_pixbuf(fname, size=0):
    """Load an image from a file as a pixbuf, with optional resizing.
    """
    image = gtk.Image()
    image.set_from_file(fname)
    image = image.get_pixbuf()
    if size:
        aspect = float(image.get_height()) / image.get_width()
        image = image.scale_simple(size, int(aspect*size), 2)
    return image

