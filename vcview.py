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

from __future__ import generators

import tempfile
import shutil
import gtk
import os
import re

import tree
import misc
import gnomeglade
import melddoc
import paths
import vc

################################################################################
#
# Local Functions
#
################################################################################

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
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/vcview.glade"), "commitdialog")
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
            self.parent._command_on_selected( self.parent.vc.commit_command(msg) )
        if len(msg.strip()):
            self.previousentry.prepend_history(1, msg)
        self.widget.destroy()
    def on_previousentry_activate(self, gentry):
        buf = self.textview.get_buffer()
        buf.set_text( gentry.gtk_entry().get_text() )

COL_LOCATION, COL_STATUS, COL_REVISION, COL_TAG, COL_OPTIONS, COL_END = range(tree.COL_END, tree.COL_END+6)

class VcTreeStore(tree.DiffTreeStore):
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
class VcMenu(gnomeglade.Component):
    def __init__(self, app, event):
        gladefile = paths.share_dir("glade2/vcview.glade")
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
    def on_revert_activate(self, menuitem):
        self.parent.on_button_revert_clicked( menuitem )
    def on_remove_locally_activate(self, menuitem):
        self.parent.on_button_delete_clicked( menuitem )

################################################################################
# filters
################################################################################
entry_modified = lambda x: (x.state >= tree.STATE_NEW) or (x.isdir and (x.state > tree.STATE_NONE))
entry_normal   = lambda x: (x.state == tree.STATE_NORMAL)
entry_nonvc    = lambda x: (x.state == tree.STATE_NONE) or (x.isdir and (x.state > tree.STATE_IGNORED))
entry_ignored  = lambda x: (x.state == tree.STATE_IGNORED) or x.isdir

