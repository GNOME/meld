#! python

# todo use .cvsignore

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
        return "%s %s" % (self.name, (self.path, self.isdir, self.parent))
    def __repr__(self):
        return self.name

CVS_NONE, CVS_NORMAL, CVS_MODIFIED, CVS_MISSING = range(4)

class Dir(Entry):
    def __init__(self, path, name, state):
        Entry.__init__(self, path, name)
        self.cvs = state 
        self.isdir = 1

class File(Entry):
    def __init__(self, path, name, status):
        Entry.__init__(self, path, name)
        self.cvs = status

def _lookup_cvs_files(files, dirs):
    "files is array of (name, path). assume all files in same dir"
    if len(files):
        directory = os.path.dirname(files[0][1])
    elif len(dirs):
        directory = os.path.dirname(dirs[0][1])
    else:
        return [],[]

    try:
        entries = open( os.path.join(directory, "CVS/Entries")).read()
    except IOError, e:
        d = map(lambda x: Dir(x[1],x[0], CVS_NONE), dirs) 
        f = map(lambda x: File(x[1],x[0], CVS_NONE), files) 
        return d,f

    retfiles = []
    retdirs = []
    matches = re.findall("^(D?)/([^/]+)/(.+)$(?m)", entries)

    for match in matches:
        isdir = match[0]
        name = match[1]
        path = os.path.join(directory, name)
        rev, date, junk0, junk1 = match[2].split("/")
        if isdir:
            state = os.path.exists(path) and CVS_NORMAL or CVS_MISSING
            retdirs.append( Dir(path,name,state) )
        else:
            if date=="dummy timestamp":
                state = CVS_MODIFIED
            else:
                cotime = time.mktime( time.strptime(date) )
                try:
                    mtime = os.stat(path).st_mtime
                except OSError:
                    state = CVS_MISSING
                else:
                    if mtime==cotime:
                        state = CVS_NORMAL
                    else:
                        state = CVS_MODIFIED
            retfiles.append( File(path, name, state) )
    # find missing
    cvsfiles = map(lambda x: x[1], matches)
    for f,path in files:
        if f not in cvsfiles:
            retfiles.append( File(path, f, CVS_NONE) )
    for d,path in dirs:
        if d not in cvsfiles:
            retdirs.append( Dir(path, d, CVS_NONE) )

    return retdirs, retfiles

################################################################################
#
# Local Functions
#
################################################################################
def _find(start):
    cfiles = []
    cdirs = []
    try:
        entries = os.listdir(start)
    except OSError:
        entries = []
    for f in filter(lambda x: x!="CVS", entries):
        fname = os.path.join(start,f)
        lname = fname
        if os.path.isdir(fname):
            cdirs.append( (f, lname) )
        else:
            cfiles.append( (f, lname) )
    return _lookup_cvs_files(cfiles, cdirs)

def recursive_find(start, progressfunc):
    if start=="":
        start="."
    ret = []
    def visit(arg, dirname, names):
        try: names.remove("CVS")
        except ValueError: pass
        dirs, files = _find(dirname)
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
               lambda x: x.cvs > CVS_NORMAL or (x.cvs and x.isdir),
               lambda x: 1, 
               lambda x: x.cvs in [CVS_NONE,CVS_MODIFIED,CVS_MISSING] or x.isdir  ]

    def __init__(self, location=None):
        self.__gobject_init__()
        gnomeglade.Component.__init__(self, misc.appdir("glade2/cvsview.glade"), "cvsview")

        self.image_dir = gnomeglade.load_pixbuf("/usr/share/pixmaps/gnome-folder.png", 14)
        self.image_file= gnomeglade.load_pixbuf("/usr/share/pixmaps/gnome-file-c.png", 14)
        self.treemodel = gtk.TreeStore( type(self.image_dir), type(""), type(""), type(""), gobject.TYPE_PYOBJECT )
        self.treeview.set_model(self.treemodel)
        self.treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.treeview.set_headers_visible(0)
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
        self.treeview.append_column(tvc)

        self.colors = ["#888888", "#000000", "#ff0000", "#0000ff"]
        self.status = ["", "", "modified", "missing"]

        self.location = None
        self.set_location(location)

    def on_row_activated(self, treeview, path, tvc):
        iter = self.treemodel.get_iter(path)
        entry = self.treemodel.get_value(iter, 4)
        if not entry: return
        if entry.isdir:
            if self.treeview.row_expanded(path):
                self.treeview.collapse_row(path)
            else:
                self.treeview.expand_row(path,0)
        else:
            if entry.cvs == CVS_MODIFIED:
                patch = misc.read_pipe("cvs -z3 diff -u %s" % entry.path)
                if patch:
                    print entry.path, "\n", patch
                    self.show_patch(patch)
                    return
            self.emit("create-diff", [entry.path])

    def on_row_expanded(self, tree, me, path):
        model = self.treemodel
        location = model.get_value( me, 4 ).path

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
                    model.set_value(iter, 4, f)
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
                model.set_value(iter, 3, self.status[f.cvs])
                model.set_value(iter, 4, f)
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
            self.treemodel.set_value( root, 4, Dir(location,location, CVS_NORMAL) )
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
            ret.append( model.get_value(iter,4).path )
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
        self._command("cvs commit -m ''")
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
        patch = self._command("cvs -z3 -q diff -u")
        print patch
        self.show_patch(patch)

    def show_patch(self, patch):
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
            try:
                shutil.copyfile(file, destfile)
            except IOError: # missing, create empty file
                open(destfile,"w").close()
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

