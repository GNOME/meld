#! python

import tempfile
import gobject
import shutil
import time
import gtk
import os
import re

import misc
import gnomeglade

################################################################################
#
# Local Functions
#
################################################################################
class Entry:
    def __init__(self, path, name):
        self.path = path
        self.isdir = 0
        assert path[-1] != "/"
        self.parent, self.name = os.path.split(path)
        #print self.parent, self.name
    def __str__(self):
        return self.name
    def __repr__(self):
        return self.name

CVS_NONE, CVS_NORMAL, CVS_MODIFIED = range(3)

class Dir(Entry):
    def __init__(self, path, name):
        Entry.__init__(self, path, name)
        if os.path.exists( os.path.join(self.path, "CVS")):
            self.cvs = CVS_NORMAL
        else:
            self.cvs = CVS_NONE
        self.isdir = 1

         
class File(Entry):
    def __init__(self, path, name):
        Entry.__init__(self, path, name)
        try: #todo optimse
            entries = open( os.path.join(self.parent, "CVS/Entries")).read()
            #print "*", self.parent, "*", name
            match = re.search("^/%s/(.+)$" % name, entries, re.M)
            if match:
                self.cvs = 1
                rev, date, junk0, junk1 = match.group(1).split("/")
                if date=="dummy timestamp":
                    self.cvs = CVS_MODIFIED
                else:
                    cotime = time.mktime( time.strptime(date) )
                    mtime = os.stat(path).st_mtime
                    if mtime==cotime:
                        self.cvs = CVS_NORMAL
                    else:
                        self.cvs = CVS_MODIFIED
            else:
                self.cvs = CVS_NONE
        except IOError, e:
            self.cvs = CVS_NONE

################################################################################
#
# Local Functions
#
################################################################################
def _find(start, cull=0):
    cfiles = []
    cdirs = []
    for f in filter(lambda x: x!="CVS", os.listdir(start)):
        fname = os.path.join(start,f)
        lname = fname[cull:]
        if os.path.isdir(fname):
            cdirs.append( (f, lname) )
        else:
            cfiles.append( (f, lname) )
    cfiles.sort()
    cdirs.sort()
    cfiles = map(lambda x: File(x[1],x[0]), cfiles )
    cdirs  = map(lambda x: Dir(x[1],x[0]), cdirs )
    return cdirs, cfiles

def recursive_find(start, progressfunc):
    if start=="":
        start="."
    ret = []
    cull = len(start) + (start[-1]!="/")
    def visit(arg, dirname, names):
        try: names.remove("CVS")
        except ValueError: pass
        dirs, files = _find(dirname, cull)
        ret.extend( dirs )
        ret.extend( files )
        progressfunc()
    os.path.walk(start, visit, ret)
    return ret

def find(start):
    if start=="":
        start="."
    dirs, files = _find(start)
    return dirs+files

