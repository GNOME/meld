### Copyright (C) 2002-2003 Stephen Kennedy <steve9000@users.sf.net>

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

from __future__ import generators

import tempfile
import gobject
import shutil
import time
import copy
import gtk
import os
import re

import tree
import misc
import gnomeglade
import melddoc

CVS_COMMAND = ["cvs", "-z3", "-q"]

################################################################################
#
# Local Functions
#
################################################################################
class Entry:
    def __str__(self):
        return "%s %s\n" % (self.name, (self.path, self.state))
    def __repr__(self):
        return "%s %s\n" % (self.name, (self.path, self.state))
    def get_status(self):
        return ["Non CVS", "", "Error", "", "Newly added", "Modified", "Removed", "Missing"][self.state]

class Dir(Entry):
    def __init__(self, path, name, state):
        self.path = path
        self.parent, self.name = os.path.split(path[:-1])
        self.state = state
        self.isdir = 1
        self.rev = ""
        self.tag = ""
        self.options = ""

class File(Entry):
    def __init__(self, path, name, state, rev="", tag="", options=""):
        assert path[-1] != "/"
        self.path = path
        self.parent, self.name = os.path.split(path)
        self.state = state
        self.isdir = 0
        self.rev = rev
        self.tag = tag
        self.options = options

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
        d = map(lambda x: Dir(x[1],x[0], tree.STATE_NONE), dirs) 
        f = map(lambda x: File(x[1],x[0], tree.STATE_NONE, None), files) 
        return d,f
    try:
        entries += open( os.path.join(directory, "CVS/Entries.Log")).read()
    except IOError, e:
        pass

    retfiles = []
    retdirs = []
    matches = re.findall("^(?:A )?(D?)/([^/]+)/(.+)$(?m)", entries)
    matches.sort()

    for match in matches:
        isdir = match[0]
        name = match[1]
        path = os.path.join(directory, name)
        rev, date, options, tag = match[2].split("/")
        if tag:
            tag = tag[1:]
        if isdir:
            if os.path.exists(path):
                state = tree.STATE_NORMAL
            else:
                state = tree.STATE_MISSING
            retdirs.append( Dir(path,name,state) )
        else:
            if date=="dummy timestamp":
                if rev[0] == "0":
                    state = tree.STATE_NEW
                elif rev[0] == "-":
                    state = tree.STATE_REMOVED
                else:
                    print "Revision '%s' not understood" % rev
            else:
                plus = date.find("+")
                if plus >= 0:
                    cotime = 0
                try:
                    cotime = time.mktime( time.strptime(date) )
                except ValueError, e:
                    if not date.startswith("Result of merge"):
                        print "Unable to parse date '%s' in '%s/CVS/Entries'" % (date, directory)
                    cotime = 0
                try:
                    mtime = os.stat(path).st_mtime
                except OSError:
                    state = tree.STATE_MISSING
                else:
                    if mtime==cotime:
                        state = tree.STATE_NORMAL
                    else:
                        state = tree.STATE_MODIFIED
            retfiles.append( File(path, name, state, rev, tag, options) )
    # find missing
    cvsfiles = map(lambda x: x[1], matches)
    for f,path in files:
        if f not in cvsfiles:
            retfiles.append( File(path, f, tree.STATE_NONE, "") )
    for d,path in dirs:
        if d not in cvsfiles:
            retdirs.append( Dir(path, d, tree.STATE_NONE) )

    return retdirs, retfiles

################################################################################
#
# Local Functions
#
################################################################################
def _find(start):
    if start[-1] != "/": start+="/"
    cfiles = []
    cdirs = []
    try:
        entries = os.listdir(start)
        entries.sort()
    except OSError:
        entries = []
    for f in filter(lambda x: x!="CVS" and x[0]!=".", entries):
        fname = start + f
        lname = fname
        if os.path.isdir(fname):
            cdirs.append( (f, lname) )
        else:
            cfiles.append( (f, lname) )
    return _lookup_cvs_files(cfiles, cdirs)

def recursive_find(start):
    if start=="":
        start="."
    ret = []
    def visit(arg, dirname, names):
        try: names.remove("CVS")
        except ValueError: pass
        dirs, files = _find(dirname)
        ret.extend( dirs )
        ret.extend( files )
    os.path.walk(start, visit, ret)
    return ret

def listdir_cvs(start):
    if start=="":
        start="."
    dirs, files = _find(start)
    return dirs+files


