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

import gtk
import prefs
import paths
import misc
import glade

class ListWidget(glade.Component):
    def __init__(self, columns, prefs, key):
        glade.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "listwidget")
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
        setattr( self.prefs, self.key, self.prefs.get_default(self.key) )
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
        for filtstring in getattr( self.prefs, self.key).split("\n"):
            filt = misc.ListItem(filtstring)
            iter = model.append()
            model.set_value( iter, 0, filt.name)
            model.set_value( iter, 1, filt.active)
            model.set_value( iter, 2, filt.value)
   
class PreferencesDialog(glade.Component):

    editor_radio_values = {"internal":0, "gnome":1, "custom":2}

    def __init__(self, parentapp):
        glade.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "preferencesdialog")
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
        # editor
        self.map_widgets_into_lists( ["editor_command"] )
        if self.prefs.use_custom_font:
            self.radiobutton_custom_font.set_active(1)
        else:
            self.radiobutton_gnome_font.set_active(1)
        self.label_font_name.set_markup( '<span face="%s">%s</span>' % (self.prefs.custom_font,self.prefs.custom_font) )
        self.spinbutton_tabsize.set_value( self.prefs.tab_size )
        self.option_wrap_lines.set_history( self.prefs.edit_wrap_lines )
        self.checkbutton_supply_newline.set_active( self.prefs.supply_newline )
        self.checkbutton_show_line_numbers.set_active( self.prefs.show_line_numbers )
        self.checkbutton_use_syntax_highlighting.set_active( self.prefs.use_syntax_highlighting )
        self.editor_command[ self.editor_radio_values.get(self.prefs.edit_command_type, "internal") ].set_active(1)
        self.gnome_default_editor_label.set_text( "(%s)" % " ".join(self.prefs.get_gnome_editor_command([])) )
        self.custom_edit_command_entry.set_text( " ".join(self.prefs.get_custom_editor_command([])) )
        # display
        self.map_widgets_into_lists( ["draw_style"] )
        self.map_widgets_into_lists( ["toolbar_style"] )
        self.draw_style[self.prefs.draw_style].set_active(1)
        self.toolbar_style[self.prefs.toolbar_style].set_active(1)
        # file filters
        cols = [ ("Name", type("")), ("Active", type(0)), ("Pattern", type("")) ]
        self.filefilter = ListWidget( cols, self.prefs, "filters")
        self.file_filters_box.pack_start(self.filefilter.toplevel)
        # text filters
        cols = [ ("Name", type("")), ("Active", type(0)), ("Regex", type("")) ]
        self.textfilter = ListWidget( cols, self.prefs, "regexes")
        self.text_filters_box.pack_start(self.textfilter.toplevel)
        self.checkbutton_ignore_blank_lines.set_active(self.prefs.ignore_blank_lines)
        # encoding
        self.entry_text_codecs.set_text( self.prefs.text_codecs )
        self.map_widgets_into_lists( ["save_encoding"] )
        self.save_encoding[self.prefs.save_encoding].set_active(1)
        # cvs
        self.cvs_quiet_check.set_active( self.prefs.cvs_quiet )
        self.cvs_compression_check.set_active( self.prefs.cvs_compression )
        self.cvs_compression_value_spin.set_value( self.prefs.cvs_compression_value )
        self.cvs_ignore_cvsrc_check.set_active( self.prefs.cvs_ignore_cvsrc )
        self.cvs_binary_fileentry.set_filename( self.prefs.cvs_binary )
        self.cvs_create_missing_check.set_active( self.prefs.cvs_create_missing )
        self.cvs_prune_empty_check.set_active( self.prefs.cvs_prune_empty )
        # finally connect handlers
        self.connect_signal_handlers()
    def on_button_pick_font__clicked(self, *args):
        print "pick"
    #
    # treeview
    #
    def on_treeview__cursor_changed(self, tree):
        path, column = tree.get_cursor()
        self.notebook.set_current_page(path[0])
    #
    # editor
    #
    def _on_radiobutton_font__toggled(self, radio):
        if radio.get_active():
            iscustom = (radio == self.radiobutton_custom_font)
            self.fontpicker.set_sensitive(iscustom)
            self.prefs.use_custom_font = iscustom
    def on_radiobutton_gnome_font__toggled(self, radio):
        self._on_radiobutton_font__toggled(radio)
    def on_radiobutton_custom_font__toggled(self, radio):
        self._on_radiobutton_font__toggled(radio)
    def on_fontpicker__font_set(self, picker, font):
        self.prefs.custom_font = font
    def on_spinbutton_tabsize__changed(self, spin):
        self.prefs.tab_size = int(spin.get_value())
    def on_option_wrap_lines__changed(self, option):
        self.prefs.edit_wrap_lines = option.get_history()
    def on_checkbutton_supply_newline__toggled(self, check):
        self.prefs.supply_newline = check.get_active()
    def on_checkbutton_show_line_numbers__toggled(self, check):
        self.prefs.show_line_numbers = check.get_active()
        if check.get_active() and not sourceview.available:
            misc.run_dialog(_("Line numbers are only available if you have pygtksourceview installed.") )
    def on_checkbutton_use_syntax_highlighting__toggled(self, check):
        self.prefs.use_syntax_highlighting = check.get_active()
        if check.get_active() and not sourceview.available:
            misc.run_dialog(_("Syntax highlighting is only available if you have pygtksourceview installed.") )
    def on_editor_command__toggled(self, radio):
        if radio.get_active():
            idx = self.editor_command.index(radio)
            for k,v in self.editor_radio_values.items():
                if v == idx:
                    self.prefs.edit_command_type = k
                    break
    #
    # display
    #
    def on_draw_style__toggled(self, radio):
        if radio.get_active():
            self.prefs.draw_style = self.draw_style.index(radio)
    def on_toolbar_style__toggled(self, radio):
        if radio.get_active():
            self.prefs.toolbar_style = self.toolbar_style.index(radio)
    #
    # filters
    #
    def on_checkbutton_ignore_blank_lines__toggled(self, check):
        self.prefs.ignore_blank_lines = check.get_active()

    #
    # encoding
    #
    def on_save_encoding__toggled(self, radio):
        if radio.get_active():
            self.prefs.save_encoding = self.save_encoding.index(radio)
    #
    # cvs
    #
    def on_cvs_quiet_check__toggled(self, toggle):
        self.prefs.cvs_quiet = toggle.get_active()
    def on_cvs_compression_check__toggled(self, toggle):
        self.prefs.cvs_compression = toggle.get_active()
    def on_cvs_compression_value_spin__changed(self, spin):
        self.prefs.cvs_compression_value = int(spin.get_value())
    def on_cvs_ignore_cvsrc_check__toggled(self, toggle):
        self.prefs.cvs_ignore_cvsrc = toggle.get_active()
    def on_cvs_binary_fileentry__activate(self, fileentry):
        self.prefs.cvs_binary = fileentry.gtk_entry().get_text()
    def on_cvs_create_missing_check__toggled(self, toggle):
        self.prefs.cvs_create_missing = toggle.get_active()
    def on_cvs_prune_empty_check__toggled(self, toggle):
        self.prefs.cvs_prune_empty = toggle.get_active()
    #
    # dialog response
    #
    def on__response(self, dialog, arg):
        if arg==gtk.RESPONSE_CLOSE:
            self.prefs.text_codecs = self.entry_text_codecs.get_property("text")
            self.prefs.edit_command_custom = self.custom_edit_command_entry.get_property("text")
        self.toplevel.destroy()