################################################################################
#
# CvsView
#
################################################################################
class CvsView(gnomeglade.Component):

    __gsignals__ = {
        'label-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        'working-hard': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_INT,)),
        'create-diff': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))
    }

    MODIFIED_FILTER_MASK, UNKNOWN_FILTER_MASK = 1,2

    filters = [lambda x: x.cvs != CVS_NONE,
               lambda x: x.cvs == CVS_MODIFIED or (x.cvs and x.isdir == 1),
               lambda x: 1, 
               lambda x: x.cvs in [CVS_NONE,CVS_MODIFIED]  ]

    def __init__(self, location=None):
        self.__gobject_init__()
        gnomeglade.Component.__init__(self, misc.appdir("glade2/cvsview.glade"), "cvsview")

        self.image_dir = gnomeglade.load_pixbuf("/usr/share/pixmaps/gnome-folder.png", 14)
        self.image_file= gnomeglade.load_pixbuf("/usr/share/pixmaps/gnome-file-c.png", 14)
        self.treemodel = gtk.TreeStore( type(self.image_dir), type(""), type(""), type(""), type("")  )
        self.treeview.set_model(self.treemodel)
        self.treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        tvc = gtk.TreeViewColumn()
        renpix = gtk.CellRendererPixbuf()
        rentext = gtk.CellRendererText()
        tvc.pack_start(renpix, 0)
        tvc.pack_start(rentext, 1)
        tvc.add_attribute(renpix, "pixbuf", 0)
        tvc.add_attribute(rentext, "text", 1)
        tvc.add_attribute(rentext, "foreground", 2)
        self.treeview.append_column(tvc)

        tvc = gtk.TreeViewColumn()
        rentext = gtk.CellRendererText()
        tvc.pack_start(rentext, 0)
        tvc.add_attribute(rentext, "text", 3)
        #tvc.add_attribute(rentext, "foreground", 2)
        self.treeview.append_column(tvc)

        self.colors = ["#888888", "#000000", "#ff0000"]

        self.location = None
        self.set_location(location)

    def on_row_expanded(self, tree, me, path):
        model = self.treemodel
        location = model.get_value( me, 4 )

        filtermask = 0
        if self.button_modified.get_active():
            filtermask |= self.MODIFIED_FILTER_MASK
        if self.button_unknown.get_active():
            filtermask |= self.UNKNOWN_FILTER_MASK
        showable = self.filters[filtermask]

        if self.button_recurse.get_active():
            def progressfunc():
                self.emit("working-hard", 1)
                self.flushevents()
            files = filter(showable, recursive_find(location, progressfunc))
            for f in files:
                if not f.isdir:
                    iter = model.append(me)
                    model.set_value(iter, 0, self.image_file )
                    model.set_value(iter, 1, f.name )
                    model.set_value(iter, 2, self.colors[f.cvs] )
                    model.set_value(iter, 3, f.parent )
                    model.set_value(iter, 4, f.path)
            self.emit("working-hard", 0)
        else:
            files = filter(showable, find(location))
            for f in files:
                iter = model.append(me)
                model.set_value(iter, 1, f.name)
                if f.isdir:
                    model.set_value(iter, 0, self.image_dir )
                    child = model.append(iter)
                    model.set_value(child, 1, "<empty>" )
                else:
                    model.set_value(iter, 0, self.image_file )
                model.set_value(iter, 2, self.colors[f.cvs] )
                model.set_value(iter, 3, "")
                model.set_value(iter, 4, f.path)
        if len(files):
            child = model.iter_children(me)
            model.remove(child)

    def on_row_collapsed(self, tree, me, path):
        model = self.treemodel
        child = model.iter_children(me)
        while child:
            model.remove(child)
            child = model.iter_children(me)
        child = model.append(me)
        model.set_value(child, 1, "<empty>" )

    def set_location(self, location):
        self.treemodel.clear()
        if location:
            self.location = location
            self.fileentry.gtk_entry().set_text(location)
            root = self.treemodel.append(None)
            self.treemodel.set_value( root, 0, self.image_dir )
            self.treemodel.set_value( root, 1, location )
            self.treemodel.set_value( root, 2, self.colors[1])
            self.treemodel.set_value( root, 3, "")
            self.treemodel.set_value( root, 4, location )
            child = self.treemodel.append(root)
            self.treemodel.set_value(child, 1, "<empty>" )
            self.treeview.expand_row(self.treemodel.get_path(root), 0)
        else: #not location:
            self.location = location
        self.label_changed()

    def on_button_recurse_toggled(self, button):
        self.refresh()
    def on_button_modified_toggled(self, button):
        self.refresh()
    def on_button_unknown_toggled(self, button):
        self.refresh()

    def on_fileentry_activate(self, fileentry):
        self.set_location(fileentry.get_full_path(0))

    def on_key_press_event(self, object, event):
        pass
    def on_key_release_event(self, object, event):
        pass

    def _get_selected_files(self):
        ret = []
        def gather(model, path, iter):
            ret.append( model.get_value(iter,4) )
        s = self.treeview.get_selection()
        s.selected_foreach(gather)
        return filter(lambda x: x!=None, ret)
    def _command(self, command):
        f = self._get_selected_files()
        if len(f):
            r = misc.read_pipe("%s %s" % (command, " ".join(f) ) )
            self.refresh()
            return r
        return None
    def on_button_update_clicked(self, object):
        self._command("cvs update -dP")
    def on_button_commit_clicked(self, object):
        self._command("cvs commit")
    def on_button_add_clicked(self, object):
        self._command("cvs add")
    def on_button_remove_clicked(self, object):
        self._command("cvs rm -f")
    def on_button_delete_clicked(self, object):
        for f in self._get_selected_files():
            try: os.unlink(f)
            except IOError: pass
        self.refresh()
    def on_button_diff_clicked(self, object):
        print "Getting diff"
        patch = self._command("cvs -q diff -u")
        if not patch: return

        print "Copying files"
        tmpdir = tempfile.mktemp("-meld")
        os.mkdir(tmpdir)

        regex = re.compile("^Index:\s+(.*$)", re.M)
        files = regex.findall(patch)
        diffs = []
        for file in files:
            destfile = os.path.join(tmpdir,file)
            destdir = os.path.dirname( destfile )

            if not os.path.exists(destdir):
                os.makedirs(destdir)
            shutil.copyfile(file, destfile)
            diffs.append( (destfile, file) )

        misc.write_pipe("patch --strip=0 --reverse --directory=%s" % tmpdir, patch)
        for d in diffs:
            self.emit("create-diff", d)

    def refresh(self):
        root = self.treemodel.get_path( self.treemodel.get_iter_root() )
        self.treeview.collapse_row(root)
        self.treeview.expand_row(root, 0)
    def save(self,*args):
        pass
    def next_diff(self,*args):
        pass

    def label_changed(self):
        self.emit("label-changed", "[CVS] %s " % self.location)

gobject.type_register(CvsView)

