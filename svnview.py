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

import calendar
import tempfile
import gobject
import shutil
import errno
import time
import copy
import gtk
import os
import re

import tree
import misc
import gnomeglade
import melddoc
import paths

################################################################################
#
# Local Functions
#
################################################################################
class Entry(object):
    states = _("Ignored:Non SVN:::Error::Newly added:Modified:<b>Conflict</b>:Removed:Missing").split(":")
    assert len(states)==tree.STATE_MAX
    def __str__(self):
        return "<%s:%s %s>\n" % (self.__class__, self.name, (self.path, self.state))
    def __repr__(self):
        return "%s %s\n" % (self.name, (self.path, self.state))
    def get_status(self):
        return self.states[self.state]

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

def get_svn_command(command):
    return ["svn", command]

def _lookup_cvs_files(dirs, files):
    "files is array of (name, path). assume all files in same dir"
    if len(files):
        directory = os.path.dirname(files[0][1])
    elif len(dirs):
        directory = os.path.dirname(dirs[0][1])
    else:
        return [],[]

    while 1:
        try:
            entries = os.popen("svn status -Nv "+directory).read()
            break
        except OSError, e:
            if e.errno != errno.EAGAIN:
                raise

    retfiles = []
    retdirs = []
    matches = re.findall("^(.)....\s*\d*\s*(\d*)\s*[^ ]*\s*(.*)$(?m)", entries)
    matches.sort()

    for match in matches:
        name = match[2]
        if(match[0] == "!" or match[0] == "A"):
            # for new or missing files, the findall expression
            # does not supply the correct name 
            name = re.sub(r'^[?]\s*(.*)$', r'\1', name)
        isdir = os.path.isdir(name)
        path = os.path.join(directory, name)
        rev = match[1]
        options = ""
        tag = ""
        if tag:
            tag = tag[1:]
        if isdir:
            if os.path.exists(path):
                state = tree.STATE_NORMAL
            else:
                state = tree.STATE_MISSING
            # svn adds the directory reported to the status list we get.
            if(os.path.basename(name) != os.path.basename(directory)):
                retdirs.append( Dir(path,name,state) )
        else:
            state = { "?": tree.STATE_NONE,
                      "A": tree.STATE_NEW,
                      " ": tree.STATE_NORMAL,
                      "!": tree.STATE_MISSING,
                      "I": tree.STATE_IGNORED,
                      "M": tree.STATE_MODIFIED,
                      "C": tree.STATE_CONFLICT }.get(match[0], tree.STATE_NONE)
            retfiles.append( File(path, name, state, rev, tag, options) )

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
    return _lookup_cvs_files(cdirs, cfiles)

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

def _expand_to_root( treeview, path ):
    """Expand rows from path up to root"""
    start = path[:]
    while len(start) and not treeview.row_expanded(start):
        start = start[:-1]
    level = len(start)
    while level < len(path):
        level += 1
        treeview.expand_row( path[:level], 0)

def _commonprefix(files):
    if len(files) != 1:
        workdir = misc.commonprefix(files)
    else:
        workdir = os.path.dirname(files[0])
    return workdir

################################################################################
#
# CommitDialog
#
################################################################################
class CommitDialog(gnomeglade.Component):
    def __init__(self, parent):
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/cvsview.glade"), "commitdialog")
        self.parent = parent
        self.widget.set_transient_for( parent.widget.get_toplevel() )
        selected = parent._get_selected_files()
        topdir = _commonprefix(selected)
        selected = [ s[len(topdir):] for s in selected ]
        self.changedfiles.set_text( ("(in %s) "%topdir) + " ".join(selected) )
        self.widget.show_all()

    def run(self):
        self.previousentry.list.select_item(0)
        self.textview.grab_focus()
        buf = self.textview.get_buffer()
        buf.place_cursor( buf.get_start_iter() )
        buf.move_mark( buf.get_selection_bound(), buf.get_end_iter() )
        response = self.widget.run()
        msg = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), 0)
        if response == gtk.RESPONSE_OK:
            self.parent._command_on_selected(get_svn_command("commit") + ["-m", msg] )
        if len(msg.strip()):
            self.previousentry.prepend_history(1, msg)
        self.widget.destroy()
    def on_previousentry_activate(self, gentry):
        buf = self.textview.get_buffer()
        buf.set_text( gentry.gtk_entry().get_text() )

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
# DirDiffMenu
#
################################################################################
class CvsMenu(gnomeglade.Component):
    def __init__(self, app, event):
        gladefile = paths.share_dir("glade2/cvsview.glade")
        gnomeglade.Component.__init__(self, gladefile, "menu_popup")
        self.parent = app
        self.widget.popup( None, None, None, 3, event.time )
    def on_diff_activate(self, menuitem):
        self.parent.on_button_diff_clicked( menuitem )
    def on_edit_activate(self, menuitem):
        self.parent._edit_files( self.parent._get_selected_files() )
    def on_update_activate(self, menuitem):
        self.parent.on_button_update_clicked( menuitem )
    def on_commit_activate(self, menuitem):
        self.parent.on_button_commit_clicked( menuitem )
    def on_add_activate(self, menuitem):
        self.parent.on_button_add_clicked( menuitem )
    def on_add_binary_activate(self, menuitem):
        self.parent.on_button_add_binary_clicked( menuitem )
    def on_remove_activate(self, menuitem):
        self.parent.on_button_remove_clicked( menuitem )
    def on_remove_locally_activate(self, menuitem):
        self.parent.on_button_delete_clicked( menuitem )

