## python

# system
import sys
import os

# pygtk
import pygtk
pygtk.require("2.0")

# gnome
import gtk
import gtk.glade
import gnome
import gconf

# project
import gnomeglade
import filediff
import misc
import cvsview
import dirdiff

version = "0.6.4b"
developer = 0

################################################################################
#
# BrowseFileDialog
#
################################################################################

class BrowseFileDialog(gnomeglade.Dialog):
    def __init__(self, parentapp, labels, callback, isdir=0):
        gnomeglade.Dialog.__init__(self, misc.appdir("glade2/meld-app.glade"), "browsefile")
        self.widget.set_transient_for(parentapp.widget)
        self.numfile = len(labels)
        self.callback = callback
        self.entries = []
        for i in range(self.numfile):
            l = gtk.Label(labels[i])
            l.set_justify(gtk.JUSTIFY_RIGHT)
            self.table.attach(l , 0, 1, i, i+1, gtk.SHRINK)
            e = gnome.ui.FileEntry("fileentry", "Browse "+labels[i])
            e.set_directory_entry(isdir)
            self.table.attach(e , 1, 2, i, i+1)
            self.entries.append(e)
        self.widget.show_all()
    def on_response(self, dialog, arg):
        if arg==gtk.RESPONSE_OK:
            files = [e.get_full_path(1) or "" for e in self.entries]
            self.callback(files)
        self.widget.destroy()
   
################################################################################
#
# PreferencesDialog
#
################################################################################

class PreferencesDialog(gnomeglade.Dialog):

    def __init__(self, parentapp):
        gnomeglade.Dialog.__init__(self, misc.appdir("glade2/meld-app.glade"), "preferencesdialog")
        self.diff_options_frame.set_sensitive(0)
        self.diff_options_frame.set_sensitive(0)
        self.tabsize_spin.set_sensitive(0)
        self._map_widgets_into_lists( ["draw_style"] )
        self.widget.set_transient_for(parentapp.widget)
        self.gconf = gconf.client_get_default()
        self.gconf.add_dir("/apps/meld/filediff", gconf.CLIENT_PRELOAD_NONE)
        style = self.gconf.get_int("/apps/meld/filediff/draw_style")
        self.draw_style[style].set_active(1)
        self.widget.show()
        fallback = self.gconf.get_string("/apps/meld/filediff/fallback_encoding")
        if fallback:
            self.fallback_entry.gtk_entry().set_property("text", fallback)
            self.fallback_entry.prepend_history(0, fallback )

    def on_menu_draw_style_toggled(self, radio):
        if radio.get_active():
            style = self.draw_style.index(radio)
            self.gconf.set_int("/apps/meld/filediff/draw_style", style)

    def on_tabsize_spin_value_changed(self, spin):
        val = spin.get_value()
        self.gconf.set_int("/apps/meld/filediff/tabsize", val)

    def on_response(self, dialog, arg):
        if arg==gtk.RESPONSE_CLOSE:
            orig = self.gconf.get_string("/apps/meld/filediff/fallback_encoding")
            now = self.fallback_entry.gtk_entry().get_property("text")
            if now != orig:
                self.fallback_entry.prepend_history(0, now)
                self.gconf.set_string("/apps/meld/filediff/fallback_encoding", now)
        self.widget.destroy()

################################################################################
#
# MeldStatusBar
#
################################################################################

class MeldStatusBar:

    def __init__(self, appbar):
        self.appbar = appbar
        self.statusmessages = []
        self.statuscount = []
        self.appbar.set_default("OK")

    def add_status(self, status, timeout=4000, allow_duplicate=0):
        if not allow_duplicate:
            try:
                dup = self.statusmessages.index(status)
            except ValueError:
                pass
            else:
                self.statuscount[dup] += 1
                gtk.timeout_add(timeout, lambda x: self.remove_status(status), 0)
                return

        self.statusmessages.append(status)
        message = self._get_status_message()
        if len(self.statusmessages)==1:
            self.appbar.push(message)
        else:
            self.appbar.set_status(message)
        if timeout:
            gtk.timeout_add(timeout, lambda x: self.remove_status(status), 0)
        self.statuscount.append(1)

    def _get_status_message(self):
        return "[%s]" % "] [".join(self.statusmessages)

    def remove_status(self, status):
        i = self.statusmessages.index(status)
        if self.statuscount[i] == 1:
            self.statusmessages.pop(i)
            self.statuscount.pop(i)
            if len(self.statusmessages)==0:
                self.appbar.pop()
            else:
                message = self._get_status_message()
                self.appbar.set_status(message)
        else:
            self.statuscount[i] -= 1

