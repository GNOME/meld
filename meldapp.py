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

# system
import sys
import os

# gnome
import gtk
import gtk.glade
import gobject

# project
import paths
import prefs
import gnomeglade
import misc
import filediff
import vcview
import dirdiff
import task

# optional
sourceview_available = 0

for sourceview in "gtksourceview sourceview".split():
    try:
        __import__(sourceview)
        sourceview_available = 1
        break
    except ImportError:
        pass

version = "1.1.1"

# magic developer switch, changes some behaviour
developer = 0

################################################################################
#
# NewDocDialog
#
################################################################################

class NewDocDialog(gnomeglade.Component):

    TYPE = misc.struct(DIFF2=0, DIFF3=1, DIR2=2, DIR3=3, VC=4)
         
    def __init__(self, parentapp, type):
        self.parentapp = parentapp
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "newdialog")
        self._map_widgets_into_lists( ("fileentry", "direntry", "vcentry", "three_way_compare", "tablabel") )
        self.entrylists = self.fileentry, self.direntry, self.vcentry
        self.widget.set_transient_for(parentapp.widget)
        cur_page = type // 2
        self.notebook.set_current_page( cur_page )
        self.widget.show_all()

    def on_entry_activate(self, entry):
        for el in self.entrylists:
            if entry in el:
                i = el.index(entry)
                if i == len(el) - 1:
                    self.button_ok.grab_focus()
                else:
                    el[i+1].gtk_entry().grab_focus()

    def on_three_way_toggled(self, button):
        page = self.three_way_compare.index(button)
        self.entrylists[page][0].set_sensitive( button.get_active() )
        self.entrylists[page][ not button.get_active() ].gtk_entry().grab_focus()

    def on_response(self, dialog, arg):
        if arg==gtk.RESPONSE_OK:
            page = self.notebook.get_current_page()
            paths = [ e.get_full_path(0) or "" for e in self.entrylists[page] ]
            if page < 2 and not self.three_way_compare[page].get_active():
                paths.pop(0)
            methods = (self.parentapp.append_filediff,
                       self.parentapp.append_dirdiff,
                       self.parentapp.append_vcview )
            methods[page](paths)
        self.widget.destroy()

################################################################################
#
# ListWidget
#
################################################################################
class ListWidget(gnomeglade.Component):
    def __init__(self, columns, prefs, key):
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "listwidget")
        self.prefs = prefs
        self.key = key
        self.treeview.set_model( gtk.ListStore( *[c[1] for c in columns] ) )
        view = self.treeview
        def addTextCol(label, colnum, expand=0):
            model = view.get_model()
            rentext = gtk.CellRendererText()
            rentext.set_property("editable", 1)
            def change_text(ren, row, text):
                it = model.get_iter( (int(row),))
                model.set_value( it, colnum, text)
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
                it = model.get_iter( (int(row),))
                model.set_value( it, colnum, not ren.get_active() )
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
    def on_item_new_clicked(self, button):
        model = self.treeview.get_model()
        it = model.append()
        model.set_value(it, 0, "label")
        model.set_value(it, 2, "pattern")
        self._update_filter_string()
    def _get_selected(self):
        selected = []
        self.treeview.get_selection().selected_foreach(
            lambda store, path, it: selected.append( path ) )
        return selected
    def on_item_delete_clicked(self, button):
        model = self.treeview.get_model()
        for s in self._get_selected():
            model.remove( model.get_iter(s) )
        self._update_filter_string()
    def on_item_up_clicked(self, button):
        model = self.treeview.get_model()
        for s in self._get_selected():
            if s[0] > 0: # XXX need model.swap
                old = model.get_iter(s[0])
                it = model.insert( s[0]-1 )
                for i in range(3):
                    model.set_value(it, i, model.get_value(old, i) )
                model.remove(old)
                self.treeview.get_selection().select_iter(it)
        self._update_filter_string()
    def on_item_down_clicked(self, button):
        model = self.treeview.get_model()
        for s in self._get_selected():
            if s[0] < len(model)-1: # XXX need model.swap
                old = model.get_iter(s[0])
                it = model.insert( s[0]+2 )
                for i in range(3):
                    model.set_value(it, i, model.get_value(old, i) )
                model.remove(old)
                self.treeview.get_selection().select_iter(it)
        self._update_filter_string()
    def on_items_revert_clicked(self, button):
        setattr( self.prefs, self.key, self.prefs.get_default(self.key) )
        self._update_filter_model()
    def _update_filter_string(self):
        model = self.treeview.get_model()
        pref = []
        for row in model:
            pref.append("%s\t%s\t%s" % (row[0], row[1], misc.unescape(row[2])))
        setattr( self.prefs, self.key, "\n".join(pref) )
    def _update_filter_model(self):
        model = self.treeview.get_model()
        model.clear()
        for filtstring in getattr( self.prefs, self.key).split("\n"):
            filt = misc.ListItem(filtstring)
            it = model.append()
            model.set_value( it, 0, filt.name)
            model.set_value( it, 1, filt.active)
            model.set_value( it, 2, misc.escape(filt.value))
   
