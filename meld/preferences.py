### Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>

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


from gettext import gettext as _

import gtk

from ui import gnomeglade
import misc
import paths
from util import prefs
import vc

from util.sourceviewer import srcviewer


class ListWidget(gnomeglade.Component):
    def __init__(self, columns, prefs, key):
        gnomeglade.Component.__init__(self, paths.ui_dir("preferences.ui"), "listwidget")
        self.prefs = prefs
        self.key = key
        self.treeview.set_model( gtk.ListStore( *[c[1] for c in columns] ) )
        view = self.treeview
        def addTextCol(label, colnum):
            model = view.get_model()
            rentext = gtk.CellRendererText()
            rentext.props.editable = 1
            def change_text(ren, path, text):
                model[path][colnum] = text
                self._update_filter_string()
            rentext.connect("edited", change_text)
            column = gtk.TreeViewColumn(label, rentext, text=colnum)
            view.append_column(column)
        def addToggleCol(label, colnum):
            model = view.get_model()
            rentoggle = gtk.CellRendererToggle()
            def change_toggle(ren, path):
                model[path][colnum] = not ren.get_active()
                self._update_filter_string()
            rentoggle.connect("toggled", change_toggle)
            column = gtk.TreeViewColumn(label, rentoggle, active=colnum)
            view.append_column(column)
        for c,i in zip( columns, range(len(columns))):
            if c[1] == type(""):
                addTextCol(c[0], i)
            elif c[1] == type(0):
                addToggleCol( c[0], 1)
        view.get_selection().connect('changed', self._update_sensitivity)
        view.get_model().connect('row-inserted', self._update_sensitivity)
        view.get_model().connect('rows-reordered', self._update_sensitivity)
        self._update_sensitivity()
        self._update_filter_model()

    def _update_sensitivity(self, *args):
        (model, it, path) = self._get_selected()
        if not it:
            self.item_delete.set_sensitive(False)
            self.item_up.set_sensitive(False)
            self.item_down.set_sensitive(False)
        else:
            self.item_delete.set_sensitive(True)
            self.item_up.set_sensitive(path > 0)
            self.item_down.set_sensitive(path < len(model) - 1)

    def on_item_new_clicked(self, button):
        model = self.treeview.get_model()
        model.append([_("label"), 0, _("pattern")])
        self._update_filter_string()
    def _get_selected(self):
        (model, it) = self.treeview.get_selection().get_selected()
        if it:
            path = model.get_path(it)[0]
        else:
            path = None
        return (model, it, path)
    def on_item_delete_clicked(self, button):
        (model, it, path) = self._get_selected()
        model.remove(it)
        self._update_filter_string()
    def on_item_up_clicked(self, button):
        (model, it, path) = self._get_selected()
        model.swap(it, model.get_iter(path - 1))
        self._update_filter_string()
    def on_item_down_clicked(self, button):
        (model, it, path) = self._get_selected()
        model.swap(it, model.get_iter(path + 1))
        self._update_filter_string()
    def on_items_revert_clicked(self, button):
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
            model.append([filt.name, filt.active, filt.value])
   

