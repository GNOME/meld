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

import gconf
import gettext
import glade
import glob
import gobject
import gtk
import gtk.glade
import os
import paths
import re

RE_ON_HANDLER = re.compile(r"on_(.+?)__(.+)")
RE_AFTER_HANDLER = re.compile(r"after_(.+?)__(.+)")

def connect_signal_handlers(self):
    """Connect method named on_<widget>__<event> or after_<widget>__<event>
    to the relevant widget events
    """
    for methodname in dir(self.__class__):
        method = getattr(self, methodname)
        match = RE_ON_HANDLER.match(methodname)
        after = 0
        if not match:
            match = RE_AFTER_HANDLER.match(methodname)
            after = 1
        if match:
            widget, signal = match.groups()
            #print "%s::%s" % (widget, signal)
            attr = getattr(self, widget or "toplevel")
            def connect(attr, signal, method):
                try:
                    if after:
                        return attr.connect_after(signal, method)
                    else:
                        return attr.connect(signal, method)
                except TypeError, e:
                    print "Couldn't connect %s::%s (%s)" % ( widget, signal, e)
            if isinstance(attr,gobject.GObject):
                id = connect(attr, signal, method)
                try:
                    attr.signal_handler_ids.append(id)
                except AttributeError:
                    attr.signal_handler_ids = [id]
            elif isinstance(attr,type([])):
                for a in attr:
                    id = connect(a, signal, method)
                    try:
                        a.signal_handler_ids.append(id)
                    except AttributeError:
                        a.signal_handler_ids = [id]
            else:
                print attr, type(attr)
                assert 0

class Component(object):
    """Base class for all glade objects.

    The handle to the xml file is stored in 'self.glade_xml'. The
    toplevel widget is stored in 'self.toplevel'. The python object
    is stored in the "pyobject" property of the toplevel widget.
    """

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

    def get_widget_name(self, widget):
        return gtk.glade.get_widget_name(widget)

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
        connect_signal_handlers(self)

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

class Dialog(Component):
    """A convenience base class for widgets which use glade.
    """

    def __init__(self, file, root, override={}):
        Component.__init__(self, file, root, override)

    def run(self):
        response = self.toplevel.run()
        self.toplevel.destroy()
        return response

class GtkApp(Component):
    """A convenience base class for gtk+ apps created in glade.
    """

    def __init__(self, file, root, override={}):
        Component.__init__(self, file, root, override)

    def main(self):
        """Enter the gtk main loop.
        """
        gtk.main()

    def quit(*args):
        """Signal the gtk main loop to quit.
        """
        gtk.main_quit()

class CloseLabel(gtk.HBox):
    __gsignals__ = {
        'closed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ()),
    }

    def __init__(self, iconname, text=""):
        gtk.HBox.__init__(self)
        self.label = gtk.Label(text)
        self.button = gtk.Button()
        icon = gtk.Image()
        icon.set_from_file( paths.share_dir("glade2/pixmaps/%s" % iconname) )
        icon.set_from_pixbuf( icon.get_pixbuf().scale_simple(15, 15, 2) ) #TODO font height
        image = gtk.Image()
        image.set_from_file( paths.share_dir("glade2/pixmaps/button_delete.xpm") )
        image.set_from_pixbuf( image.get_pixbuf().scale_simple(9, 9, 2) ) #TODO font height
        self.button.add( image )
        self.pack_start( icon )
        self.pack_start( self.label )
        self.pack_start( self.button, expand=0 )
        self.show_all()
        self.button.connect("clicked", self.on_button__clicked)
    def on_button__clicked(self, button):
        self.emit("closed")
    def set_text(self, text):
        self.label.set_text(text)
    def set_markup(self, markup):
        self.label.set_markup(markup)
gobject.type_register(CloseLabel)

