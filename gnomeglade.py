import sys
sys.path.append("/home/stephen/garnome/lib/python2.2/site-packages")
import gtk
import gtk.glade
import gnome.ui

################################################################################
#
# GnomeGladeComponent
#
################################################################################
class Component(gtk.Widget):
    """A convenience base class for widgets which use glade"""

    def __init__(self, file, root):
        """Create from node 'root' in a specified file"""
        self.xml = gtk.glade.XML(file, root)
        handlers = {}
        for h in filter(lambda x:x[:3]=="on_", dir(self.__class__)):
            handlers[h] = getattr(self, h)
        self.xml.signal_autoconnect( handlers )
        self._widget = getattr(self, root)
        self._widget.set_data("pyobject", self)

    def __getattr__(self, key):
        """Allow widgets to be accessed as self.widget"""
        widget = self.xml.get_widget(key)
        if widget: # cache lookups
            setattr(self, key, widget)#self.__dict__[key] = widget
            return widget
        raise AttributeError(key)

################################################################################
#
# GnomeGladeComponent
#
################################################################################
class Dialog(gtk.Dialog):
    """A convenience base class for dialogs created in glade"""

    def __init__(self, file, root):
        """Create from node 'root' in a specified file"""
        gtk.Dialog.__init__(self)
        self.xml = gtk.glade.XML(file, root)
        handlers = {}
        for h in filter(lambda x:x[:3]=="on_", dir(self.__class__)):
            handlers[h] = getattr(self, h)
        self.xml.signal_autoconnect( handlers )
        self._widget = getattr(self, root)
        self._widget.set_data("pyobject", self)

    def __getattr__(self, key):
        """Allow widgets to be accessed as self.widget"""
        widget = self.xml.get_widget(key)
        if widget: # cache lookups
            setattr(self, key, widget)#self.__dict__[key] = widget
            return widget
        raise AttributeError(key)

################################################################################
#
# GnomeGladeApp
#
################################################################################
class App(gnome.ui.App):
    """A convenience base class for apps created in glade"""
    def __init__(self, name, version, file, root=None):
        self.program = gnome.program_init(name, version)
        gnome.ui.App.__init__(self, appname=name, title="%s %s" % (name,version))
        self.xml = gtk.glade.XML(file, root)
        handlers = {}
        for h in filter(lambda x:x[:3]=="on_", dir(self.__class__)):
            handlers[h] = getattr(self, h)
        self.xml.signal_autoconnect( handlers )

    def __getattr__(self, key):
        widget = self.xml.get_widget(key)
        if widget: # cache lookups
            setattr(self, key, widget)
            return widget
        raise AttributeError(key)

    def mainloop(self):
        gtk.mainloop()
    def quit(*args):
        gtk.main_quit()