class PreferencesDialog(gnomeglade.Component):

    def __init__(self, parentapp):
        gnomeglade.Component.__init__(self, paths.ui_dir("preferences.ui"),
                                      "preferencesdialog", ["adjustment1"])
        self.widget.set_transient_for(parentapp.widget)
        self.prefs = parentapp.prefs
        if not self.prefs.use_custom_font:
            self.checkbutton_default_font.set_active(True)
            self.fontpicker.set_sensitive(False)
        else:
            self.checkbutton_default_font.set_active(False)
            self.fontpicker.set_sensitive(True)
            self.fontpicker.set_font_name(self.prefs.custom_font)
        self.fontpicker.set_font_name( self.prefs.custom_font )
        self.spinbutton_tabsize.set_value( self.prefs.tab_size )
        if srcviewer.gsv is not None:
            self.checkbutton_spaces_instead_of_tabs.set_active( self.prefs.spaces_instead_of_tabs )
            self.checkbutton_show_line_numbers.set_active( self.prefs.show_line_numbers )
            self.checkbutton_use_syntax_highlighting.set_active( self.prefs.use_syntax_highlighting )
        else:
            no_sourceview_text = \
                _("Only available if you have gnome-python-desktop installed")
            for w in (self.checkbutton_spaces_instead_of_tabs,
                      self.checkbutton_show_line_numbers,
                      self.checkbutton_use_syntax_highlighting):
                w.set_sensitive(False)
                w.set_tooltip_text(no_sourceview_text)
        # TODO: This doesn't restore the state of character wrapping when word
        # wrapping is disabled, but this is hard with our existing gconf keys
        if self.prefs.edit_wrap_lines != gtk.WRAP_NONE:
            if self.prefs.edit_wrap_lines == gtk.WRAP_CHAR:
                self.checkbutton_split_words.set_active(False)
            self.checkbutton_wrap_text.set_active(True)

        size_group = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)
        size_group.add_widget(self.label1)
        size_group.add_widget(self.label2)
        size_group.add_widget(self.label16)
        use_default = self.prefs.edit_command_type == "internal" or \
                      self.prefs.edit_command_type == "gnome"
        self.system_editor_checkbutton.set_active(use_default)
        self.custom_edit_command_entry.set_sensitive(not use_default)
        self.custom_edit_command_entry.set_text( " ".join(self.prefs.get_custom_editor_command([])) )

        # file filters
        cols = [ (_("Name"), type("")), (_("Active"), type(0)), (_("Pattern"), type("")) ]
        self.filefilter = ListWidget( cols, self.prefs, "filters")
        self.file_filters_tab.pack_start(self.filefilter.widget)
        self.checkbutton_ignore_symlinks.set_active( self.prefs.ignore_symlinks)
        # text filters
        cols = [ (_("Name"), type("")), (_("Active"), type(0)), (_("Regex"), type("")) ]
        self.textfilter = ListWidget( cols, self.prefs, "regexes")
        self.text_filters_tab.pack_start(self.textfilter.widget)
        self.checkbutton_ignore_blank_lines.set_active( self.prefs.ignore_blank_lines )
        # encoding
        self.entry_text_codecs.set_text( self.prefs.text_codecs )
    #
    # editor
    #
    def on_fontpicker_font_set(self, picker):
        self.prefs.custom_font = picker.get_font_name()

    def on_checkbutton_default_font_toggled(self, button):
        use_custom = not button.get_active()
        self.fontpicker.set_sensitive(use_custom)
        self.prefs.use_custom_font = use_custom

    def on_spinbutton_tabsize_changed(self, spin):
        self.prefs.tab_size = int(spin.get_value())
    def on_checkbutton_spaces_instead_of_tabs_toggled(self, check):
        self.prefs.spaces_instead_of_tabs = check.get_active()

    def on_checkbutton_wrap_text_toggled(self, button):
        if not self.checkbutton_wrap_text.get_active():
            self.prefs.edit_wrap_lines = 0
            self.checkbutton_split_words.set_sensitive(False)
        else:
            self.checkbutton_split_words.set_sensitive(True)
            if self.checkbutton_split_words.get_active():
                self.prefs.edit_wrap_lines = 2
            else:
                self.prefs.edit_wrap_lines = 1

    def on_checkbutton_show_line_numbers_toggled(self, check):
        self.prefs.show_line_numbers = check.get_active()
    def on_checkbutton_use_syntax_highlighting_toggled(self, check):
        self.prefs.use_syntax_highlighting = check.get_active()

    def on_system_editor_checkbutton_toggled(self, check):
        use_default = check.get_active()
        self.custom_edit_command_entry.set_sensitive(not use_default)
        if use_default:
            self.prefs.edit_command_type = "gnome"
        else:
            self.prefs.edit_command_type = "custom"

    def on_custom_edit_command_entry_activate(self, entry, *args):
        # Called on "activate" and "focus-out-event"
        self.prefs.edit_command_custom = entry.props.text

    #
    # filters
    #
    def on_checkbutton_ignore_symlinks_toggled(self, check):
        self.prefs.ignore_symlinks = check.get_active()
    def on_checkbutton_ignore_blank_lines_toggled(self, check):
        self.prefs.ignore_blank_lines = check.get_active()

    def on_entry_text_codecs_activate(self, entry, *args):
        # Called on "activate" and "focus-out-event"
        self.prefs.text_codecs = entry.props.text

    def on_response(self, dialog, response_id):
        self.widget.destroy()