################################################################################
#
# NotebookLabel
#
################################################################################
class NotebookLabel(gtk.HBox):

    def __init__(self, text="", onclose=None):
        gtk.HBox.__init__(self)
        self.label = gtk.Label(text)
        self.button = gtk.Button("X")
        self.button.set_size_request(14,14) #TODO font height
        self.pack_start( self.label )
        self.pack_start( self.button, expand=0 )
        self.show_all()
        if onclose:
            self.button.connect("clicked", onclose)



################################################################################
#
# MeldNewMenu
#
################################################################################
class MeldNewMenu(gnomeglade.Menu):
    def __init__(self, app):
        gladefile = misc.appdir("glade2/meld-app.glade")
        gnomeglade.Menu.__init__(self, gladefile, "popup_new")
        self.parent = app
    def on_menu_new_diff2_activate(self, *extra):
        self.parent.on_menu_new_diff2_activate()
    def on_menu_new_diff3_activate(self, *extra):
        self.parent.on_menu_new_diff3_activate()
    def on_menu_new_dir2_activate(self, *extra):
        self.parent.on_menu_new_dir2_activate()
    def on_menu_new_dir3_activate(self, *extra):
        self.parent.on_menu_new_dir3_activate()
    def on_menu_new_cvsview_activate(self, *extra):
        self.parent.on_menu_new_cvsview_activate()

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
        gladefile = misc.appdir("glade2/meld-app.glade")
        gnomeglade.GnomeApp.__init__(self, "Meld", version, gladefile, "meldapp")
        self._map_widgets_into_lists( ["menu_file_save_file", "setting_number_panes", "setting_drawstyle"] )
        self.popup_new = MeldNewMenu(self)
        self.statusbar = MeldStatusBar(self.appbar)
        if not developer:#hide magic testing button
            self.toolbar_magic.hide()
            self.setting_filters.hide()

    #
    # General events and callbacks
    #
    def on_key_press_event(self, object, event):
        misc.safe_apply( self.current_doc(), "on_key_press_event", (object,event) )
        return 0

    def on_key_release_event(self, object, event):
        misc.safe_apply( self.current_doc(), "on_key_release_event", (object,event) )
        return 0

    def on_delete_event(self, *extra):
        return self.on_menu_quit_activate()

    def on_switch_page(self, notebook, page, which):
        newdoc = notebook.get_nth_page(which).get_data("pyobject")
        if hasattr(newdoc, "undosequence"):
            newseq = newdoc.undosequence
            self.button_undo.set_sensitive(newseq.can_undo())
            self.button_redo.set_sensitive(newseq.can_redo())
            for i in range(3):
                sensitive = newdoc.num_panes > i
                self.menu_file_save_file[i].set_sensitive(sensitive)
        else:
            self.button_undo.set_sensitive(0)
            self.button_redo.set_sensitive(0)
            for i in range(3):
                self.menu_file_save_file[i].set_sensitive(0)
        nbl = self.notebook.get_tab_label( newdoc.widget )
        self.widget.set_title( nbl.label.get_text() + " - Meld")

    def on_working_hard(self, widget, working):
        "Called" 
        if working:
            self.appbar.get_progress().pulse()
        else:
            self.appbar.get_progress().set_fraction(0)

    def on_notebook_label_changed(self, component, text):
        nbl = self.notebook.get_tab_label( component.widget )
        nbl.label.set_text(text)
        self.widget.set_title(text + " - Meld")

    def on_can_undo(self, undosequence, can):
        self.button_undo.set_sensitive(can)

    def on_can_redo(self, undosequence, can):
        self.button_redo.set_sensitive(can)
    
    #
    # Toolbar and menu items (file)
    #
    def on_menu_new_diff2_activate(self, *extra):
        BrowseFileDialog(self,["Original File", "Modified File"], self.append_filediff)

    def on_menu_new_diff3_activate(self, *extra):
        BrowseFileDialog(self,["Other Changes","Common Ancestor","Local Changes"], self.append_filediff )

    def on_menu_new_dir2_activate(self, *extra):
        BrowseFileDialog(self,["Original Directory", "Modified Directory"], self.append_dirdiff, isdir=1)

    def on_menu_new_dir3_activate(self, *extra):
        BrowseFileDialog(self,["Other Directory", "Original Directory", "Modified Directory"], self.append_dirdiff, isdir=1)

    def on_menu_new_cvsview_activate(self, *extra):
        BrowseFileDialog(self,["Root CVS Directory"], self.append_cvsview, isdir=1)

    def on_menu_save_activate(self, menuitem):
        try:
            index = self.menu_file_save_file.index(menuitem)
        except ValueError:
            index = -1
        try:
            if index >= 0: # save one
                self.current_doc().save_file(index)
            else: # save all
                self.current_doc().save_all()
        except AttributeError:
            pass

    def on_menu_refresh_activate(self, *args):
        self.current_doc().refresh()

    def on_menu_close_activate(self, *extra):
        i = self.notebook.get_current_page()
        if i >= 0:
            page = self.notebook.get_nth_page(i).get_data("pyobject")
            self.try_remove_page(page)

    def on_menu_quit_activate(self, *extra):
        state = []
        for c in self.notebook.get_children():
            try: state.append( c.get_data("pyobject").is_modified() )
            except AttributeError: state.append(0)
        if 1 in state:
            dialog = gnomeglade.Dialog(misc.appdir("glade2/meld-app.glade"), "closedialog")
            dialog.widget.set_transient_for(self.widget.get_toplevel())
            response = dialog.widget.run()
            dialog.widget.destroy()
            if response!=gtk.RESPONSE_OK:
                return gnomeglade.DELETE_ABORT
        for c in self.notebook.get_children():
            misc.safe_apply( c.get_data("pyobject"), "on_quit_event", () )
        self.quit()
        return gnomeglade.DELETE_OK

    #
    # Toolbar and menu items (edit)
    #
    def on_menu_undo_activate(self, *extra):
        self.current_doc().undo()

    def on_menu_redo_activate(self, *extra):
        self.current_doc().redo()

    #
    # Toolbar and menu items (settings)
    #
    def on_menu_number_panes_activate(self, menuitem):
        n = self.setting_number_panes.index(menuitem) + 1
        d = self.current_doc()
        misc.safe_apply( d, "set_num_panes", n )
        for i in range(3): #TODO
            sensitive = d.num_panes > i
            self.menu_file_save_file[i].set_sensitive(sensitive)
            
    def on_menu_filter_activate(self, check):
        print check, check.child.get_text()
        #style = self.setting_drawstyle.index(radio)
        #self.gconf.set_int("/apps/meld/filediff/draw_style", style)

    def on_menu_preferences_activate(self, item):
        PreferencesDialog(self)

    #
    # Toolbar and menu items (help)
    #
    def on_menu_meld_home_page_activate(self, button):
        gnome.url_show("http://meld.sourceforge.net")

    def on_menu_users_manual_activate(self, button):
        gnome.url_show("file:///"+os.path.abspath(misc.appdir("manual/index.html") ) )

    def on_menu_about_activate(self, *extra):
        about = gtk.glade.XML(misc.appdir("glade2/meld-app.glade"),"about").get_widget("about")
        about.set_property("name", "Meld")
        about.set_property("version", version)
        about.show()

    #
    # Toolbar and menu items (misc)
    #
    def on_menu_magic_activate(self, *args):
        pass

    def on_menu_down_activate(self, *args):
        misc.safe_apply( self.current_doc(), "next_diff", gtk.gdk.SCROLL_DOWN )

    def on_menu_up_activate(self, *args):
        misc.safe_apply( self.current_doc(), "next_diff", gtk.gdk.SCROLL_UP )

    def on_toolbar_new_clicked(self, *args):
        self.popup_new.widget.popup(None,None,None,3,0)

    def try_remove_page(self, page):
        "See if a page will allow itself to be removed"
        try:
            deletefunc = page.on_delete_event
        except AttributeError, a:
            delete = gnomeglade.DELETE_OK
        else:
            delete = deletefunc(self)
        if delete == gnomeglade.DELETE_OK:
            i = self.notebook.page_num(page.widget)
            assert(i>=0)
            self.notebook.remove_page(i)

    def append_dirdiff(self, dirs):
        ndirs = len(dirs)
        doc = dirdiff.DirDiff(ndirs, self.statusbar)
        for i in range(ndirs):
            doc.set_location(dirs[i], i)
        nbl = NotebookLabel(onclose=lambda b: self.try_remove_page(doc))
        self.notebook.append_page( doc.widget, nbl)
        self.notebook.set_current_page( self.notebook.page_num(doc.widget) )
        doc.connect("label-changed", self.on_notebook_label_changed)
        doc.connect("create-diff", lambda obj,arg: self.append_filediff(arg) )
        doc.label_changed()
        doc.refresh()

    def append_filediff2(self, file0, file1):
        self.append_filediff( (file0, file1) )
    def append_filediff3(self, file0, file1, file2):
        self.append_filediff( (file0, file1, file2) )
    def append_filediff(self, files):
        assert len(files) in (1,2,3)
        nfiles = len(files)
        doc = filediff.FileDiff(nfiles, self.statusbar)
        for i in range(nfiles):
            doc.set_file(files[i],i)
        seq = doc.undosequence
        seq.clear()
        seq.connect("can-undo", self.on_can_undo)
        seq.connect("can-redo", self.on_can_redo)
        nbl = NotebookLabel(onclose=lambda b: self.try_remove_page(doc))
        self.notebook.append_page( doc.widget, nbl)
        self.notebook.set_current_page( self.notebook.page_num(doc.widget) )
        doc.connect("label-changed", self.on_notebook_label_changed)
        doc.label_changed()
        doc.refresh()

    def append_cvsview(self, locations):
        location = locations[0]
        doc = cvsview.CvsView(self.statusbar, location)
        nbl = NotebookLabel(onclose=lambda b: self.try_remove_page(doc))
        self.notebook.append_page( doc.widget, nbl)
        self.notebook.next_page()
        doc.connect("label-changed", self.on_notebook_label_changed)
        doc.connect("working-hard", self.on_working_hard)
        doc.connect("create-diff", lambda obj,arg: self.append_filediff(arg) )
        doc.label_changed()
        doc.refresh()

    #
    # Current doc actions
    #
    def current_doc(self):
        "Get the current doc or a dummy object if there is no current"
        index = self.notebook.get_current_page()
        if index >= 0:
            return self.notebook.get_nth_page(index).get_data("pyobject")
        class DummyDoc:
            def __getattr__(self, a): return lambda *x: None
        return DummyDoc()

    #
    # Usage
    #
    def usage(self, msg):
        dialog = gnomeglade.Dialog(misc.appdir("glade2/meld-app.glade"),
            "usagedialog")
        dialog.widget.set_transient_for(self.widget.get_toplevel())
        dialog.label_message.set_text(msg)
        dialog.label_usage.set_text(usage_string)
        response = dialog.widget.run()
        dialog.widget.destroy()
        if response == gtk.RESPONSE_CANCEL:
            sys.exit(0)
        
        
        
