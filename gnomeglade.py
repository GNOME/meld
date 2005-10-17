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

"""Utility classes for working with glade files.

"""

import gtk
import gtk.glade
import gnome
import gnome.ui
import gettext

class Base(object):
    """Base class for all glade objects.

    This class handles loading the xml glade file and connects
    all methods name 'on_*' to the signals in the glade file.

    The handle to the xml file is stored in 'self.xml'. The
    toplevel widget is stored in 'self.widget'.

    In addition it calls widget.set_data("pyobject", self) - this
    allows us to get the python object given only the 'raw' gtk+
    object, which is sadly sometimes necessary.
    """

    def __init__(self, file, root, override={}):
        """Load the widgets from the node 'root' in file 'file'.

        Automatically connects signal handlers named 'on_*'.
        """
        self.xml = gtk.glade.XML(file, root, gettext.textdomain(), override )
        handlers = {}
        for h in filter(lambda x:x.startswith("on_"), dir(self.__class__)):
            handlers[h] = getattr(self, h)
        self.xml.signal_autoconnect( handlers )
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

    def flushevents(self):
        """Handle all the events currently in the main queue and return.
        """
        while gtk.events_pending():
            gtk.main_iteration();

    def _map_widgets_into_lists(self, widgetnames):
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


class Component(Base):
    """A convenience base class for widgets which use glade.
    """

    def __init__(self, file, root, override={}):
        Base.__init__(self, file, root, override)


class GtkApp(Base):
    """A convenience base class for gtk+ apps created in glade.
    """

    def __init__(self, file, root=None):
        Base.__init__(self, file, root)

    def main(self):
        """Enter the gtk main loop.
        """
        gtk.main()

    def quit(self, *args):
        """Signal the gtk main loop to quit.
        """
        gtk.main_quit()


class GnomeApp(GtkApp):
    """A convenience base class for apps created in glade.
    """

    def __init__(self, name, version, file, root):
        """Initialise program 'name' and version from 'file' containing root node 'root'.
        """
        self.program = gnome.program_init(name, version)
        GtkApp.__init__(self,file,root)
        if 0:
            self.client = gnome.ui.Client()
            self.client.disconnect()
            def connected(*args):
                print "CONNECTED", args
            def cb(name):
                def cb2(*args):
                    print name, args, "\n"
                return cb2
            self.client.connect("connect", cb("CON"))
            self.client.connect("die", cb("DIE"))
            self.client.connect("disconnect", cb("DIS"))
            self.client.connect("save-yourself", cb("SAVE"))
            self.client.connect("shutdown-cancelled", cb("CAN"))
            self.client.connect_to_session_manager()


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

def url_show(url):
    return gnome.url_show(url)

def FileEntry(*args):
    return gnome.ui.FileEntry(*args)

