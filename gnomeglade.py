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
import glob
import os
import gettext
import gobject
import re
import misc

DEBUG = False

class Base(object):
    """Base class for all glade objects.

    The handle to the xml file is stored in 'self.glade_xml'. The
    toplevel widget is stored in 'self.toplevel'. The python object
    is stored in the "pyobject" property of the toplevel widget.
    """

    RE_ON_HANDLER = re.compile(r"on_(.+?)__(.+)")
    RE_AFTER_HANDLER = re.compile(r"after_(.+?)__(.+)")

    def __init__(self, file, root, override={}):
        """Load the widgets from the node 'root' in file 'file'.
        """
        self.glade_xml = gtk.glade.XML(file, root, gettext.textdomain(), typedict=override)
        self.toplevel = getattr(self, root)
        self.toplevel.set_data("pyobject", self)

    def __getattr__(self, key):
        """Allow glade widgets to be accessed as self.widgetname.
        """
        widget = self.glade_xml.get_widget(key)
        if widget: # cache lookups
            setattr(self, key, widget)
            return widget
        raise AttributeError(key)

    def enter_locked_region(self, key):
        if not hasattr(self, key):
            setattr(self, key, 1)
            return key
        return None

    def exit_locked_region(self, key):
        delattr(self, key)

    def flushevents(self):
        """Handle all the events currently in the main queue and return.
        """
        while gtk.events_pending():
            gtk.main_iteration();

    def connect_signal_handlers(self):
        """Connect method named on_<widget>__<event> or after_<widget>__<event>
        to the relevant widget events
        """
        for methodname in dir(self.__class__):
            method = getattr(self, methodname)
            match = self.RE_ON_HANDLER.match(methodname)
            after = 0
            if not match:
                match = self.RE_AFTER_HANDLER.match(methodname)
                after = 1
            if match:
                widget, signal = match.groups()
                #print "%s::%s" % (widget, signal)
                attr = getattr(self, widget or "toplevel")
                if isinstance(attr,gobject.GObject):
                    if after:
                        id = attr.connect_after(signal, method)
                    else:
                        id = attr.connect(signal, method)
                    try:
                        attr.signal_handler_ids.append(id)
                    except AttributeError:
                        attr.signal_handler_ids = [id]
                elif isinstance(attr,type([])):
                    for a in attr:
                        if after:
                            id = a.connect_after(signal, method)
                        else:
                            id = a.connect(signal, method)
                        try:
                            a.signal_handler_ids.append(id)
                        except AttributeError:
                            a.signal_handler_ids = [id]
                else:
                    print attr, type(attr)
                    assert 0

    def block_signal_handlers(self, *widgets):
        for widget in widgets:
            for id in widget.signal_handler_ids:
                widget.handler_block(id)

    def unblock_signal_handlers(self, *widgets):
        for widget in widgets:
            for id in widget.signal_handler_ids:
                widget.handler_unblock(id)

    def add_actions(self, actiongroup, actiondefs):
        """Connect actions to their methods.
        """
        normal_actions = []
        toggle_actions = []
        radio_actions = []
        for action in actiondefs:
            if len(action) == 3:
                normal_actions.append( action )
            else:
                if len(action)==5:
                    handler = getattr(self, "action_%s__activate"%action[0])
                    normal_actions.append( action + (handler,) )
                elif isinstance(action[-1], type(True)): 
                    handler = getattr(self, "action_%s__toggled"%action[0])
                    toggle_actions.append( action[:-1] + (handler,action[-1]) )
                elif isinstance(action[-1], type(0)): 
                    handler = getattr(self, "action_%s__changed"%action[0])
                    radio_actions.append( action + (handler,) )
                else:
                    assert 0
        actiongroup.add_actions( normal_actions )
        actiongroup.add_toggle_actions( toggle_actions )
        actiongroup.add_radio_actions( radio_actions )
        for action in actiondefs:
            setattr(self, "action_"+action[0], actiongroup.get_action(action[0]))

    def map_widgets_into_lists(self, widgetnames):
        """Put sequentially numbered widgets into lists.
        
        e.g. If an object had widgets self.button0, self.button1, ...,
        then after a call to object.map_widgets_into_lists(["button"])
        object has an attribute self.button == [self.button0, self.button1, ...]."
        """
        for item in widgetnames:
            setattr(self, item, [])
            lst = getattr(self,item)
            i = 0
            while 1:
                key = "%s%i"%(item,i)
                try:
                    val = getattr(self, key)
                except AttributeError:
                    if i == 0:
                        raise
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

    def __init__(self, file, root, override={}):
        Base.__init__(self, file, root, override)

    def main(self):
        """Enter the gtk main loop.
        """
        gtk.main()

    def quit(*args):
        """Signal the gtk main loop to quit.
        """
        gtk.main_quit()

class DirectoryEntry(object):
    def __init__(self, comboentry, prefs, key):
        self.combo = comboentry
        self.entry = comboentry.child
        self.prefs = prefs
        self.key = key

        # history
        model = gtk.ListStore(type(""))
        self.combo.set_model( model )
        self.combo.set_text_column(0)
        history = getattr(prefs,key)
        if len(history):
            for p in history.split(":"):
                model.append([p])

        # completion
        self.completion = gtk.EntryCompletion()
        model = gtk.ListStore(type(""))
        self.completion.set_model( model )
        self.completion.set_text_column(0)
        self.entry.set_completion(self.completion)

        # signals
        self.entry.connect("changed", self.on_entry__changed)
        self.entry.connect("activate", self.on_entry__activate)

    def on_entry__changed(self, entry):
        model = entry.get_completion().get_model()
        model.clear()
        for m in [x for x in glob.glob( entry.get_text()+"*" ) if os.path.isdir(x)]:
            model.append( [m] )

    def on_entry__activate(self, entry):
        location = entry.get_text()
        if not os.path.isdir( location ):
            misc.run_dialog(_("No such directory '%s'") % location )
            return
        history = (getattr(self.prefs, self.key) or location).split(":")
        try:
            history.remove(location)
        except ValueError:
            if len(history) > 8:
                history.pop()
        history.insert(0,location)
        model.self.combo.get_model()
        model.clear()
        for h in history:
            model.append([h])
        setattr( self.prefs, self.key, ":".join(history) )

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

def url_show(url, parent=None):
    try:
        return gnome.url_show(url)
    except gobject.GError, e:
        misc.run_dialog(_("Could not open '%s'.\n%s")%(url,e), parent)