################################################################################
#
# VcView
#
################################################################################
class VcView(melddoc.MeldDoc, gnomeglade.Component):

    def __init__(self, prefs):
        melddoc.MeldDoc.__init__(self, prefs)
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/vcview.glade"), "vcview")
        self.toolbar.set_style( self.prefs.get_toolbar_style() )
        self.tempdirs = []
        self.model = VcTreeStore()
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
        if not self.prefs.vc_console_visible:
            self.on_console_view_toggle(self.console_hide_box)

    def set_location(self, location):
        self.model.clear()
        self.location = location = os.path.abspath(location or ".")
        self.fileentry.gtk_entry().set_text(location)
        self.vc = vc.Vc(location)
        it = self.model.add_entries( None, [location] )
        self.treeview.get_selection().select_iter(it)
        self.model.set_state(it, 0, tree.STATE_NORMAL, isdir=1)
        self.recompute_label()
        self.scheduler.remove_all_tasks()
        self.scheduler.add_task( self._search_recursively_iter(self.model.get_iter_root()).next )

    def recompute_label(self):
        self.label_text = os.path.basename(self.location)
        self.label_changed()

    def _search_recursively_iter(self, iterstart):
        yield _("[%s] Scanning %s") % (self.label_text,"")
        rootpath = self.model.get_path( iterstart  )
        rootname = self.model.value_path( self.model.get_iter(rootpath), 0 )
        prefixlen = 1 + len( self.model.value_path( self.model.get_iter_root(), 0 ) )
        todo = [ (rootpath, rootname) ]
        filters = []
        if self.button_modified.get_active():
            filters.append( entry_modified )
        if self.button_normal.get_active():
            filters.append( entry_normal )
        if self.button_nonvc.get_active():
            filters.append( entry_nonvc )
        if self.button_ignored.get_active():
            filters.append( entry_ignored )
        def showable(entry):
            for f in filters:
                if f(entry): return 1
        recursive = self.button_flatten.get_active()
        self.vc.cache_inventory(rootname)
        while len(todo):
            todo.sort() # depth first
            path, name = todo.pop(0)
            if path:
                it = self.model.get_iter( path )
                root = self.model.value_path( it, 0 )
            else:
                it = self.model.get_iter_root()
                root = name
            yield _("[%s] Scanning %s") % (self.label_text, root[prefixlen:])
            #import time; time.sleep(1.0)
            
            entries = filter(showable, self.vc.listdir(root))
            differences = 0
            for e in entries:
                differences |= (e.state != tree.STATE_NORMAL)
                if e.isdir and recursive:
                    todo.append( (None, e.path) )
                    continue
                child = self.model.add_entries(it, [e.path])
                self._update_item_state( child, e, root[prefixlen:] )
                if e.isdir:
                    todo.append( (self.model.get_path(child), None) )
            if not recursive: # expand parents
                if len(entries) == 0:
                    self.model.add_empty(it, _("(Empty)"))
                if differences or len(path)==1:
                    _expand_to_root( self.treeview, path )
            else: # just the root
                self.treeview.expand_row( (0,), 0)
        self.vc.uncache_inventory()

    def on_preference_changed(self, key, value):
        if key == "toolbar_style":
            self.toolbar.set_style( self.prefs.get_toolbar_style() )

    def on_fileentry_activate(self, fileentry):
        path = fileentry.get_full_path(0)
        self.set_location(path)

    def on_quit_event(self):
        self.scheduler.remove_all_tasks()
        for f in self.tempdirs:
            if os.path.exists(f):
                shutil.rmtree(f, ignore_errors=1)

    def on_delete_event(self, appquit=0):
        self.on_quit_event()
        return gtk.RESPONSE_OK

    def on_row_activated(self, treeview, path, tvc):
        it = self.model.get_iter(path)
        if self.model.iter_has_child(it):
            if self.treeview.row_expanded(path):
                self.treeview.collapse_row(path)
            else:
                self.treeview.expand_row(path,0)
        else:
            path = self.model.value_path(it, 0)
            self.run_diff( [path] )

    def run_diff_iter(self, paths, empty_patch_ok):
        yield _("[%s] Fetching differences") % self.label_text
        difffunc = self._command_iter(self.vc.diff_command(), paths, 0).next
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

    def run_diff(self, paths, empty_patch_ok=0):
        self.scheduler.add_task( self.run_diff_iter(paths, empty_patch_ok).next, atfront=1 )

    def on_button_press_event(self, text, event):
        if event.button==3:
            VcMenu(self, event)
        return 0

    def on_button_flatten_toggled(self, button):
        self.treeview_column_location.set_visible( self.button_flatten.get_active() )
        self.refresh()
    def on_button_filter_toggled(self, button):
        self.refresh()

    def _get_selected_treepaths(self):
        sel = []
        def gather(model, path, it):
            sel.append( model.get_path(it) )
        s = self.treeview.get_selection()
        s.selected_foreach(gather)
        return sel

    def _get_selected_files(self):
        sel = []
        def gather(model, path, it):
            sel.append( model.value_path(it,0) )
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
        def relpath(pbase, p):
            assert p.startswith(pbase)
            kill = len(pbase) and (len(pbase)+1) or 0
            return p[kill:] or "."
        if len(files) == 1 and os.path.isdir(files[0]):
            workdir = self.vc.get_working_directory(files[0])
        else:
            workdir = self.vc.get_working_directory( _commonprefix(files) )
        files = [ relpath(workdir, f) for f in files ]
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
        self._command_on_selected( self.vc.update_command() )
    def on_button_commit_clicked(self, object):
        dialog = CommitDialog( self )
        dialog.run()

    def on_button_add_clicked(self, object):
        self._command_on_selected(self.vc.add_command() )
    def on_button_add_binary_clicked(self, object):
        self._command_on_selected(self.vc.add_command(binary=1))
    def on_button_remove_clicked(self, object):
        self._command_on_selected(self.vc.remove_command())
    def on_button_revert_clicked(self, object):
        self._command_on_selected(self.vc.revert_command())
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
            self.run_diff(files, empty_patch_ok=1)

    def show_patch(self, prefix, patch):
        if not patch: return

        tmpdir = tempfile.mkdtemp("-meld")
        self.tempdirs.append(tmpdir)

        regex = re.compile("^diff(.*$)", re.M)
        regex = re.compile(self.vc.PATCH_INDEX_RE, re.M)
        files = [f.split()[-1] for f in regex.findall(patch)]
        diffs = []
        for fname in files:
            destfile = os.path.join(tmpdir,fname)
            destdir = os.path.dirname( destfile )

            if not os.path.exists(destdir):
                os.makedirs(destdir)
            pathtofile = os.path.join(prefix, fname)
            try:
                shutil.copyfile( pathtofile, destfile)
            except IOError: # it is missing, create empty file
                open(destfile,"w").close()
            diffs.append( (destfile, pathtofile) )

        patchcmd = self.vc.patch_command( tmpdir )
        misc.write_pipe(patchcmd, patch)
        for d in diffs:
            self.emit("create-diff", d)

    def refresh(self):
        self.set_location( self.model.value_path( self.model.get_iter_root(), 0 ) )

    def refresh_partial(self, where):
        if not self.button_flatten.get_active():
            it = self.find_iter_by_name( where )
            if it:
                newiter = self.model.insert_after( None, it)
                self.model.set_value(newiter, self.model.column_index( tree.COL_PATH, 0), where)
                self.model.set_state(newiter, 0, tree.STATE_NORMAL, isdir=1)
                self.model.remove(it)
                self.scheduler.add_task( self._search_recursively_iter(newiter).next )
        else: # XXX fixme
            self.refresh()

    def on_button_jump_press_event(self, button, event):
        class MyMenu(gtk.Menu):
            def __init__(self, parent, where, showup=1):
                gtk.Menu.__init__(self)
                self.vcview = parent
                self.map_id = self.connect("map", lambda item: self.on_map(item,where,showup) )
            def add_item(self, name, submenu, showup):
                item = gtk.MenuItem(name)
                if submenu:
                    item.set_submenu( MyMenu(self.vcview, submenu, showup ) )
                self.append( item )
            def on_map(self, item, where, showup):
                if showup:
                    self.add_item("..", os.path.dirname(where), 1 )
                self.populate( where, self.listdir(where) )
                self.show_all()
                self.disconnect(self.map_id)
                del self.map_id
            def listdir(self, d):
                try:
                    return [p for p in os.listdir(d) if os.path.isdir( os.path.join(d,p))]
                except OSError:
                    return []
            def populate(self, where, children):
                for child in children:
                    cc = self.listdir( os.path.join(where, child) )
                    self.add_item( child, len(cc) and os.path.join(where,child), 0 )
        menu = MyMenu( self, os.path.abspath(self.location) )
        menu.popup(None, None, None, event.button, event.time)

    def _update_item_state(self, it, vcentry, location):
        e = vcentry
        self.model.set_state( it, 0, e.state, e.isdir )
        def set(col, val):
            self.model.set_value( it, self.model.column_index(col,0), val)
        set( COL_LOCATION, location )
        set( COL_STATUS, e.get_status())
        set( COL_REVISION, e.rev)
        set( COL_TAG, e.tag)
        set( COL_OPTIONS, e.options)

    def on_file_changed(self, filename):
        it = self.find_iter_by_name(filename)
        if it:
            path = self.model.value_path(it, 0)
            dirs, files = self.vc.lookup_files( [], [ (os.path.basename(path), path)] )
            for e in files:
                if e.path == path:
                    prefixlen = 1 + len( self.model.value_path( self.model.get_iter_root(), 0 ) )
                    self._update_item_state( it, e, e.parent[prefixlen:])
                    return

    def find_iter_by_name(self, name):
        it = self.model.get_iter_root()
        path = self.model.value_path(it, 0)
        while it:
            if name == path:
                return it
            elif name.startswith(path):
                child = self.model.iter_children( it )
                while child:
                    path = self.model.value_path(child, 0)
                    if name == path:
                        return child
                    elif name.startswith(path):
                        break
                    else:
                        child = self.model.iter_next( child )
                it = child
            else:
                break
        return None

    def on_console_view_toggle(self, box, event=None):
        if box == self.console_hide_box:
            self.prefs.vc_console_visible = 0
            self.console_hbox.hide()
            self.console_show_box.show()
        else:
            self.prefs.vc_console_visible = 1
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