class MeldPreferences(prefs.Preferences):
    defaults = {
        "window_size_x": prefs.Value(prefs.INT, 600),
        "window_size_y": prefs.Value(prefs.INT, 600),
        "use_custom_font": prefs.Value(prefs.BOOL,0),
        "custom_font": prefs.Value(prefs.STRING,"monospace, 14"),
        "tab_size": prefs.Value(prefs.INT, 4),
        "spaces_instead_of_tabs": prefs.Value(prefs.BOOL, False),
        "show_line_numbers": prefs.Value(prefs.BOOL, 0),
        "use_syntax_highlighting": prefs.Value(prefs.BOOL, 0),
        "edit_wrap_lines" : prefs.Value(prefs.INT, 0),
        "edit_command_type" : prefs.Value(prefs.STRING, "gnome"), #gnome, custom
        "edit_command_custom" : prefs.Value(prefs.STRING, "gedit"),
        "text_codecs": prefs.Value(prefs.STRING, "utf8 latin1"),
        "ignore_symlinks": prefs.Value(prefs.BOOL,0),
        "vc_console_visible": prefs.Value(prefs.BOOL, 0),
        "color_delete_bg" : prefs.Value(prefs.STRING, "DarkSeaGreen1"),
        "color_delete_fg" : prefs.Value(prefs.STRING, "Red"),
        "color_replace_bg" : prefs.Value(prefs.STRING, "#ddeeff"),
        "color_replace_fg" : prefs.Value(prefs.STRING, "Black"),
        "color_conflict_bg" : prefs.Value(prefs.STRING, "Pink"),
        "color_conflict_fg" : prefs.Value(prefs.STRING, "Black"),
        "color_inline_bg" : prefs.Value(prefs.STRING, "LightSteelBlue2"),
        "color_inline_fg" : prefs.Value(prefs.STRING, "Red"),
        "color_edited_bg" : prefs.Value(prefs.STRING, "gray90"),
        "color_edited_fg" : prefs.Value(prefs.STRING, "Black"),
        "filters" : prefs.Value(prefs.STRING,
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Backups\t1\t#*# .#* ~* *~ *.{orig,bak,swp}\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Version Control\t1\t%s\n") % misc.shell_escape(' '.join(vc.get_plugins_metadata())) + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Binaries\t1\t*.{pyc,a,obj,o,so,la,lib,dll}\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Media\t0\t*.{jpg,gif,png,wav,mp3,ogg,xcf,xpm}")),
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
        "regexes" : prefs.Value(prefs.STRING, _("CVS keywords\t0\t\$\\w+(:[^\\n$]+)?\$\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("C++ comment\t0\t//.*\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("C comment\t0\t/\*.*?\*/\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("All whitespace\t0\t[ \\t\\r\\f\\v]*\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Leading whitespace\t0\t^[ \\t\\r\\f\\v]*\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Script comment\t0\t#.*")),
        "ignore_blank_lines" : prefs.Value(prefs.BOOL, False),
        "toolbar_visible" : prefs.Value(prefs.BOOL, True),
        "statusbar_visible" : prefs.Value(prefs.BOOL, True)
    }

    def __init__(self):
        super(MeldPreferences, self).__init__("/apps/meld", self.defaults)

    def get_current_font(self):
        if self.use_custom_font:
            return self.custom_font
        else:
            if not hasattr(self, "_gconf"):
                return "Monospace 10"
            return self._gconf.get_string('/desktop/gnome/interface/monospace_font_name') or "Monospace 10"

    def get_toolbar_style(self):
        if not hasattr(self, "_gconf"):
            return gtk.TOOLBAR_BOTH
        style = self._gconf.get_string('/desktop/gnome/interface/toolbar_style') or "both"
        style = {"both":gtk.TOOLBAR_BOTH, "text":gtk.TOOLBAR_TEXT,
                 "icon":gtk.TOOLBAR_ICONS, "icons":gtk.TOOLBAR_ICONS,
                 "both_horiz":gtk.TOOLBAR_BOTH_HORIZ,
                 "both-horiz":gtk.TOOLBAR_BOTH_HORIZ
                 }[style]
        return style

    def get_gnome_editor_command(self, files):
        if not hasattr(self, "_gconf"):
            return []
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