################################################################################
#
# PreferencesDialog
#
################################################################################

class PreferencesDialog(gnomeglade.Component):

    editor_radio_values = {"internal":0, "gnome":1, "custom":2}

    def __init__(self, parentapp):
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/meldapp.glade"), "preferencesdialog")
        self.widget.set_transient_for(parentapp.widget)
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
        self._map_widgets_into_lists( ["editor_command"] )
        if self.prefs.use_custom_font:
            self.radiobutton_custom_font.set_active(1)
        else:
            self.radiobutton_gnome_font.set_active(1)
        self.fontpicker.set_font_name( self.prefs.custom_font )
        self.spinbutton_tabsize.set_value( self.prefs.tab_size )
        self.option_wrap_lines.set_history( self.prefs.edit_wrap_lines )
        self.checkbutton_supply_newline.set_active( self.prefs.supply_newline )
        self.checkbutton_show_line_numbers.set_active( self.prefs.show_line_numbers )
        self.checkbutton_use_syntax_highlighting.set_active( self.prefs.use_syntax_highlighting )
        self.editor_command[ self.editor_radio_values.get(self.prefs.edit_command_type, "internal") ].set_active(1)
        self.gnome_default_editor_label.set_text( "(%s)" % " ".join(self.prefs.get_gnome_editor_command([])) )
        self.custom_edit_command_entry.set_text( " ".join(self.prefs.get_custom_editor_command([])) )
        # display
        self._map_widgets_into_lists( ["draw_style"] )
        self._map_widgets_into_lists( ["toolbar_style"] )
        self.draw_style[self.prefs.draw_style].set_active(1)
        self.toolbar_style[self.prefs.toolbar_style].set_active(1)
        # file filters
        cols = [ ("Name", type("")), ("Active", type(0)), ("Pattern", type("")) ]
        self.filefilter = ListWidget( cols, self.prefs, "filters")
        self.file_filters_box.pack_start(self.filefilter.widget)
        # text filters
        cols = [ ("Name", type("")), ("Active", type(0)), ("Regex", type("")) ]
        self.textfilter = ListWidget( cols, self.prefs, "regexes")
        self.text_filters_box.pack_start(self.textfilter.widget)
        self.checkbutton_ignore_blank_lines.set_active( self.prefs.ignore_blank_lines )
        # encoding
        self.entry_text_codecs.set_text( self.prefs.text_codecs )
        self._map_widgets_into_lists( ["save_encoding"] )
        self.save_encoding[self.prefs.save_encoding].set_active(1)
        # cvs
        self.cvs_quiet_check.set_active( self.prefs.cvs_quiet )
        self.cvs_compression_check.set_active( self.prefs.cvs_compression )
        self.cvs_compression_value_spin.set_value( self.prefs.cvs_compression_value )
        self.cvs_ignore_cvsrc_check.set_active( self.prefs.cvs_ignore_cvsrc )
        self.cvs_binary_fileentry.set_filename( self.prefs.cvs_binary )
        self.cvs_create_missing_check.set_active( self.prefs.cvs_create_missing )
        self.cvs_prune_empty_check.set_active( self.prefs.cvs_prune_empty )
    #
    # treeview
    #
    def on_treeview_cursor_changed(self, tree):
        path, column = tree.get_cursor()
        self.notebook.set_current_page(path[0])
    #
    # editor
    #
    def on_fontpicker_font_set(self, picker, font):
        self.prefs.custom_font = font
    def on_radiobutton_font_toggled(self, radio):
        if radio.get_active():
            custom = radio == self.radiobutton_custom_font
            self.fontpicker.set_sensitive(custom)
            self.prefs.use_custom_font = custom
    def on_spinbutton_tabsize_changed(self, spin):
        self.prefs.tab_size = int(spin.get_value())
    def on_option_wrap_lines_changed(self, option):
        self.prefs.edit_wrap_lines = option.get_history()
    def on_checkbutton_supply_newline_toggled(self, check):
        self.prefs.supply_newline = check.get_active()
    def on_checkbutton_show_line_numbers_toggled(self, check):
        self.prefs.show_line_numbers = check.get_active()
        if check.get_active() and not sourceview_available:
            misc.run_dialog(_("Line numbers are only available if you have pysourceview installed.") )
    def on_checkbutton_use_syntax_highlighting_toggled(self, check):
        self.prefs.use_syntax_highlighting = check.get_active()
        if check.get_active() and not sourceview_available:
            misc.run_dialog(_("Syntax highlighting is only available if you have pysourceview installed.") )
    def on_editor_command_toggled(self, radio):
        if radio.get_active():
            idx = self.editor_command.index(radio)
            for k,v in self.editor_radio_values.items():
                if v == idx:
                    self.prefs.edit_command_type = k
                    break
    #
    # display
    #
    def on_draw_style_toggled(self, radio):
        if radio.get_active():
            self.prefs.draw_style = self.draw_style.index(radio)
    def on_toolbar_style_toggled(self, radio):
        if radio.get_active():
            self.prefs.toolbar_style = self.toolbar_style.index(radio)
    #
    # filters
    #
    def on_checkbutton_ignore_blank_lines_toggled(self, check):
        self.prefs.ignore_blank_lines = check.get_active()

    #
    # encoding
    #
    def on_save_encoding_toggled(self, radio):
        if radio.get_active():
            self.prefs.save_encoding = self.save_encoding.index(radio)
    #
    # cvs
    #
    def on_cvs_quiet_toggled(self, toggle):
        self.prefs.cvs_quiet = toggle.get_active()
    def on_cvs_compression_toggled(self, toggle):
        self.prefs.cvs_compression = toggle.get_active()
    def on_cvs_compression_value_changed(self, spin):
        self.prefs.cvs_compression_value = int(spin.get_value())
    def on_cvs_ignore_cvsrc_toggled(self, toggle):
        self.prefs.cvs_ignore_cvsrc = toggle.get_active()
    def on_cvs_binary_activate(self, fileentry):
        self.prefs.cvs_binary = fileentry.gtk_entry().get_text()
    def on_cvs_create_missing_toggled(self, toggle):
        self.prefs.cvs_create_missing = toggle.get_active()
    def on_cvs_prune_empty_toggled(self, toggle):
        self.prefs.cvs_prune_empty = toggle.get_active()
    def on_response(self, dialog, arg):
        if arg==gtk.RESPONSE_CLOSE:
            self.prefs.text_codecs = self.entry_text_codecs.get_property("text")
            self.prefs.edit_command_custom = self.custom_edit_command_entry.get_property("text")
        self.widget.destroy()