################################################################################
#
# CommitDialog
#
################################################################################
class CommitDialog(gnomeglade.Component):
    def __init__(self, parent):
        gnomeglade.Component.__init__(self, misc.appdir("glade2/cvsview.glade"), "commitdialog")
        self.parent = parent
        self.widget.set_transient_for( parent.widget.get_toplevel() )
        self.changedfiles.set_text( " ".join(parent._get_selected_files()))
        self.widget.show_all()
        self.previousentry.hide()
        self.previouslogs_label.hide()

    def run(self):
        response = self.widget.run()
        buf = self.textview.get_buffer()
        msg = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), 0)
        if response == gtk.RESPONSE_OK:
            self.parent._command_on_selected(CVS_COMMAND + ["commit", "-m", msg] )
        self.previousentry.append_history(1, msg)
        self.widget.destroy()

################################################################################
#
# CvsTreeStore
#
################################################################################

COL_LOCATION, COL_STATUS, COL_REVISION, COL_TAG, COL_OPTIONS, COL_END = range(tree.COL_END, tree.COL_END+6)

class CvsTreeStore(tree.DiffTreeStore):
    def __init__(self):
        types = [type("")] * COL_END
        types[tree.COL_ICON] = type(tree.pixbuf_file)
        gtk.TreeStore.__init__(self, *types)
        self.ntree = 1
        self._setup_default_styles()
        self.textstyle[tree.STATE_MISSING] = '<span foreground="#000088" strikethrough="true" weight="bold">%s</span>'

