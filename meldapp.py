#! python

# system
import os

# recent versions of python-gnome include pygtk
# older versions don't have it.
try:
    import pygtk
except ImportError:
    pass
else:
    pygtk.require("2.0")

# gnome
import gtk
import gtk.glade
import gnome

# project
import gnomeglade
import filediff
import misc
import cvsview
import dirdiff

version = "0.5.2"

################################################################################
#
# BrowseFileDialog
#
################################################################################

class BrowseFileDialog(gnomeglade.Dialog):
    def __init__(self, parentapp, labels, callback, isdir=0):
        gnomeglade.Dialog.__init__(self, misc.appdir("glade2/meld-app.glade"), "browsefile")
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
        self.table.show_all()
    def on_response(self, dialog, arg):
        if arg==gtk.RESPONSE_OK:
            files = [e.get_full_path(1) or "" for e in self.entries]
            self.callback(files)
        self._widget.destroy() #TODO why ._widget?
   
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
                gtk.timeout_add(timeout, lambda x: self._remove_status(status), 0)
                return

        self.statusmessages.append(status)
        message = self._get_status_message()
        if len(self.statusmessages)==1:
            self.appbar.push(message)
        else:
            self.appbar.set_status(message)
        gtk.timeout_add(timeout, lambda x: self._remove_status(status), 0)
        self.statuscount.append(1)

    def _get_status_message(self):
        return "[%s]" % "] [".join(self.statusmessages)

    def _remove_status(self, status):
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
# MeldApp
#
################################################################################
class MeldApp(gnomeglade.GnomeApp):

    def __init__(self):
        gnomeglade.GnomeApp.__init__(self, "Meld", version, misc.appdir("glade2/meld-app.glade"), "meldapp")
        self._map_widgets_into_lists( ["menu_file_save_file"] )
        self.statusbar = MeldStatusBar(self.appbar)
            
    def on_key_press_event(self, object, event):
        self.current_doc().on_key_press_event(object, event)
    def on_key_release_event(self, object, event):
        self.current_doc().on_key_release_event(object, event)

    def on_switch_page(self, notebook, page, which):
        newdoc = notebook.get_nth_page(which).get_data("pyobject") #TODO why pyobject?
        if hasattr(newdoc, "undosequence"):
            newseq = newdoc.undosequence
            self.button_undo.set_sensitive(newseq.can_undo())
            self.button_redo.set_sensitive(newseq.can_redo())
            for i in range(3):
                sensitive = newdoc.numpanes > i
                self.menu_file_save_file[i].set_sensitive(sensitive)
        else:
            self.button_undo.set_sensitive(0)
            self.button_redo.set_sensitive(0)
            for i in range(3):
                self.menu_file_save_file[i].set_sensitive(0)
        nbl = self.notebook.get_tab_label( newdoc._widget ) #TODO why ._widget?
        self.set_title( nbl.label.get_text() + " : meld")

    #
    # global
    #
    def on_app_delete_event(self, *extra):
        self.quit()
    def on_help_about_activate(self, *extra):
        gtk.glade.XML(misc.appdir("glade2/meld-app.glade"),"about").get_widget("about").show()
    def on_quit_activate(self, *extra):
        self.quit()
    #def on_button_press_event(self, text, event):
    #    if event.button==3:
    #        self.popup_menu.popup(None,None,None,3,0)
    #        return 1
    #    return 0

    #
    # current doc
    #
    def current_doc(self):
        index = self.notebook.get_current_page()
        if index >= 0:
            return self.notebook.get_nth_page(index).get_data("pyobject") #TODO why pyobject?
        class DummyDoc:
            def __getattr__(self, a): return lambda *x: None
        return DummyDoc()
        
    def on_close_doc_activate(self, *extra):
        page = self.notebook.get_current_page()
        if page >= 0:
            self.notebook.remove_page(page)
    def on_new_diff2_activate(self, *extra):
        BrowseFileDialog(self,["Original File", "Modified File"], self.append_filediff)
    def on_new_diff3_activate(self, *extra):
        BrowseFileDialog(self,["Other Changes","Common Ancestor","Local Changes"], self.append_filediff )
    def on_new_dirdiff_activate(self, *extra):
        BrowseFileDialog(self,["Original Directory", "Modified Directory"], self.append_dirdiff, isdir=1)
    def on_new_cvsview_activate(self, *extra):
        self.append_cvsview(None)
    def on_refresh_doc_clicked(self, *args):
        self.current_doc().refresh()
    def on_undo_doc_clicked(self, *extra):
        self.current_doc().undo()
    def on_redo_doc_clicked(self, *extra):
        self.current_doc().redo()

    def on_save_file_activate(self, menuitem):
        index = self.menu_file_save_file.index(menuitem)
        self.current_doc().save_file(index)

    def on_doc_label_changed(self, component, text):
        nbl = self.notebook.get_tab_label( component._widget ) #TODO why ._widget?
        nbl.label.set_text(text)
        self.set_title(text + " : meld")

    def on_can_undo_doc(self, undosequence, can):
        self.button_undo.set_sensitive(can)
    def on_can_redo_doc(self, undosequence, can):
        self.button_redo.set_sensitive(can)
    #
    # methods
    #
    def _remove_page(self, page):
        i = self.notebook.page_num(page._widget)
        assert(i>=0)
        self.notebook.remove_page(i)

    def append_dirdiff(self, files):
        print "XXX",files #self.append_filediff( (file0, file1) )
        doc = dirdiff.DirDiff()

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
        seq.connect("can-undo", self.on_can_undo_doc)
        seq.connect("can-redo", self.on_can_redo_doc)
        nbl = NotebookLabel(onclose=lambda b: self._remove_page(doc))
        self.notebook.append_page( doc._widget, nbl) #TODO why ._widget?
        self.notebook.set_current_page( self.notebook.page_num(doc._widget) )
        doc.connect("label-changed", self.on_doc_label_changed)
        doc.label_changed()
        doc.refresh()
    def append_cvsview(self, location=None):
        doc = cvsview.CvsView(location)
        nbl = NotebookLabel(onclose=lambda b: self._remove_page(doc))
        self.notebook.append_page( doc._widget, nbl) #TODO why ._widget?
        self.notebook.next_page()
        doc.connect("label-changed", self.on_doc_label_changed)
        doc.connect("working-hard", self.on_doc_working_hard)
        doc.connect("create-diff", lambda obj,arg: self.append_filediff(arg) )
        doc.label_changed()
        doc.refresh()

    def on_doc_working_hard(self, widget, working):
        if working:
            self.appbar.get_progress().pulse()
        else:
            self.appbar.get_progress().set_fraction(0)

    def on_down_doc_clicked(self, *args):
        self.current_doc().next_diff( gtk.gdk.SCROLL_DOWN)
    def on_up_doc_clicked(self, *args):
        self.current_doc().next_diff( gtk.gdk.SCROLL_UP)

    def on_save_doc_clicked(self, *args):
        self.current_doc().save()


    def on_menu_help_meld_home_page_activate(self, button):
        gnome.url_show("http://meld.sourceforge.net")
    def on_menu_help_users_manual(self, button):
        gnome.url_show("file:///"+os.path.abspath(misc.appdir("manual/index.html") ) )