################################################################################
#
# MeldStatusBar
#
################################################################################

class MeldStatusBar(object):

    def __init__(self, task_progress, task_status, doc_status):
        self.task_progress = task_progress
        self.task_status = task_status
        self.doc_status = doc_status

    def set_task_status(self, status):
        self.task_status.pop(1)
        self.task_status.push(1, status)

    def set_doc_status(self, status):
        self.doc_status.pop(1)
        self.doc_status.push(1, status)

################################################################################
#
# NotebookLabel
#
################################################################################
class NotebookLabel(gtk.HBox):

    def __init__(self, iconname, text="", onclose=None):
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
        if onclose:
            self.button.connect("clicked", onclose)

################################################################################
#
# MeldPreferences
#
################################################################################
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
        "cvs_quiet": prefs.Value(prefs.BOOL, 1),
        "cvs_compression": prefs.Value(prefs.BOOL, 1),
        "cvs_compression_value": prefs.Value(prefs.INT, 3),
        "cvs_ignore_cvsrc": prefs.Value(prefs.BOOL, 0),
        "cvs_binary": prefs.Value(prefs.STRING, "/usr/bin/cvs"),
        "cvs_create_missing": prefs.Value(prefs.BOOL, 1),
        "cvs_prune_empty": prefs.Value(prefs.BOOL, 1),
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
        "filters" : prefs.Value(prefs.STRING, "Backups\t1\t#*# .#* ~* *~ *.{orig,bak,swp}\n" + \
                                              "CVS\t1\tCVS\n" + \
                                              "SVN\t1\t.svn\n" + \
                                              "Binaries\t1\t*.{pyc,a,obj,o,so,la,lib,dll}\n" + \
                                              "Media\t0\t*.{jpg,gif,png,wav,mp3,ogg,xcf,xpm}"),
        "regexes" : prefs.Value(prefs.STRING, "CVS keywords\t0\t\$\\w+(:[^\\n$]+)?\$\n" + \
                                              "C++ comment\t0\t//.*\n" + \
                                              "C comment\t0\t/\*.*?\*/\n" + \
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


################################################################################
#
# MeldApp
#
################################################################################
class MeldApp(gnomeglade.GnomeApp):

    #
    # init
    #
    def __init__(self):
        gladefile = paths.share_dir("glade2/meldapp.glade")
        gnomeglade.GnomeApp.__init__(self, "meld", version, gladefile, "meldapp")
        self._map_widgets_into_lists( "settings_drawstyle".split() )
        self.statusbar = MeldStatusBar(self.task_progress, self.task_status, self.doc_status)
        self.prefs = MeldPreferences()
        if not developer:#hide magic testing button
            self.toolbar_magic.hide()
        elif 1:
            def showPrefs(): PreferencesDialog(self)
            gobject.idle_add(showPrefs)
        self.toolbar.set_style( self.prefs.get_toolbar_style() )
        self.prefs.notify_add(self.on_preference_changed)
        self.idle_hooked = 0
        self.scheduler = task.LifoScheduler()
        self.scheduler.connect("runnable", self.on_scheduler_runnable )
        self.widget.set_default_size(self.prefs.window_size_x, self.prefs.window_size_y)
        self.widget.show()

    def on_idle(self):
        ret = self.scheduler.iteration()
        if ret:
            if type(ret) in (type(""), type(u"")):
                self.statusbar.set_task_status(ret)
            elif type(ret) == type(0.0):
                self.statusbar.task_progress.set_fraction(ret)
            else:
                self.statusbar.task_progress.pulse()
        else:
            self.statusbar.task_progress.set_fraction(0)
        if self.scheduler.tasks_pending():
            return 1
        else:
            self.statusbar.set_task_status("")
            self.idle_hooked = 0
            return 0

    def on_scheduler_runnable(self, sched):
        if not self.idle_hooked:
            self.idle_hooked = 1
            gobject.idle_add( self.on_idle )

    def on_preference_changed(self, key, value):
        if key == "toolbar_style":
            self.toolbar.set_style( self.prefs.get_toolbar_style() )

    #
    # General events and callbacks
    #
    def on_delete_event(self, *extra):
        return self.on_menu_quit_activate()

    def on_switch_page(self, notebook, page, which):
        newdoc = notebook.get_nth_page(which).get_data("pyobject")
        newseq = newdoc.undosequence
        self.button_undo.set_sensitive(newseq.can_undo())
        self.button_redo.set_sensitive(newseq.can_redo())
        nbl = self.notebook.get_tab_label( newdoc.widget )
        self.widget.set_title( nbl.label.get_text() + " - Meld")
        self.statusbar.set_doc_status("")
        newdoc.on_switch_event()
        self.scheduler.add_task( newdoc.scheduler )

    def on_notebook_label_changed(self, component, text):
        nbl = self.notebook.get_tab_label( component.widget )
        nbl.label.set_text(text)
        self.widget.set_title(text + " - Meld")
        self.notebook.child_set_property(component.widget, "menu-label", text)

    def on_can_undo(self, undosequence, can):
        self.button_undo.set_sensitive(can)

    def on_can_redo(self, undosequence, can):
        self.button_redo.set_sensitive(can)

    def on_size_allocate(self, window, rect):
        self.prefs.window_size_x = rect.width
        self.prefs.window_size_y = rect.height

    #
    # Toolbar and menu items (file)
    #
    def on_menu_file_new_activate(self, menuitem):
        NewDocDialog(self, NewDocDialog.TYPE.DIFF2)

    def on_menu_save_activate(self, menuitem):
        self.current_doc().save()

    def on_menu_save_as_activate(self, menuitem):
        pane = self.current_doc()._get_focused_pane()
        if pane >= 0:
            self.current_doc().save_file(pane, 1)

    def on_menu_refresh_activate(self, *args):
        self.current_doc().refresh()

    def on_menu_close_activate(self, *extra):
        i = self.notebook.get_current_page()
        if i >= 0:
            page = self.notebook.get_nth_page(i).get_data("pyobject")
            self.try_remove_page(page)

    def on_menu_quit_activate(self, *extra):
        if not developer:
            for c in self.notebook.get_children():
                response = c.get_data("pyobject").on_delete_event(appquit=1)
                if response == gtk.RESPONSE_CANCEL:
                    return gtk.RESPONSE_CANCEL
                elif response == gtk.RESPONSE_CLOSE:
                    break
        for c in self.notebook.get_children():
            c.get_data("pyobject").on_quit_event()
        self.quit()
        return gtk.RESPONSE_CLOSE

    #
    # Toolbar and menu items (edit)
    #
    def on_menu_undo_activate(self, *extra):
        self.current_doc().on_undo_activate()

    def on_menu_redo_activate(self, *extra):
        self.current_doc().on_redo_activate()
  
    def on_menu_find_activate(self, *extra):
        self.current_doc().on_find_activate()

    def on_menu_find_next_activate(self, *extra):
        self.current_doc().on_find_next_activate()

    def on_menu_replace_activate(self, *extra):
        self.current_doc().on_replace_activate()

    def on_menu_copy_activate(self, *extra):
        self.current_doc().on_copy_activate()

    def on_menu_cut_activate(self, *extra):
        self.current_doc().on_cut_activate()

    def on_menu_paste_activate(self, *extra):
        self.current_doc().on_paste_activate()

    #
    # Toolbar and menu items (settings)
    #
    def on_menu_filter_activate(self, check):
        print check, check.child.get_text()

    def on_menu_preferences_activate(self, item):
        PreferencesDialog(self)

    #
    # Toolbar and menu items (help)
    #
    def on_menu_meld_home_page_activate(self, button):
        gnomeglade.url_show("http://meld.sourceforge.net")

    def on_menu_help_bug_activate(self, button):
        gnomeglade.url_show("http://bugzilla.gnome.org/buglist.cgi?product=meld")

    def on_menu_users_manual_activate(self, button):
        gnomeglade.url_show("ghelp:///"+os.path.abspath(paths.help_dir("C/meld.xml") ))

    def on_menu_about_activate(self, *extra):
        about = gtk.glade.XML(paths.share_dir("glade2/meldapp.glade"),"about").get_widget("about")
        about.set_property("name", "Meld")
        about.set_property("version", version)
        about.show()

    #
    # Toolbar and menu items (misc)
    #
    def on_menu_magic_activate(self, *args):
        for i in range(8):
            self.append_filediff( ("ntest/file%ia"%i, "ntest/file%ib"%i) )
            #self.append_filediff( ("ntest/file9a", "ntest/file9b") )
        pass

    def on_menu_edit_down_activate(self, *args):
        misc.safe_apply( self.current_doc(), "next_diff", gtk.gdk.SCROLL_DOWN )

    def on_menu_edit_up_activate(self, *args):
        misc.safe_apply( self.current_doc(), "next_diff", gtk.gdk.SCROLL_UP )

    def on_toolbar_new_clicked(self, *args):
        NewDocDialog(self, NewDocDialog.TYPE.DIFF2)

    def on_toolbar_stop_clicked(self, *args):
        self.current_doc().stop()

    def try_remove_page(self, page):
        "See if a page will allow itself to be removed"
        if page.on_delete_event() == gtk.RESPONSE_OK:
            self.scheduler.remove_scheduler( page.scheduler )
            i = self.notebook.page_num( page.widget )
            assert(i>=0)
            self.notebook.remove_page(i)

    def on_file_changed(self, srcpage, filename):
        for c in self.notebook.get_children():
            page = c.get_data("pyobject")
            if page != srcpage:
                page.on_file_changed(filename)

    def _append_page(self, page, icon):
        nbl = NotebookLabel(icon, onclose=lambda b: self.try_remove_page(page))
        self.notebook.append_page( page.widget, nbl)
        self.notebook.set_current_page( self.notebook.page_num(page.widget) )
        self.scheduler.add_scheduler(page.scheduler)
        page.connect("label-changed", self.on_notebook_label_changed)
        page.connect("file-changed", self.on_file_changed)
        page.connect("create-diff", lambda obj,arg: self.append_filediff(arg) )
        page.connect("status-changed", lambda junk,arg: self.statusbar.set_doc_status(arg) )

    def append_dirdiff(self, dirs):
        assert len(dirs) in (1,2,3)
        doc = dirdiff.DirDiff(self.prefs, len(dirs))
        self._append_page(doc, "tree-folder-normal.png")
        doc.set_locations(dirs)

    def append_filediff(self, files):
        assert len(files) in (1,2,3)
        doc = filediff.FileDiff(self.prefs, len(files))
        seq = doc.undosequence
        seq.clear()
        seq.connect("can-undo", self.on_can_undo)
        seq.connect("can-redo", self.on_can_redo)
        self._append_page(doc, "tree-file-normal.png")
        doc.set_files(files)

    def append_diff(self, paths):
        aredirs = [ os.path.isdir(p) for p in paths ]
        arefiles = [ os.path.isfile(p) for p in paths ]
        if (1 in aredirs) and (1 in arefiles):
            misc.run_dialog( _("Cannot compare a mixture of files and directories.\n"),
                    parent = self,
                    buttonstype = gtk.BUTTONS_OK)
        elif 1 in aredirs:
            self.append_dirdiff(paths)
        else:
            self.append_filediff(paths)

    def append_vcview(self, locations):
        assert len(locations) in (1,)
        location = locations[0]
        doc = vcview.VcView(self.prefs)
        self._append_page(doc, "vc-icon.png")
        doc.set_location(location)

    #
    # Current doc actions
    #
    def current_doc(self):
        "Get the current doc or a dummy object if there is no current"
        index = self.notebook.get_current_page()
        if index >= 0:
            return self.notebook.get_nth_page(index).get_data("pyobject")
        class DummyDoc(object):
            def __getattr__(self, a): return lambda *x: None
        return DummyDoc()

    #
    # Usage
    #
    def usage(self, msg):
        response = misc.run_dialog(msg,
            self,
            gtk.MESSAGE_ERROR,
            gtk.BUTTONS_NONE,
            [(gtk.STOCK_QUIT, gtk.RESPONSE_CANCEL), (gtk.STOCK_OK, gtk.RESPONSE_OK)] )
        if response == gtk.RESPONSE_CANCEL:
            sys.exit(0)
        
        
        
################################################################################
#
# usage
#
################################################################################
usage_string = _("""Meld is a file and directory comparison tool. Usage:

    meld                        Start with no windows open
    meld <dir>                  Start with VC browser in 'dir'
    meld <file>                 Start with VC diff of 'file'
    meld <file> <file> [file]   Start with 2 or 3 way file comparison
    meld <dir>  <dir>  [dir]    Start with 2 or 3 way directory comparison

Options:
    -h, --help                  Show this help text and exit
    -v, --version               Display the version and exit

For more information choose help -> contents.
Report bugs at http://bugzilla.gnome.org/buglist.cgi?product=meld
Discuss meld at http://mail.gnome.org/mailman/listinfo/meld-list
""")

version_string = _("""Meld %s
Written by Stephen Kennedy <stevek@gnome.org>""") % version

################################################################################
#
# Main
#
################################################################################
def main():
    class Unbuffered(object):
        def __init__(self, file):
            self.file = file
        def write(self, arg):
            self.file.write(arg)
            self.file.flush()
        def __getattr__(self, attr):
            return getattr(self.file, attr)
    sys.stdout = Unbuffered(sys.stdout)
    args = sys.argv[1:]

    if len(args) >= 2:
        if "-h" in args or "--help" in args:
            print usage_string
            return
        if "-v" in args or "--version" in args:
            print version_string
            return

    app = MeldApp()

    if len(args) == 0:
        pass

    elif len(args) == 1:
        a = args[0]
        if os.path.isfile(a):
            doc = vcview.VcView(app.prefs)
            def cleanup():
                app.scheduler.remove_scheduler(doc.scheduler)
            app.scheduler.add_task(cleanup)
            app.scheduler.add_scheduler(doc.scheduler)
            doc.set_location( os.path.dirname(a) )
            doc.connect("create-diff", lambda obj,arg: app.append_diff(arg) )
            doc.run_diff([a])
        else:
            app.append_vcview( [a] )
                
    elif len(args) in (2,3):
        app.append_diff(args)
    else:
        app.usage( _("Wrong number of arguments (Got %i)") % len(args))

    app.main()