class MeldPreferences(prefs.Preferences):
    defaults = {
        "window_size_x": prefs.Value(prefs.INT, 600),
        "window_size_y": prefs.Value(prefs.INT, 600),
        "use_custom_font": prefs.Value(prefs.BOOL,0),
        "custom_font": prefs.Value(prefs.STRING,"monospace, 14"),
        "tab_size": prefs.Value(prefs.INT, 4),
        "show_line_numbers": prefs.Value(prefs.BOOL, 0),
        "use_syntax_highlighting": prefs.Value(prefs.BOOL, 0),
        "edit_wrap_lines" : prefs.Value(prefs.INT, 0),
        "edit_command_type" : prefs.Value(prefs.STRING, "internal"), #internal, gnome, custom
        "edit_command_custom" : prefs.Value(prefs.STRING, "gedit"),
        "supply_newline": prefs.Value(prefs.BOOL,1),
        "text_codecs": prefs.Value(prefs.STRING, "utf8 latin1"), 
        "save_encoding": prefs.Value(prefs.INT, 0),
        "draw_style": prefs.Value(prefs.INT,2),
        "toolbar_style": prefs.Value(prefs.INT,0),
        "cvs_location_history": prefs.Value(prefs.STRING, ""),
        "cvs_flatten": prefs.Value(prefs.BOOL, 1),
        "cvs_quiet": prefs.Value(prefs.BOOL, 1),
        "cvs_compression": prefs.Value(prefs.BOOL, 1),
        "cvs_compression_value": prefs.Value(prefs.INT, 3),
        "cvs_ignore_cvsrc": prefs.Value(prefs.BOOL, 0),
        "cvs_binary": prefs.Value(prefs.STRING, "/usr/bin/cvs"),
        "cvs_create_missing": prefs.Value(prefs.BOOL, 1),
        "cvs_prune_empty": prefs.Value(prefs.BOOL, 1),
        "cvs_console_visible": prefs.Value(prefs.BOOL, 0),
        "color_delete_bg" : prefs.Value(prefs.STRING, "DarkSeaGreen1"),
        "color_delete_fg" : prefs.Value(prefs.STRING, "Red"),
        "color_replace_bg" : prefs.Value(prefs.STRING, "#ddeeff"),
        "color_replace_fg" : prefs.Value(prefs.STRING, "Black"),
        "color_conflict_bg" : prefs.Value(prefs.STRING, "misty rose"),
        "color_conflict_fg" : prefs.Value(prefs.STRING, "Black"),
        "color_inline2_bg" : prefs.Value(prefs.STRING, "pink1"),
        "color_inline2_fg" : prefs.Value(prefs.STRING, "DarkBlue"),
        "color_inline_bg" : prefs.Value(prefs.STRING, "LightSteelBlue2"),
        "color_inline_fg" : prefs.Value(prefs.STRING, "Red"),
        "color_edited_bg" : prefs.Value(prefs.STRING, "gray90"),
        "color_edited_fg" : prefs.Value(prefs.STRING, "Black"),
        "filters" : prefs.Value(prefs.STRING, "Backups\t1\t#*# .#* ~* *~ *.{orig,bak,swp}\n" + \
                                              "CVS\t1\tCVS\n" + \
                                              "Binaries\t1\t*.{pyc,a,obj,o,so,la,lib,dll}\n" + \
                                              "Media\t0\t*.{jpg,gif,png,wav,mp3,ogg,xcf,xpm}"),
        "regexes" : prefs.Value(prefs.STRING, "CVS keywords\t0\t\$[^:]+:[^\$]+\$\n" + \
                                              "C++ comment\t0\t//.*\n" + \
                                              "C comment\t0\t/\*[^*]*\*+([^/*][^*]*\*+)*/\n" + \
                                              "All whitespace\t0\t[ \\t\\r\\f\\v]*\n" + \
                                              "Leading whitespace\t0\t^[ \\t\\r\\f\\v]*\n" + \
                                              "Script comment\t0\t#.*"),
        "ignore_blank_lines" : prefs.Value(prefs.BOOL, 1)
    }

    def __init__(self):
        prefs.Preferences.__init__(self, "/apps/meld", self.defaults)

    def get_cvs_command(self, op=None):
        cmd = [self.cvs_binary]
        if self.cvs_quiet:
            cmd.append("-q")
        if self.cvs_compression:
            cmd.append("-z%i" % self.cvs_compression_value)
        if self.cvs_ignore_cvsrc:
            cmd.append("-f")
        if op:
            cmd.append(op)
            if op == "update":
                if self.cvs_create_missing:
                    cmd.append("-d")
                if self.cvs_prune_empty:
                    cmd.append("-P")
        return cmd
    def get_current_font(self):
        if self.use_custom_font:
            return self.custom_font
        else:
            return self._gconf.get_string('/desktop/gnome/interface/monospace_font_name') or "Monospace 10"

    def get_toolbar_style(self):
        if self.toolbar_style == 0:
            style = self._gconf.get_string('/desktop/gnome/interface/toolbar_style') or "both"
            style = style.replace("-","_")
            style = {"both":gtk.TOOLBAR_BOTH, "text":gtk.TOOLBAR_TEXT,
                     "icon":gtk.TOOLBAR_ICONS, "icons":gtk.TOOLBAR_ICONS,
                     "both_horiz":gtk.TOOLBAR_BOTH_HORIZ,
                     "both-horiz":gtk.TOOLBAR_BOTH_HORIZ
                     }[style]
        else:
            style = self.toolbar_style - 1
        return style

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
        return self.edit_command_custom.split() + files

