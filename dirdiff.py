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

import diffutil
import errno
import gnomeglade
import gobject
import gtk
import math
import misc
import os
import shutil
import melddoc
import tree

gdk = gtk.gdk

################################################################################
#
# Local Functions
#
################################################################################

def _clamp(val, lower, upper):
    assert lower <= upper
    return min( max(val, lower), upper)

def _uniq(l):
    """Sort the list 'l' and return its unique items"""
    l.sort()
    r = []
    c = None
    for i in l:
        if i != c:
            r.append(i)
            c = i
    return r

def _files_same(lof):
    """Return 1 if all the files in 'lof' have the same contents"""
    # early out if only one file
    if len(lof) <= 1:
        return 1
    # early out if size differs
    arefiles = 1 in [ os.path.isfile(i) for i in lof ]
    if arefiles:
        sizes = [ os.stat(f).st_size for f in lof]
        for s in sizes[1:]:
            if s != sizes[0]:
                return 0
        # compare entire file
        text = [ open(f).read() for f in lof]
        for t in text[1:]:
            if t != text[0]:
                return 0
    return 1

def _not_none(l):
    """Return list with Nones filtered out"""
    return filter(lambda x: x!=None, l)

join = os.path.join


################################################################################
#
# DirDiffMenu
#
################################################################################
class DirDiffMenu(gnomeglade.Component):
    def __init__(self, app):
        gladefile = misc.appdir("glade2/dirdiff.glade")
        gnomeglade.Component.__init__(self, gladefile, "popup")
        self._map_widgets_into_lists( ["copy"] )
        self.parent = app
        self.source_pane = -1
    def get_selected(self):
        assert self.source_pane >= 0
        treeview = self.parent.treeview[self.source_pane]
        selected = []
        treeview.get_selection().selected_foreach(lambda store, path, iter: selected.append( (iter, path) ) )
        return [ misc.struct(name=self.parent.model.value_path(s[0], self.source_pane), path=s[1]) for s in selected]
    def on_popup_compare_activate(self, menuitem):
        get_iter = self.parent.model.get_iter
        for s in self.get_selected():
            self.parent.launch_comparison( get_iter(s.path) )
    def on_popup_copy_activate(self, menuitem):
        destpane = self.copy.index(menuitem)
        sel = self.get_selected()
        sel.reverse()
        model = self.parent.model
        for s in filter(lambda x: x.name!=None, sel):
            iter = model.get_iter(s.path)
            src = model.value_path(iter, self.source_pane)
            dst = model.value_path(iter, destpane)
            try:
                if os.path.isfile(src):
                    dstdir = os.path.dirname( dst )
                    if not os.path.exists( dstdir ):
                        os.makedirs( dstdir )
                    shutil.copy( src, dstdir )
                    self.parent.file_created(s.name, s.path, destpane)
                elif os.path.isdir(src):
                    if not os.path.isdir(dst):
                        os.makedirs( dst )
                    self.parent.file_created(s.name, s.path, destpane)
            except OSError, e:
                misc.run_dialog("Error copying '%s' to '%s'\n\n%s." % (src, dst,e))
    def on_popup_delete_activate(self, menuitem):
        # reverse so paths dont get changed
        sel = self.get_selected()
        sel.reverse()
        for s in sel:
            iter = self.parent.model.get_iter(s.path)
            p = self.parent.model.value_path(iter, self.source_pane )
            try:
                if os.path.isfile(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    os.rmdir(p)
            except OSError, e:
                misc.run_dialog("Error removing %s\n\n%s." % (p,e))
            else:
                self.parent.file_deleted(s.name, s.path, self.source_pane)

################################################################################
#
# DirDiff
#
################################################################################

class DirDiff(melddoc.MeldDoc, gnomeglade.Component):
    """Two or three way diff of directories"""

    __gsignals__ = {
        'create-diff': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))
    }

    def __init__(self, prefs, num_panes):
        melddoc.MeldDoc.__init__(self, prefs)
        gnomeglade.Component.__init__(self, misc.appdir("glade2/dirdiff.glade"), "dirdiff")
        self._map_widgets_into_lists( ["treeview", "fileentry", "diffmap", "scrolledwindow", "linkmap"] )
        self.lock = 0
        self.popup_menu = DirDiffMenu(self)
        self.set_num_panes(num_panes)

        rentext = gtk.CellRendererText()
        renpix = gtk.CellRendererPixbuf()
        for i in range(3):
            self.treeview[i].get_selection().set_mode(gtk.SELECTION_MULTIPLE)
            column = gtk.TreeViewColumn()
            column.pack_start(renpix, expand=0)
            column.pack_start(rentext, expand=1)
            column.set_attributes(renpix, pixbuf=self.model.column_index(tree.COL_ICON,i))
            column.set_attributes(rentext, markup=self.model.column_index(tree.COL_TEXT,i))
            self.treeview[i].append_column(column)
            self.scrolledwindow[i].get_vadjustment().connect("value-changed", self._sync_vscroll )
            self.scrolledwindow[i].get_hadjustment().connect("value-changed", self._sync_hscroll )
        self.linediffs = [[], []]

    def _do_to_others(self, master, objects, methodname, args):
        if self.lock == 0:
            self.lock = 1
            for o in filter(lambda x:x!=master, objects[:self.num_panes]):
                method = getattr(o,methodname)
                method(*args)
            self.lock = 0

    def _sync_vscroll(self, adjustment):
        adjs = map(lambda x: x.get_vadjustment(), self.scrolledwindow)
        self._do_to_others( adjustment, adjs, "set_value", (adjustment.value,) )

    def _sync_hscroll(self, adjustment):
        adjs = map(lambda x: x.get_hadjustment(), self.scrolledwindow)
        self._do_to_others( adjustment, adjs, "set_value", (adjustment.value,) )

    def file_deleted(self, name, path, pane):
        # is file still extant in other pane?
        iter = self.model.get_iter(path)
        files = self.model.value_paths(iter)
        is_present = [ os.path.exists( file ) for file in files ]
        if 1 in is_present:
            self.update_file_state(iter)
        else: # nope its gone
            self.model.remove(iter)

    def file_created(self, name, path, pane):
        iter = self.model.get_iter(path)
        while iter and self.model.get_path(iter) != (0,):
            self.update_file_state( iter )
            iter = self.model.iter_parent(iter)

    def on_fileentry_activate(self, entry):
        locs = [ e.get_full_path(0) for e in self.fileentry[:self.num_panes] ]
        self.set_locations(locs)

    def set_locations(self, locations):
        self.set_num_panes(len(locations))
        locations = [os.path.abspath(l or ".") for l in locations]
        self.model.clear()
        for pane, loc in misc.enumerate(locations):
            self.fileentry[pane].set_filename(loc)
        child = self.model.add_entries(None, locations)
        self.update_file_state(child)
        self.recompute_label()
        self.scheduler.remove_all_tasks()
        self.scheduler.add_task( self._search_recursively_iter().next )

    def _search_recursively_iter(self):
        yield "[%s] Scanning" % self.label_text
        rootpath = self.model.get_path( self.model.get_iter_root() )
        prefixlen = 1 + len( self.model.value_path( self.model.get_iter(rootpath), 0 ) )
        todo = [ rootpath ]
        while len(todo):
            todo.sort() # depth first
            path = todo.pop(0)
            iter = self.model.get_iter( path )
            roots = self.model.value_paths( iter )
            yield "[%s] Scanning %s" % (self.label_text, roots[0][prefixlen:])
            #import time; time.sleep(1.0)
            differences = [0]
            alldirs = []
            allfiles = []
            for i, root in misc.enumerate(roots):
                if os.path.isdir( root ):
                    try:
                        e = os.listdir( root )
                    except OSError, err:
                        self.model.add_error( iter, err.strerror, i )
                        differences = [1]
                    else:
                        e.sort()
                        e = filter(lambda x: not x.endswith(".pyc"), e) #TODO
                        e = filter(lambda x: x.find("CVS") == -1,    e) #TODO
                        alldirs  += filter(lambda x: os.path.isdir(  join(root, x) ), e)
                        allfiles += filter(lambda x: os.path.isfile( join(root, x) ), e)
            alldirs = _uniq(alldirs)
            allfiles = _uniq(allfiles)

            # then directories and files
            if len(alldirs) + len(allfiles) != 0:
                def add_entry(entry):
                    child = self.model.add_entries( iter, [join(r,entry) for r in roots] )
                    differences[0] |= self.update_file_state(child)
                    return child
                for d in alldirs:
                    c = add_entry(d)
                    todo.append( self.model.get_path(c) )
                for f in allfiles:
                    add_entry(f)
            else: # directory is empty, add a placeholder
                self.model.add_empty(iter)
            if differences[0]:
                start = path[:]
                while len(start) and not self.treeview[0].row_expanded(start):
                    start = start[:-1]
                level = len(start)
                while level < len(path):
                    level += 1
                    self.treeview[0].expand_row( path[:level], 0)
        yield "[%s] Done" % self.label_text

    def launch_comparison(self, iter):
        paths = filter(os.path.exists, self.model.value_paths(iter))
        self.emit("create-diff", paths)

    def on_treeview_row_activated(self, view, path, column):
        iter = self.model.get_iter(path)
        files = []
        for i in range(self.num_panes):
            file = self.model.value_path( iter, i )
            if os.path.exists(file):
                files.append(file)
            else:
                files.append(None)
        if files.count(None) != self.num_panes:
            # Its possible to have file 'foo' in one pane and dir 'foo' in another.
            # We want to do the right thing depending on the one clicked.
            clicked_pane = [ t.get_column(0) for t in self.treeview ].index(column)
            while files[clicked_pane] == None: # clicked on missing entry?
                clicked_pane = (clicked_pane+1) % self.num_panes
            if os.path.isfile( files[clicked_pane] ):
                self.emit("create-diff", filter(os.path.isfile, _not_none(files) ))
            else:
                if view.row_expanded(path):
                    view.collapse_row(path)
                else:
                    view.expand_row(path,0)

    def on_treeview_row_expanded(self, view, iter, path):
        self._do_to_others(view, self.treeview, "expand_row", (path,0) )

    def on_treeview_row_collapsed(self, view, me, path):
        self._do_to_others(view, self.treeview, "collapse_row", (path,) )

    def update_file_state(self, iter):
        files = self.model.value_paths(iter)
        is_present = [ os.path.exists( file ) for file in files ]
        all_present = 0 not in is_present
        if all_present:
            all_same = _files_same( files )
            all_present_same = all_same
        else:
            lof = []
            for j in range(len(is_present)):
                if is_present[j]:
                    lof.append( files[j] )
            all_same = 0
            all_present_same = _files_same( lof )
        filename = os.path.basename(file)
        different = 1
        for j in range(self.model.ntree):
            if is_present[j]:
                isdir = os.path.isdir( files[j] )
                if all_same:
                    self.model.set_state(iter, j,  tree.STATE_NORMAL, isdir)
                    different = 0
                elif all_present_same:
                    self.model.set_state(iter, j,  tree.STATE_NEW, isdir)
                else:
                    self.model.set_state(iter, j,  tree.STATE_MODIFIED, isdir)
            else:
                self.model.set_state(iter, j,  tree.STATE_MISSING)
        return different

    def update_diff_maps(self):
        return

    def on_treeview_button_press_event(self, treeview, event):
        # unselect others
        for t in filter(lambda x:x!=treeview, self.treeview[:self.num_panes]):
            sel = t.get_selection()
            sel.unselect_all()
        if event.button == 3:
            pane = self.treeview.index(treeview)
            self.popup_menu.source_pane = pane
            path, col, cellx, celly = treeview.get_path_at_pos( event.x, event.y )
            treeview.set_cursor( path, col, 0)
            for i in range(3):
                c = self.popup_menu.copy[i]
                if i >= self.num_panes:
                    c.hide()
                else:
                    c.show()
                    c.set_sensitive( i != pane)
                    c.get_child().set_label("_Copy to pane %i" % (i+1))
            self.popup_menu.widget.popup( None, None, None, 3, gtk.get_current_event_time() )
            return 1

    def set_num_panes(self, n):
        if n != self.num_panes and n in (1,2,3):
            self.model = tree.DiffTreeStore(n)
            for i in range(n):
                self.treeview[i].set_model(self.model)
            toshow =  self.scrolledwindow[:n] + self.fileentry[:n]
            toshow += self.linkmap[:n-1] + self.diffmap[:n]
            map( lambda x: x.show(), toshow )
            tohide =  self.scrolledwindow[n:] + self.fileentry[n:]
            tohide += self.linkmap[n-1:] + self.diffmap[n:]
            map( lambda x: x.hide(), tohide )
            if self.num_panes != 0: # not first time through
                self.num_panes = n
                self.on_fileentry_activate(None)
            else:
                self.num_panes = n

    def refresh(self):
        root = self.model.get_iter_root()
        roots = self.model.value_paths(root)
        self.set_locations( roots )

    def recompute_label(self):
        root = self.model.get_iter_root()
        filenames = self.model.value_paths(root)
        shortnames = misc.shorten_names(*filenames)
        self.label_text = " : ".join(shortnames)
        self.label_changed()

    def on_diffmap_expose_event(self, area, event):
        return
        diffmapindex = self.diffmap.index(area)
        treeindex = (0, self.num_panes-1)[diffmapindex]
        treeview = self.treeview[treeindex]

        root = self.model.get_iter_root()
        todo = [root]
        lines = []
        while len(todo):
            iter = todo.pop(0)
            path = self.model.get_path(iter)
            foo = self.model.value_path(iter)
            lines.append(foo)
            if treeview.row_expanded(path):
                child = self.model.iter_children(iter)
                while child:
                    todo.append(child)
                    child = self.model.iter_next(child)
        #print lines
        return
            
##

        #TODO need height of arrow button on scrollbar - how do we get that?
        #size_of_arrow = 14
        #hperline = float( self.treeview0.get_allocation().height - 4*size_of_arrow) / self.linediffs[diffmapindex].numlines
        #if hperline > 14:#self.pixels_per_line:
        #    hperline = 14#self.pixels_per_line
        #scaleit = lambda x,s=hperline,o=size_of_arrow: x*s+o
        x0 = 4
        x1 = area.get_allocation().width - 2*x0
        madj = self.scrolledwindow[treeindex].get_vadjustment()

        window = area.window
        window.clear()
        style = area.get_style()
        gc = { "insert":style.light_gc[0],
               "delete":style.light_gc[0],
               "replace":style.light_gc[0],
               "conflict":style.dark_gc[3] }

        for c in self.linediffs[diffmapindex].changes:
            s,e = ( scaleit(c[1]), scaleit(c[2]+(c[1]==c[2])) )
            s,e = math.floor(s), math.ceil(e)
            window.draw_rectangle(gc[c[0]], 1, x0, s, x1, e-s)

gobject.type_register(DirDiff)