################################################################################
#
# CvsView
#
################################################################################
class CvsView(melddoc.MeldDoc, gnomeglade.Component):

    __gsignals__ = {
        'create-diff': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))
    }


    MODIFIED_FILTER_MASK, UNKNOWN_FILTER_MASK = 1,2

    filters = [lambda x: (x.state > tree.STATE_NONE),
               lambda x: (x.state > tree.STATE_NORMAL) or (x.isdir and (x.state > tree.STATE_NONE)),
               lambda x: 1, 
               lambda x: (x.state != tree.STATE_NORMAL) or (x.isdir and (x.state > tree.STATE_NONE)) ]

    def __init__(self, prefs):
        melddoc.MeldDoc.__init__(self, prefs)
        gnomeglade.Component.__init__(self, misc.appdir("glade2/cvsview.glade"), "cvsview")
        self.toolbar.set_style( self.prefs.get_toolbar_style() )
        self.tempfiles = []
        self.model = CvsTreeStore()
        self.treeview.set_model(self.model)
        self.treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.treeview.set_headers_visible(1)
        column = gtk.TreeViewColumn("Name")
        renpix = gtk.CellRendererPixbuf()
        rentext = gtk.CellRendererText()
        column.pack_start(renpix, expand=0)
        column.pack_start(rentext, expand=1)
        column.set_attributes(renpix, pixbuf=self.model.column_index(tree.COL_ICON, 0))
        column.set_attributes(rentext, markup=self.model.column_index(tree.COL_TEXT, 0))
        self.treeview.append_column(column)

        def addCol(name, num):
            column = gtk.TreeViewColumn(name)
            rentext = gtk.CellRendererText()
            column.pack_start(rentext, expand=0)
            column.set_attributes(rentext, markup=self.model.column_index(num, 0))
            self.treeview.append_column(column)
            return column

        self.treeview_column_location = addCol("Location", COL_LOCATION)
        addCol("Status", COL_STATUS)
        addCol("Rev", COL_REVISION)
        addCol("Tag", COL_TAG)
        addCol("Options", COL_OPTIONS)

        self.location = None
        self.treeview_column_location.set_visible( self.button_recurse.get_active() )
        size = self.fileentry.size_request()[1]
        self.button_jump.set_size_request(size, size)
        self.button_jump.hide()

    def set_location(self, location):
        self.model.clear()
        self.location = location = os.path.abspath(location or ".")
        self.fileentry.gtk_entry().set_text(location)
        iter = self.model.add_entries( None, [location] )
        self.model.set_state(iter, 0, tree.STATE_NORMAL, isdir=1)
        self.recompute_label()
        self.scheduler.remove_all_tasks()
        self.scheduler.add_task( self._search_recursively_iter().next )

    def recompute_label(self):
        self.label_text = os.path.basename(self.location)
        self.label_changed()

    def _search_recursively_iter(self):
        yield "[%s] Scanning" % self.label_text
        rootpath = self.model.get_path( self.model.get_iter_root() )
        rootname = self.model.value_path( self.model.get_iter(rootpath), 0 )
        prefixlen = 1 + len(rootname)
        todo = [ (rootpath, rootname) ]
        filtermask = 0
        if self.button_modified.get_active():
            filtermask |= self.MODIFIED_FILTER_MASK
        if self.button_noncvs.get_active():
            filtermask |= self.UNKNOWN_FILTER_MASK
        showable = self.filters[filtermask]
        recursive = self.button_recurse.get_active()
        while len(todo):
            todo.sort() # depth first
            path, name = todo.pop(0)
            if path:
                iter = self.model.get_iter( path )
                root = self.model.value_path( iter, 0 )
            else:
                iter = self.model.get_iter_root()
                root = name
            yield "[%s] Scanning %s" % (self.label_text, root[prefixlen:])
            #import time; time.sleep(1.0)
            
            entries = filter(showable, listdir_cvs(root))
            differences = 0
            for e in entries:
                differences |= (e.state != tree.STATE_NORMAL)
                if e.isdir and recursive:
                    todo.append( (None, e.path) )
                    continue
                child = self.model.add_entries(iter, [e.path])
                self.model.set_state( child, 0, e.state, e.isdir )
                def set(col, val):
                    self.model.set_value( child, self.model.column_index(col,0), val)
                set( COL_LOCATION, root[prefixlen:] )
                set( COL_STATUS, e.get_status())
                set( COL_REVISION, e.rev)
                set( COL_TAG, e.tag)
                set( COL_OPTIONS, e.options)
                if e.isdir:
                    todo.append( (self.model.get_path(child), None) )
            if not recursive:
                if len(entries) == 0:
                    self.model.add_empty(iter, "no cvs files")
                if differences or len(path)==1:
                    start = path[:]
                    while len(start) and not self.treeview.row_expanded(start):
                        start = start[:-1]
                    level = len(start)
                    while level < len(path):
                        level += 1
                        self.treeview.expand_row( path[:level], 0)
            else:
                self.treeview.expand_row( (0,), 0)

    def on_fileentry_activate(self, fileentry):
        path = fileentry.get_full_path(0)
        self.set_location(path)

    def on_quit_event(self):
        self.scheduler.remove_all_tasks()
        for f in self.tempfiles:
            if os.path.exists(f):
                shutil.rmtree(f, ignore_errors=1)

    def on_delete_event(self, parent):
        self.on_quit_event()
        return gnomeglade.DELETE_OK

    def on_row_activated(self, treeview, path, tvc):
        iter = self.model.get_iter(path)
        if self.model.iter_has_child(iter):
            if self.treeview.row_expanded(path):
                self.treeview.collapse_row(path)
            else:
                self.treeview.expand_row(path,0)
        else:
            path = self.model.value_path(iter, 0)
            self.run_cvs_diff( [path] )

    def run_cvs_diff_iter(self, paths, empty_patch_ok):
        yield "[%s] Fetching differences." % self.label_text
        difffunc = self._command_iter(CVS_COMMAND + ["diff", "-u"], paths, 0).next
        diff = None
        while type(diff) != type(()):
            diff = difffunc()
            yield 1
        prefix, patch = diff[0], diff[1]
        yield "[%s] Applying patch." % self.label_text
        if patch:
            self.show_patch(prefix, patch)
        elif empty_patch_ok:
            pass #self.statusbar.add_status("%s has no differences" % path)
        else:
            for path in paths:
                self.emit("create-diff", [path])

    def run_cvs_diff(self, paths, empty_patch_ok=0):
        self.scheduler.add_task( self.run_cvs_diff_iter(paths, empty_patch_ok).next )

    def on_button_press_event(self, text, event):
        if event.button==3:
            appdir = misc.appdir("glade2/cvsview.glade")
            popup = gnomeglade.Menu(appdir, "menu_popup")
            popup.show_all()
            popup.popup(None,None,None,event.button,event.time)
        return 0


    def on_button_recurse_toggled(self, button):
        self.treeview_column_location.set_visible( self.button_recurse.get_active() )
        self.refresh()
    def on_button_modified_toggled(self, button):
        self.refresh()
    def on_button_noncvs_toggled(self, button):
        self.refresh()


    def _get_selected_files(self):
        ret = []
        def gather(model, path, iter):
            ret.append( model.value_path(iter,0) )
        s = self.treeview.get_selection()
        s.selected_foreach(gather)
        # remove empty entries and remove trailing slashes
        return map(lambda x: x[-1]!="/" and x or x[:-1], filter(lambda x: x!=None, ret))

    def _command_iter(self, command, files, refresh):
        """Run 'command' on 'files'. Return a tuple of the directory the
           command was executed in and the output of the command."""
        msg = " ".join(command)
        yield "[%s] %s" % (self.label_text, msg)
        if len(files) != 1 :
            workdir = misc.commonprefix(files)
        elif os.path.isdir(files[0]):
            workdir = files[0]
        else:
            workdir = os.path.dirname(files[0])
        kill = len(workdir) and (len(workdir)+1) or 0
        files = filter(lambda x: len(x), map(lambda x: x[kill:], files))
        r = None
        readfunc = misc.read_pipe_iter(command + files, workdir=workdir).next
        try:
            while r == None:
                r = readfunc()
                yield 1
        except IOError, e:
            print "*** ERROR READING PIPE", e
        if refresh:
            self.refresh()
        yield workdir, r

    def _command(self, command, files, refresh=1):
        """Run 'command' on 'files'.
        """
        self.scheduler.add_task( self._command_iter(command, files, refresh).next )
        
    def _command_on_selected(self, command, refresh=1):
        files = self._get_selected_files()
        if len(files):
            self._command(command, files, refresh)
        else:
            self.statusbar.add_status("Select some files first.")

    def on_button_update_clicked(self, object):
        self._command_on_selected(CVS_COMMAND + ["update","-dP"] )
    def on_button_commit_clicked(self, object):
        dialog = CommitDialog( self )
        dialog.run()

    def on_button_add_clicked(self, object):
        self._command_on_selected(CVS_COMMAND + ["add"] )
    def on_button_remove_clicked(self, object):
        self._command_on_selected(CVS_COMMAND + ["rm", "-f"] )
    def on_button_delete_clicked(self, object):
        for f in self._get_selected_files():
            try: os.unlink(f)
            except IOError: pass
        self.refresh()

    def on_button_diff_clicked(self, object):
        files = self._get_selected_files()
        if len(files):
            self.run_cvs_diff(files, empty_patch_ok=1)

    def show_patch(self, prefix, patch):
        if not patch: return

        tmpdir = tempfile.mktemp("-meld")
        self.tempfiles.append(tmpdir)
        os.mkdir(tmpdir)

        regex = re.compile("^Index:\s+(.*$)", re.M)
        files = regex.findall(patch)
        diffs = []
        for file in files:
            destfile = os.path.join(tmpdir,file)
            destdir = os.path.dirname( destfile )

            if not os.path.exists(destdir):
                os.makedirs(destdir)
            pathtofile = os.path.join(prefix, file)
            try:
                shutil.copyfile( pathtofile, destfile)
            except IOError: # it is missing, create empty file
                open(destfile,"w").close()
            diffs.append( (destfile, pathtofile) )

        misc.write_pipe(["patch","--strip=0","--reverse","--directory=%s" % tmpdir], patch)
        for d in diffs:
            self.emit("create-diff", d)

    def refresh(self):
        self.set_location( self.model.value_path( self.model.get_iter_root(), 0 ) )

    def next_diff(self,*args):
        pass

    def on_button_jump_press_event(self, button, event):
        class MyMenu(gtk.Menu):
            def __init__(self, parent, loc, toplev=0):
                gtk.Menu.__init__(self)
                self.cvsview = parent 
                self.loc = loc
                self.scanned = 0
                self.connect("map", self.on_map)
                self.toplev = toplev
            def on_map(self, menu):
                if self.scanned == 0:
                    listing = [ os.path.join(self.loc, p) for p in os.listdir(self.loc)]
                    items = [p for p in listing if os.path.basename(p) != "CVS" and os.path.isdir(p)]
                    if 0 and self.toplev:
                        items.insert(0, "..")
                    for f in items:
                        base = os.path.basename(f)
                        item = gtk.MenuItem( base )
                        item.connect("button-press-event", lambda item,event : self.cvsview.set_location(f) )
                        self.append(item)
                        item.set_submenu( MyMenu(self.cvsview, f, base=="..") )
                    if len(items)==0:
                        item = gtk.MenuItem("<empty>")
                        item.set_sensitive(0)
                        self.append(item)
                    self.scanned = 1
                self.show_all()
        menu = MyMenu( self, os.path.abspath(self.location), 1 )
        menu.popup(None, None, None, event.button, event.time)
        #print event

gobject.type_register(CvsView)