################################################################################
# filters
################################################################################
entry_modified = lambda x: (x.state >= tree.STATE_NEW) or (x.isdir and (x.state > tree.STATE_NONE))
entry_normal   = lambda x: (x.state == tree.STATE_NORMAL) 
entry_noncvs   = lambda x: (x.state == tree.STATE_NONE) or (x.isdir and (x.state > tree.STATE_IGNORED))
entry_ignored  = lambda x: (x.state == tree.STATE_IGNORED) or x.isdir

################################################################################
#
# CvsView
#
################################################################################
class CvsView(melddoc.MeldDoc, gnomeglade.Component):

    def __init__(self, prefs):
        melddoc.MeldDoc.__init__(self, prefs)
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/cvsview.glade"), "cvsview")
        self.toolbar.set_style( self.prefs.get_toolbar_style() )
        self.tempfiles = []
        self.model = CvsTreeStore()
        self.treeview.set_model(self.model)
        self.treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.treeview.set_headers_visible(1)
        column = gtk.TreeViewColumn( _("Name") )
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

        self.treeview_column_location = addCol( _("Location"), COL_LOCATION)
        addCol(_("Status"), COL_STATUS)
        addCol(_("Rev"), COL_REVISION)
        addCol(_("Tag"), COL_TAG)
        addCol(_("Options"), COL_OPTIONS)

        class ConsoleStream(object):
            def __init__(this, textview):
                this.textview = textview
                b = textview.get_buffer()
                this.mark = b.create_mark("END", b.get_end_iter(), 0)
            def write(this, s):
                if s:
                    b = this.textview.get_buffer()
                    b.insert(b.get_end_iter(), s)
                    this.textview.scroll_mark_onscreen( this.mark )
        self.consolestream = ConsoleStream(self.consoleview)
        self.location = None
        self.treeview_column_location.set_visible( self.button_flatten.get_active() )
        size = self.fileentry.size_request()[1]
        self.button_jump.set_size_request(size, size)
        self.button_jump.hide()
        if not self.prefs.cvs_console_visible:
            self.on_console_view_toggle(self.console_hide_box)

    def set_location(self, location):
        self.model.clear()
        self.location = location = os.path.abspath(location or ".")
        self.fileentry.gtk_entry().set_text(location)
        iter = self.model.add_entries( None, [location] )
        self.treeview.get_selection().select_iter(iter)
        self.model.set_state(iter, 0, tree.STATE_NORMAL, isdir=1)
        self.recompute_label()
        self.scheduler.remove_all_tasks()
        self.scheduler.add_task( self._search_recursively_iter(self.model.get_iter_root()).next )

    def recompute_label(self):
        self.label_text = os.path.basename(self.location)
        self.label_changed()

    def _search_recursively_iter(self, iterstart):
        yield _("[%s] Scanning") % self.label_text
        rootpath = self.model.get_path( iterstart  )
        rootname = self.model.value_path( self.model.get_iter(rootpath), 0 )
        prefixlen = 1 + len( self.model.value_path( self.model.get_iter_root(), 0 ) )
        todo = [ (rootpath, rootname) ]
        filters = []
        if self.button_modified.get_active():
            filters.append( entry_modified )
        if self.button_normal.get_active():
            filters.append( entry_normal )
        if self.button_noncvs.get_active():
            filters.append( entry_noncvs )
        if self.button_ignored.get_active():
            filters.append( entry_ignored )
        def showable(entry):
            for f in filters:
                if f(entry): return 1
        recursive = self.button_flatten.get_active()
        while len(todo):
            todo.sort() # depth first
            path, name = todo.pop(0)
            if path:
                iter = self.model.get_iter( path )
                root = self.model.value_path( iter, 0 )
            else:
                iter = self.model.get_iter_root()
                root = name
            yield _("[%s] Scanning %s") % (self.label_text, root[prefixlen:])
            #import time; time.sleep(1.0)
            
            entries = filter(showable, listdir_cvs(root))
            differences = 0
            for e in entries:
                differences |= (e.state != tree.STATE_NORMAL)
                if e.isdir and recursive:
                    todo.append( (None, e.path) )
                    continue
                child = self.model.add_entries(iter, [e.path])
                self._update_item_state( child, e, root[prefixlen:] )
                if e.isdir:
                    todo.append( (self.model.get_path(child), None) )
            if not recursive: # expand parents
                if len(entries) == 0:
                    self.model.add_empty(iter, _("(Empty)"))
                if differences or len(path)==1:
                    _expand_to_root( self.treeview, path )
            else: # just the root
                self.treeview.expand_row( (0,), 0)

    def on_preference_changed(self, key, value):
        if key == "toolbar_style":
            self.toolbar.set_style( self.prefs.get_toolbar_style() )

    def on_fileentry_activate(self, fileentry):
        path = fileentry.get_full_path(0)
        self.set_location(path)

    def on_quit_event(self):
        self.scheduler.remove_all_tasks()
        for f in self.tempfiles:
            if os.path.exists(f):
                shutil.rmtree(f, ignore_errors=1)

    def on_delete_event(self, appquit=0):
        self.on_quit_event()
        return gtk.RESPONSE_OK

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
        yield _("[%s] Fetching differences") % self.label_text
        #difffunc = self._command_iter(get_svn_command("diff") + ["-u"], paths, 0).next
        difffunc = self._command_iter(get_svn_command("diff"), paths, 0).next
        diff = None
        while type(diff) != type(()):
            diff = difffunc()
            yield 1
        prefix, patch = diff[0], diff[1]
        yield _("[%s] Applying patch") % self.label_text
        if patch:
            self.show_patch(prefix, patch)
        elif empty_patch_ok:
            misc.run_dialog( _("No differences found."), parent=self, messagetype=gtk.MESSAGE_INFO)
        else:
            for path in paths:
                self.emit("create-diff", [path])

    def run_cvs_diff(self, paths, empty_patch_ok=0):
        self.scheduler.add_task( self.run_cvs_diff_iter(paths, empty_patch_ok).next, atfront=1 )

    def on_button_press_event(self, text, event):
        if event.button==3:
            CvsMenu(self, event)
        return 0

    def on_button_flatten_toggled(self, button):
        self.treeview_column_location.set_visible( self.button_flatten.get_active() )
        self.refresh()
    def on_button_filter_toggled(self, button):
        self.refresh()

    def _get_selected_treepaths(self):
        sel = []
        def gather(model, path, iter):
            sel.append( model.get_path(iter) )
        s = self.treeview.get_selection()
        s.selected_foreach(gather)
        return sel

    def _get_selected_files(self):
        sel = []
        def gather(model, path, iter):
            sel.append( model.value_path(iter,0) )
        s = self.treeview.get_selection()
        s.selected_foreach(gather)
        # remove empty entries and remove trailing slashes
        return [ x[-1]!="/" and x or x[:-1] for x in sel if x != None ]

    def _command_iter(self, command, files, refresh):
        """Run 'command' on 'files'. Return a tuple of the directory the
           command was executed in and the output of the command.
        """
        msg = misc.shelljoin(command)
        yield "[%s] %s" % (self.label_text, msg.replace("\n", u"\u21b2") )
        if len(files) == 1 and os.path.isdir(files[0]):
            workdir = os.path.dirname( files[0] )
            files = [ os.path.basename( files[0] ) ]
        else:
            workdir = _commonprefix(files)
            kill = len(workdir) and (len(workdir)+1) or 0
            files = filter(lambda x: len(x), map(lambda x: x[kill:], files))
        r = None
        self.consolestream.write( misc.shelljoin(command+files) + " (in %s)\n" % workdir)
        readfunc = misc.read_pipe_iter(command + files, self.consolestream, workdir=workdir).next
        try:
            while r == None:
                r = readfunc()
                self.consolestream.write(r)
                yield 1
        except IOError, e:
            misc.run_dialog("Error running command.\n'%s'\n\nThe error was:\n%s" % ( misc.shelljoin(command), e),
                parent=self, messagetype=gtk.MESSAGE_ERROR)
        if refresh:
            self.refresh_partial(workdir)
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
            misc.run_dialog( _("Select some files first."), parent=self, messagetype=gtk.MESSAGE_INFO)

    def on_button_update_clicked(self, object):
        self._command_on_selected( get_svn_command("update") )
    def on_button_commit_clicked(self, object):
        dialog = CommitDialog( self )
        dialog.run()

    def on_button_add_clicked(self, object):
        self._command_on_selected(get_svn_command("add") )
    def on_button_add_binary_clicked(self, object):
        self._command_on_selected(get_svn_command("add") + ["-kb"] )
    def on_button_remove_clicked(self, object):
        self._command_on_selected(get_svn_command("rm"))
    def on_button_delete_clicked(self, object):
        files = self._get_selected_files()
        for name in files:
            try:
                if os.path.isfile(name):
                    os.remove(name)
                elif os.path.isdir(name):
                    if misc.run_dialog(_("'%s' is a directory.\nRemove recusively?") % os.path.basename(name),
                            parent = self,
                            buttonstype=gtk.BUTTONS_OK_CANCEL) == gtk.RESPONSE_OK:
                        shutil.rmtree(name)
            except OSError, e:
                misc.run_dialog(_("Error removing %s\n\n%s.") % (name,e), parent = self)
        workdir = _commonprefix(files)
        self.refresh_partial(workdir)

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

    def refresh_partial(self, where):
        if not self.button_flatten.get_active():
            iter = self.find_iter_by_name( where )
            if iter:
                newiter = self.model.insert_after( None, iter) 
                self.model.set_value(newiter, self.model.column_index( tree.COL_PATH, 0), where)
                self.model.set_state(newiter, 0, tree.STATE_NORMAL, isdir=1)
                self.model.remove(iter)
                self.scheduler.add_task( self._search_recursively_iter(newiter).next )
        else: # XXX fixme
            self.refresh()

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

    def _update_item_state(self, iter, cvsentry, location):
        e = cvsentry
        self.model.set_state( iter, 0, e.state, e.isdir )
        def set(col, val):
            self.model.set_value( iter, self.model.column_index(col,0), val)
        set( COL_LOCATION, location )
        set( COL_STATUS, e.get_status())
        set( COL_REVISION, e.rev)
        set( COL_TAG, e.tag)
        set( COL_OPTIONS, e.options)

    def on_file_changed(self, filename):
        iter = self.find_iter_by_name(filename)
        if iter:
            path = self.model.value_path(iter, 0)
            dirs, files = _lookup_cvs_files( [], [ (os.path.basename(path), path)] )
            for e in files:
                if e.path == path:
                    prefixlen = 1 + len( self.model.value_path( self.model.get_iter_root(), 0 ) )
                    self._update_item_state( iter, e, e.parent[prefixlen:])
                    return

    def find_iter_by_name(self, name):
        iter = self.model.get_iter_root()
        path = self.model.value_path(iter, 0)
        while iter:
            if name == path:
                return iter
            elif name.startswith(path): 
                child = self.model.iter_children( iter )
                while child:
                    path = self.model.value_path(child, 0)
                    if name == path:
                        return child
                    elif name.startswith(path):
                        break
                    else:
                        child = self.model.iter_next( child )
                iter = child
            else:
                break
        return None

    def on_console_view_toggle(self, box, event=None):
        if box == self.console_hide_box:
            self.prefs.cvs_console_visible = 0
            self.console_hbox.hide()
            self.console_show_box.show()
        else:
            self.prefs.cvs_console_visible = 1
            self.console_hbox.show()
            self.console_show_box.hide()

    def on_consoleview_populate_popup(self, text, menu):
        item = gtk.ImageMenuItem(gtk.STOCK_CLEAR)
        def activate(*args):
            buf = text.get_buffer()
            buf.delete( buf.get_start_iter(), buf.get_end_iter() )
        item.connect("activate", activate)
        item.show()
        menu.insert( item, 0 )
        item = gtk.SeparatorMenuItem()
        item.show()
        menu.insert( item, 1 )

    def next_diff(self, direction):
        start_iter = self.model.get_iter( (self._get_selected_treepaths() or [(0,)])[-1] )

        def goto_iter(it):
            curpath = self.model.get_path(it)
            for i in range(len(curpath)-1):
                self.treeview.expand_row( curpath[:i+1], 0)
            self.treeview.set_cursor(curpath)

        search = {gtk.gdk.SCROLL_UP : self.model.inorder_search_up}.get(direction, self.model.inorder_search_down)
        for it in search( start_iter ):
            state = int(self.model.get_state( it, 0))
            if state not in (tree.STATE_NORMAL, tree.STATE_EMPTY):
                goto_iter(it)
                return

gobject.type_register(CvsView)