################################################################################
#
# usage
#
################################################################################
usage_string = """Meld is a file and directory comparison tool. Usage:

    meld                        Start with no windows open
    meld <dir>                  Start with CVS browser
    meld <file> <file> [file]   Start with 2 or 3 way file comparison
    meld <dir> <dir> [dir]      Start with 2 or 3 way directory comparison

CVS browser is alpha. For best results, chdir to the top level
of your source tree and run `meld .'

For more information choose help -> contents.
Report bugs to steve9000@users.sourceforge.net.
"""

################################################################################
#
# Main
#
################################################################################
def main():
    class Unbuffered:
        def __init__(self, file):
            self.file = file
        def write(self, arg):
            self.file.write(arg)
            self.file.flush()
        def __getattr__(self, attr):
            return getattr(self.file, attr)
    sys.stdout = Unbuffered(sys.stdout)

    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print usage_string
        return

    app = MeldApp()
    arg = sys.argv[1:]

    if len(sys.argv) == 1:
        pass

    elif len(arg) == 1:
        a = arg[0]
        if os.path.isdir(a):
            app.append_cvsview( [a] )
        #TODO open cvs diff for a single file
        #elif os.path.isfile(a):
        #   app.append_cvsview( [os.path.dirname(a)] )
        else:
            #app.usage("`%s' is not a directory or file, cannot open cvs view" % arg[0])
            app.usage("`%s' is not a directory, cannot open cvs view" % arg[0])
                
    elif len(arg) in (2,3):
        done = 0
        exists = map( lambda a: os.access(a, os.R_OK), arg)
        if 0 in exists:
            m = "Cannot open "
            for i in range(len(arg)):
                if not exists[i]:
                    m += "`%s'" % arg[i]
            app.usage(m)
            done = 1
        if not done:
            arefiles = map( os.path.isfile, arg)
            if 0 not in arefiles:
                app.append_filediff( arg )
                done = 1
        if not done:
            aredirs = map( os.path.isdir, arg)
            if 0 not in aredirs:
                app.append_dirdiff( arg )
                done = 1
        if not done:
            m = "Cannot compare a mixture of files and directories.\n"
            for i in range(len(arg)):
                m += "(%s)\t`%s'\n" % (arefiles[i] and "file" or "dir", arg[i])
            app.usage(m)
    else:
        app.usage("Wrong number of arguments (Got %i)" % len(arg))

    app.mainloop()