class BaseEntry(gtk.HBox):
    ROOT_KEY = "/apps/meld/state"

    def __init__(self, history_id=None):
        self.__gobject_init__()
        self.combo = gtk.combo_box_entry_new_text()
        self.entry = self.combo.child
        self.button = gtk.Button(_("_Browse..."))
        self.pack_start(self.combo)
        self.pack_start(self.button, expand=False)
        self.set_spacing(3)
        # history
        self.gconf = gconf.client_get_default()
        self.history_id = history_id
        self.add_history(None)
        # completion
        self.completion = gtk.EntryCompletion()
        model = gtk.ListStore(type(""))
        self.completion.set_model( model )
        self.completion.set_text_column(0)
        self.entry.set_completion(self.completion)
        glade.connect_signal_handlers(self)
        self.show_all()

    def on_button__clicked(self, button):
        buttons = gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK
        dialog = gtk.FileChooserDialog(parent=self.get_toplevel(), action=self.FILE_CHOOSER_ACTION, buttons=buttons)
        if dialog.run() == gtk.RESPONSE_OK:
            self.entry.set_text(dialog.get_filename())
        dialog.destroy()

    def on_entry__changed(self, entry):
        model = entry.get_completion().get_model()
        model.clear()
        loc = entry.get_text()
        if os.path.isdir(loc) and loc != "/":
            loc += "/"
        completions = [x for x in glob.glob( loc+"*" ) if self.COMPLETION_FILTER(x)]
        for m in completions[:10]:
            model.append( [m] )

    def add_history(self, name):
        history = self.gconf.get_list("%s/%s" % (self.ROOT_KEY, self.history_id), gconf.VALUE_STRING )
        try:
            history.remove(name)
        except ValueError:
            pass
        while len(history) > 7:
            history.pop()
        if name:
            history.insert(0, name)
        model = self.combo.get_model()
        model.clear()
        for h in history:
            model.append([h])
        if name:
            self.combo.set_active(0)
            self.gconf.set_list("%s/%s" % (self.ROOT_KEY, self.history_id), gconf.VALUE_STRING, history )
gobject.type_register(BaseEntry)

class FileEntry(BaseEntry):
    FILE_CHOOSER_ACTION = gtk.FILE_CHOOSER_ACTION_OPEN
    COMPLETION_FILTER = lambda s,x: True
    def __init__(self, history_id=None):
        BaseEntry.__init__(self, history_id)
        
    
class DirEntry(BaseEntry):
    FILE_CHOOSER_ACTION = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
    COMPLETION_FILTER = lambda s,x : os.path.isdir(x)
    def __init__(self, history_id=None):
        BaseEntry.__init__(self, history_id)


def _custom_handler(xml, klass, name, *rest):
    return {"FileEntry":FileEntry, "DirEntry":FileEntry}[klass](name)
gtk.glade.set_custom_handler(_custom_handler)


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

def run_dialog( maintext, parent=None, messagetype=gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_OK, extrabuttons=[], subtext=None):
    """Run a dialog with text 'text'.
       Extra buttons are passed as tuples of (button label, response id).
    """
    if subtext:
        text = '<span weight="bold" size="larger">%s\n</span>%s' % (maintext, subtext)
    else:
        text = '<span weight="bold" size="larger">%s</span>' % maintext
    d = gtk.MessageDialog( parent,
        gtk.DIALOG_DESTROY_WITH_PARENT,
        messagetype,
        buttonstype,
        text )
    for b,id in extrabuttons:
        d.add_button(b,id)
    d.vbox.set_spacing(12)
    hbox = d.vbox.get_children()[0]
    hbox.set_spacing(12)
    d.image.set_alignment(0.5, 0)
    d.image.set_padding(12, 12)
    d.label.set_use_markup(1)
    d.label.set_padding(12, 12)
    ret = d.run()
    d.destroy()
    return ret

def url_show(url, parent=None):
    try:
        return gnome.url_show(url)
    except gobject.GError, e:
        misc.run_dialog(_("Could not open '%s'.\n%s")%(url,e), parent)

def tie_to_gconf(rootkey, *widgets):
    conf = gconf.client_get_default()
    get_name = gtk.glade.get_widget_name

    def connect( widget ):
        name = get_name(widget)
        key = "%s/%s" % (rootkey, name)
        if isinstance( widget, gtk.RadioButton ):
            # radio widgets must be named <keyname>_<value>
            group = widget.get_group()
            key = "%s/%s" % (rootkey, get_name(widget).split("_",1)[0])
            names = [ get_name(r).split("_",1)[1] for r in group ]
            try:
                active = names.index( conf.get_string(key) )
            except ValueError:
                pass
            else:
                group[active].set_active(True)
            def toggled(radio):
                if radio.get_active():
                    rkey, val = get_name(radio).split("_",1)
                    conf.set_string("%s/%s" %(rootkey,rkey), val )
            for w in group:
                w.connect("toggled", toggled)
        elif isinstance( widget, gtk.ToggleButton ):
            # toggles are named as their glade widget
            active = conf.get_bool(key)
            widget.set_active(active)
            widget.connect("toggled", lambda b,k=key : conf.set_bool(k, b.get_active()) )
        else:
            print "Fixme", widget, type(widget)

    for widget in widgets:
        if isinstance( widget, list ):
            for w in widget:
                connect( w )
        else:
            connect(widget)

