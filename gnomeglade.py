import gtk
import gtk.glade
import gnome.ui

################################################################################
#
# Base
#
################################################################################
class Base:

    def __init__(self, file, root):
        self.xml = gtk.glade.XML(file, root)
        handlers = {}
        for h in filter(lambda x:x[:3]=="on_", dir(self.__class__)):
            handlers[h] = getattr(self, h)
        self.xml.signal_autoconnect( handlers )
        self._widget = getattr(self, root)
        self._widget.set_data("pyobject", self)

    def __getattr__(self, key):
        """Allow glade widgets to be accessed as self.widgetname"""
        widget = self.xml.get_widget(key)
        if widget: # cache lookups
            setattr(self, key, widget)#self.__dict__[key] = widget
            return widget
        raise AttributeError(key)

    def flushevents(self):
        """Handle all the events currently in the main queue"""
        while gtk.events_pending():
            gtk.main_iteration();

    def _map_widgets_into_lists(self, widgetnames):
        """e.g. make widgets self.button0, self.button1, ... available as self.button[0], self.button[1], ..."""
        for item in widgetnames:
            setattr(self,item, [])
            list = getattr(self,item)
            i = 0
            while 1:
                key = "%s%i"%(item,i)
                try:
                    val = getattr(self, key)
                except AttributeError:
                    break
                list.append(val)
                i += 1

################################################################################
#
# GnomeGladeComponent
#
################################################################################
class Component(gtk.Widget, Base):
    """A convenience base class for widgets which use glade"""

    def __init__(self, file, root):
        """Create from node 'root' in a specified file"""
        Base.__init__(self,file,root)

################################################################################
#
# GnomeGladeMenu
#
################################################################################
class Menu(gtk.Menu, Base):
    """A convenience base class for widgets which use glade"""

    def __init__(self, file, root):
        """Create from node 'root' in a specified file"""
        gtk.Menu.__init__(self)
        Base.__init__(self,file,root)

################################################################################
#
# GnomeGladeComponent
#
################################################################################
class Dialog(gtk.Dialog, Base):
    """A convenience base class for dialogs created in glade"""

    def __init__(self, file, root):
        """Create from node 'root' in a specified file"""
        gtk.Dialog.__init__(self)
        Base.__init__(self,file,root)

################################################################################
#
# GnomeApp
#
################################################################################
class GnomeApp(gnome.ui.App, Base):
    """A convenience base class for apps created in glade"""

    def __init__(self, name, version, file, root=None):
        self.program = gnome.program_init(name, version)
        gnome.ui.App.__init__(self, appname=name, title="%s %s" % (name,version))
        Base.__init__(self,file,root)

    def mainloop(self):
        """Enter the gtk main loop"""
        gtk.mainloop()
    def quit(*args):
        """Signal the gtk main loop to quit"""
        gtk.main_quit()

################################################################################
#
# GtkApp
#
################################################################################
class GtkApp(gtk.Window, Base):
    """A convenience base class for apps created in glade"""

    def __init__(self, name, version, file, root=None):
        gtk.Window.__init__(self)
        Base.__init__(self,file,root)

    def mainloop(self):
        """Enter the gtk main loop"""
        gtk.mainloop()
    def quit(*args):
        """Signal the gtk main loop to quit"""
        gtk.main_quit()
################################################################################
#
# load_pixbuf
#
################################################################################
def load_pixbuf(fname, size=0):
    """Load an image from a file as a pixbuf"""
    image = gtk.Image()
    image.set_from_file(fname)
    image = image.get_pixbuf()
    if size:
        image = image.scale_simple(size, size, 2)
    return image

