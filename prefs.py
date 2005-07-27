### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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

"""

import gconf
import gtk
import paths
import misc
import gui

__metaclass__ = type

__get_funcs__ = {
    gconf.VALUE_BOOL: gconf.Value.get_bool,
    gconf.VALUE_FLOAT: gconf.Value.get_float,
    gconf.VALUE_INT: gconf.Value.get_int,
    gconf.VALUE_STRING: gconf.Value.get_string,
    gconf.VALUE_LIST: lambda l :
        [__get_funcs__[l.get_list_type()](v) for v in gconf.Value.get_list(l,l.get_list_type()) ]
}

class Preferences:

    class View:
        """A view of a subdirectory
        """

        def __init__(self, parent, view):
            self.parent = parent
            self.root = "%s/%s" % (parent._rootkey, view)
            if not self.parent._gconf.dir_exists( self.root ):
                raise ("No such key %s" % self.root)

        def __getattr__(self, attr):
            value = self.parent._gconf.get(self.abskey(attr))
            if value:
                return __get_funcs__[value.type](value)
            else:
                return getattr(self.parent, attr)

        def abskey(self, key):
            return "%s/%s" % (self.root, key)

    def __init__(self, rootkey):
        """Create a preferences object.

        rootkey : the root gconf key where the values will be stored
        """
        self.__dict__["_gconf"] = gconf.client_get_default()
        self.__dict__["_listeners"] = []
        self.__dict__["_rootkey"] = rootkey
        self._gconf.add_dir(rootkey, gconf.CLIENT_PRELOAD_NONE)
        self._gconf.notify_add(rootkey, self._on_preference_changed)

    def __getattr__(self, attr):
        return self.View(self, attr)

    def _on_preference_changed(self, client, timestamp, entry, extra):
        #print "PREF", client, timestamp, entry, extra
        return
        attr = entry.key[ entry.key.rindex("/")+1 : ]
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

    def get_default(self, key):
        schema = self._gconf.get_schema("/schemas"+key)
        value = schema.default_value()
        return __get_funcs__[value.type](value)

    def get_cvs_command(self, op=None):
        cmd = [self.cvs.executable]
        if self.cvs.quiet:
            cmd.append("-q")
        if self.cvs.compression:
            cmd.append("-z%i" % self.cvs.compression_value)
        if self.cvs.ignore_cvsrc:
            cmd.append("-f")
        if op:
            cmd.append(op)
            if op == "update":
                if self.cvs.create_missing:
                    cmd.append("-d")
                if self.cvs.prune_empty:
                    cmd.append("-P")
        return cmd

    def get_current_font(self):
        if self.filediff.custom_font_enabled:
            return self.filediff.custom_font
        else:
            return self._gconf.get_string('/desktop/gnome/interface/monospace_font_name') or "Monospace 10"

    def get_toolbar_style(self):
        if self.common.use_toolbar_style:
            style = self.common.toolbar_style
        else:
            style = self._gconf.get_string('/desktop/gnome/interface/toolbar_style')
        style = style.replace("_","-")
        return {"both":gtk.TOOLBAR_BOTH, "text":gtk.TOOLBAR_TEXT,
                "icon":gtk.TOOLBAR_ICONS, "icons":gtk.TOOLBAR_ICONS,
                "both-horiz":gtk.TOOLBAR_BOTH_HORIZ
                }.get(style, gtk.TOOLBAR_BOTH)

    def get_gnome_editor_command(self, files):
        argv = []
        editor = self._gconf.get_string('/desktop/gnome/applications/editor/exec') or "gedit"
        if self._gconf.get_bool("/desktop/gnome/applications/editor/needs_term"):
            texec = self._gconf.get_string("/desktop/gnome/applications/terminal/exec")
            if texec:
                argv.append(texec)
                targ = self._gconf.get_string("/desktop/gnome/applications/terminal/exec_arg")
                if targ:
                    argv.append(targ)
            argv.append( "%s %s" % (editor, " ".join( [f.replace(" ","\\ ") for f in files]) ) )
        else:
            argv = [editor] + files
        return argv

    def get_custom_editor_command(self, files):
        return self.filediff.custom_editor.split() + files



class ListWidget(gui.Component):
    def __init__(self, columns, prefs, key):
        gui.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "listwidget")
        self.prefs = prefs
        self.key = key
        self.treeview.set_model( gtk.ListStore( *[c[1] for c in columns] ) )
        view = self.treeview
        def addTextCol(label, colnum, expand=0):
            model = view.get_model()
            rentext = gtk.CellRendererText()
            rentext.set_property("editable", 1)
            def change_text(ren, row, text):
                iter = model.get_iter( (int(row),))
                model.set_value( iter, colnum, text)
                self._update_filter_string()
            rentext.connect("edited", change_text)
            column = gtk.TreeViewColumn(label)
            column.pack_start(rentext, expand=expand)
            column.set_attributes(rentext, markup=colnum)
            view.append_column(column)
        def addToggleCol(label, colnum):
            model = view.get_model()
            rentoggle = gtk.CellRendererToggle()
            def change_toggle(ren, row):
                iter = model.get_iter( (int(row),))
                model.set_value( iter, colnum, not ren.get_active() )
                self._update_filter_string()
            rentoggle.connect("toggled", change_toggle)
            column = gtk.TreeViewColumn(label)
            column.pack_start(rentoggle, expand=0)
            column.set_attributes(rentoggle, active=colnum)
            view.append_column(column)
        for c,i in zip( columns, range(len(columns))):
            if c[1] == type(""):
                e = (i == (len(columns)-1))
                addTextCol( c[0], i, expand=e)
            elif c[1] == type(0):
                addToggleCol( c[0], 1)
        self._update_filter_model()
        self.connect_signal_handlers()
    def on_item_new__clicked(self, button):
        model = self.treeview.get_model()
        iter = model.append()
        model.set_value(iter, 0, "label")
        model.set_value(iter, 2, "pattern")
        self._update_filter_string()
    def _get_selected(self):
        selected = []
        self.treeview.get_selection().selected_foreach(
            lambda store, path, iter: selected.append( path ) )
        return selected
    def on_item_delete__clicked(self, button):
        model = self.treeview.get_model()
        for s in self._get_selected():
            model.remove( model.get_iter(s) )
        self._update_filter_string()
    def on_item_up__clicked(self, button):
        model = self.treeview.get_model()
        for s in self._get_selected():
            if s[0] > 0: # XXX need model.swap
                old = model.get_iter(s[0])
                iter = model.insert( s[0]-1 )
                for i in range(3):
                    model.set_value(iter, i, model.get_value(old, i) )
                model.remove(old)
                self.treeview.get_selection().select_iter(iter)
        self._update_filter_string()
    def on_item_down__clicked(self, button):
        model = self.treeview.get_model()
        for s in self._get_selected():
            if s[0] < len(model)-1: # XXX need model.swap
                old = model.get_iter(s[0])
                iter = model.insert( s[0]+2 )
                for i in range(3):
                    model.set_value(iter, i, model.get_value(old, i) )
                model.remove(old)
                self.treeview.get_selection().select_iter(iter)
        self._update_filter_string()
    def on_items_revert__clicked(self, button):
        #setattr( self.prefs, self.key, self.prefs.get_default(self.prefs.abskey(self.key)) )
        self._update_filter_model()
    def _update_filter_string(self):
        model = self.treeview.get_model()
        pref = []
        for row in model:
            pref.append("%s\t%s\t%s" % (row[0], row[1], row[2]))
        setattr( self.prefs, self.key, "\n".join(pref) )
    def _update_filter_model(self):
        model = self.treeview.get_model()
        model.clear()
        for filtstring in getattr( self.prefs, self.key):
            filt = misc.ListItem(filtstring)
            iter = model.append()
            model.set_value( iter, 0, filt.name)
            model.set_value( iter, 1, filt.active)
            model.set_value( iter, 2, filt.value)
   


class PreferencesDialog(gui.Component):

    def __init__(self, parentapp):
        gui.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "preferencesdialog")
        self.toplevel.set_transient_for(parentapp.toplevel)
        self.notebook.set_show_tabs(0)
        # tab selector
        self.model = gtk.ListStore(type(""))
        column = gtk.TreeViewColumn()
        rentext = gtk.CellRendererText()
        column.pack_start(rentext, expand=0)
        column.set_attributes(rentext, text=0)
        self.treeview.append_column(column)
        self.treeview.set_model(self.model)
        for c in self.notebook.get_children():
            label = self.notebook.get_tab_label(c).get_text()
            if not label.startswith("_"):
                self.model.append( (label,) )
        self.prefs = parentapp.prefs
        # filediff
        gui.tie_to_gconf("/apps/meld/filediff", self.custom_font_enabled, self.custom_font,
            self.tab_size, self.wrap_lines, self.supply_newline,
            self.line_numbers, self.syntax_highlighting, self.editor_internal,
            self.editor_custom, self.text_codecs,
            self.encoding_preserve, self.ignore_blank_lines
            )
        # editor
        self.gnome_default_editor_label.set_text( "(%s)" % " ".join(self.prefs.get_gnome_editor_command([])) )
        # display
        gui.tie_to_gconf("/apps/meld/common", self.custom_toolbar_enabled, self.custom_toolbar)
        # file filters
        cols = [ ("Name", type("")), ("Active", type(0)), ("Pattern", type("")) ]
        self.filefilter = ListWidget( cols, self.prefs.dirdiff, "filters")
        self.file_filters_box.pack_start(self.filefilter.toplevel)
        # text filters
        cols = [ ("Name", type("")), ("Active", type(0)), ("Regex", type("")) ]
        self.textfilter = ListWidget( cols, self.prefs.common, "regexes")
        self.text_filters_box.pack_start(self.textfilter.toplevel)
        # cvs
        gui.tie_to_gconf("/apps/meld/cvs", self.cvs_compression_enabled, self.cvs_compression,
            self.cvs_create_missing, self.cvs_executable, self.cvs_ignore_cvsrc,
            self.cvs_prune_empty, self.cvs_quiet )
        # finally connect handlers
        self.connect_signal_handlers()
    #
    # treeview
    #
    def on_treeview__cursor_changed(self, tree):
        path, column = tree.get_cursor()
        self.notebook.set_current_page(path[0])
    #
    # editor
    #
    #def on_line_numbers__toggled(self, check):
        #if check.get_active() and not sourceview.available:
            #misc.run_dialog(_("Line numbers are only available if you have pygtksourceview installed.") )
    #def on_syntax_highlighting__toggled(self, check):
        #if check.get_active() and not sourceview.available:
            #misc.run_dialog(_("Syntax highlighting is only available if you have pygtksourceview installed.") )

    #
    # dialog response
    #
    def on_toplevel__response(self, dialog, arg):
        self.toplevel.destroy()

