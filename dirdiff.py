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
import filecmp
import re

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

    arefiles = 1 in [ os.path.isfile(i) for i in lof ] 
    if arefiles:             
        first=lof[0]
        for f in lof[1:]:
            if not filecmp.cmp(first, f):
                return 0            
    return 1

def _not_none(l):
    """Return list with Nones filtered out"""
    return filter(lambda x: x!=None, l)

join = os.path.join


COL_NEWER = tree.COL_END + 1
pixbuf_newer = gnomeglade.load_pixbuf(misc.appdir("glade2/pixmaps/tree-file-newer.png"), 14)
TYPE_PIXBUF = type(pixbuf_newer)

################################################################################
#
# DirDiffTreeStore
#
################################################################################
class DirDiffTreeStore(tree.DiffTreeStore):
    def __init__(self, ntree):
        types = [type("")] * COL_NEWER * ntree
        types[tree.COL_ICON*ntree:tree.COL_ICON*ntree+ntree] = [TYPE_PIXBUF] * ntree
        types[COL_NEWER*ntree:COL_NEWER*ntree+ntree] = [TYPE_PIXBUF] * ntree
        gtk.TreeStore.__init__(self, *types)
        self.ntree = ntree
        self._setup_default_styles()

################################################################################
#
# EmblemCellRenderer
#
################################################################################
class EmblemCellRenderer(gtk.GenericCellRenderer):
    __gproperties__ = {
        'pixbuf': (gtk.gdk.Pixbuf, 'pixmap property', 'the base pixmap', gobject.PARAM_READWRITE),
        'emblem': (gtk.gdk.Pixbuf, 'emblem property', 'the emblem pixmap', gobject.PARAM_READWRITE),
    }
    def __init__(self):
        self.__gobject_init__()
        self.renderer = gtk.CellRendererPixbuf()
        self.pixbuf = None
        self.emblem = None

    def do_set_property(self, pspec, value):
        if not hasattr(self, pspec.name):
            raise AttributeError, 'unknown property %s' % pspec.name
        setattr(self, pspec.name, value)
    def do_get_property(self, pspec):
        return getattr(self, pspec.name)

    def on_render(self, window, widget, background_area, cell_area, expose_area, flags):
        r = self.renderer
        r.set_property("pixbuf", self.pixbuf)
        r.render(window, widget, background_area, cell_area, expose_area, flags)
        r.set_property("pixbuf", self.emblem)
        r.render(window, widget, background_area, cell_area, expose_area, flags)

    def on_get_size(self, widget, cell_area):
        if not hasattr(self, "size"):
            r = self.renderer
            r.set_property("pixbuf", self.pixbuf)
            self.size = r.get_size(widget, cell_area)
        return self.size
gobject.type_register(EmblemCellRenderer)
################################################################################
#
# DirDiffMenu
#
################################################################################
class DirDiffMenu(gnomeglade.Component):
    def __init__(self, app):
        gladefile = misc.appdir("glade2/dirdiff.glade")
        gnomeglade.Component.__init__(self, gladefile, "popup")
        self.parent = app
    def popup_in_pane( self, pane ):
        self.copy_left.set_sensitive( pane > 0 )
        self.copy_right.set_sensitive( pane+1 < self.parent.num_panes )
        self.widget.popup( None, None, None, 3, gtk.get_current_event_time() )
    def on_popup_compare_activate(self, menuitem):
        self.parent.launch_comparisons_on_selected()
    def on_popup_copy_left_activate(self, menuitem):
        self.parent.on_button_copy_left_clicked( None )
    def on_popup_copy_right_activate(self, menuitem):
        self.parent.on_button_copy_right_clicked( None )
    def on_popup_delete_activate(self, menuitem):
        self.parent.on_button_delete_clicked( None )

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
        self.toolbar.set_style( self.prefs.get_toolbar_style() )
        self._map_widgets_into_lists( ["treeview", "fileentry", "diffmap", "scrolledwindow", "linkmap"] )
        self.lock = 0
        self.popup_menu = DirDiffMenu(self)
        self.set_num_panes(num_panes)
        self.on_treeview_focus_out_event(None, None)

        for i in range(3):
            self.treeview[i].get_selection().set_mode(gtk.SELECTION_MULTIPLE)
            column = gtk.TreeViewColumn()
            rentext = gtk.CellRendererText()
            renicon = EmblemCellRenderer()
            column.pack_start(renicon, expand=0)
            column.pack_start(rentext, expand=1)
            column.set_attributes(renicon, pixbuf=self.model.column_index(tree.COL_ICON,i),
                                           emblem=self.model.column_index(COL_NEWER,i))
            column.set_attributes(rentext, markup=self.model.column_index(tree.COL_TEXT,i))
            self.treeview[i].append_column(column)
            self.scrolledwindow[i].get_vadjustment().connect("value-changed", self._sync_vscroll )
            self.scrolledwindow[i].get_hadjustment().connect("value-changed", self._sync_hscroll )
        self.linediffs = [[], []]
        self.type_filters_available = []
        for i in range(6):
            pattern = getattr(self.prefs, "filter_pattern_%i" % i)
            if pattern:
                f = pattern.split()
                label = f[0]
                active = int(f[1])
                regexps = [misc.shell_to_regex(p)[:-1] for p in f[2:]]
                try:
                    cregexps = [re.compile(r) for r in regexps]
                    def func(x, cr=cregexps):
                        for c in cr:
                            if c.match(x)!=None:
                                return 0
                        return 1
                except re.error, e:
                    misc.run_dialog( _("Error converting pattern '%s' to regular expression") % pattern, self )
                else:
                    self.type_filters_available.append( (f[0], active, func) )
        self.type_filters = []
        for i,f in misc.enumerate(self.type_filters_available):
            icon = gtk.Image()
            icon.set_from_stock(gtk.STOCK_FIND, gtk.ICON_SIZE_LARGE_TOOLBAR)
            icon.show()
            toggle = self.toolbar.append_element(gtk.TOOLBAR_CHILD_TOGGLEBUTTON, None, f[0],
                _("Hide %s") % f[0], "", icon, self._update_type_filter, i )
            toggle.set_active(f[1])
        self.state_filters = [
            tree.STATE_NORMAL,
            tree.STATE_MODIFIED,
            tree.STATE_NEW,
        ]

    def on_preference_changed(self, key, value):
        if key == "toolbar_style":
            self.toolbar.set_style( self.prefs.get_toolbar_style() )

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

    def _get_focused_pane(self):
        focus = [ t.is_focus() for t in self.treeview ]
        try:
            return focus.index(1)
        except ValueError:
            return None

    def file_deleted(self, path, pane):
        # is file still extant in other pane?
        iter = self.model.get_iter(path)
        files = self.model.value_paths(iter)
        is_present = [ os.path.exists( file ) for file in files ]
        if 1 in is_present:
            self._update_item_state(iter)
        else: # nope its gone
            self.model.remove(iter)

    def file_created(self, path, pane):
        iter = self.model.get_iter(path)
        while iter and self.model.get_path(iter) != (0,):
            self._update_item_state( iter )
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
        self._update_item_state(child)
        self.recompute_label()
        self.scheduler.remove_all_tasks()
        self.recursively_update( (0,) )

    def recursively_update( self, path ):
        """Recursively update from tree path 'path'.
        """
        iter = self.model.get_iter( path )
        child = self.model.iter_children( iter )
        while child:
            self.model.remove(child)
            child = self.model.iter_children( iter )
        self._update_item_state(iter)
        self.scheduler.add_task( self._search_recursively_iter( path ).next )

    def _search_recursively_iter(self, rootpath):
        yield _("[%s] Scanning") % self.label_text
        prefixlen = 1 + len( self.model.value_path( self.model.get_iter(rootpath), 0 ) )
        todo = [ rootpath ]
        while len(todo):
            todo.sort() # depth first
            path = todo.pop(0)
            iter = self.model.get_iter( path )
            roots = self.model.value_paths( iter )
            yield _("[%s] Scanning %s") % (self.label_text, roots[0][prefixlen:])
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
                        for f in self.type_filters:
                            e = filter(f[2], e)
                        e.sort()
                        alldirs  += filter(lambda x: os.path.isdir(  join(root, x) ), e)
                        allfiles += filter(lambda x: os.path.isfile( join(root, x) ), e)

            alldirs = _uniq(alldirs)
            allfiles = self._filter_on_state( roots, _uniq(allfiles) )

            # then directories and files
            if len(alldirs) + len(allfiles) != 0:
                def add_entry(entry):
                    child = self.model.add_entries( iter, [join(r,entry) for r in roots] )
                    differences[0] |= self._update_item_state(child)
                    return child
                map(lambda x: todo.append(self.model.get_path(add_entry(x))), alldirs)                
                map(add_entry, allfiles)

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
        yield _("[%s] Done") % self.label_text

    def launch_comparison(self, iter, pane, force=1):
        """Launch comparison at 'iter'. 
           If it is a file we launch a diff.
           If it is a folder we recursively open diffs for each non equal file.
        """
        paths = filter(os.path.exists, self.model.value_paths(iter))
        arefiles = map(os.path.isfile, paths)
        if 0 not in arefiles:
            if force or int(self.model.get_state(iter,pane)) >= tree.STATE_NEW:
                self.emit("create-diff", paths)
        else:
            aredirs = map(os.path.isdir, paths)
            if aredirs:
                child = self.model.iter_children(iter)
                while child:
                    state = int(self.model.get_state(child, pane))
                    self.launch_comparison(child, pane, force=0)
                    child = self.model.iter_next(child)
            else:
                print "Mixture of files and folders?", paths

    def launch_comparisons_on_selected(self):
        """Launch comparisons on all selected elements.
        """
        pane = self._get_focused_pane()
        if pane != None:
            selected = self._get_selected_paths(pane)
            get_iter = self.model.get_iter
            for s in selected:
                self.launch_comparison( get_iter(s), pane )

    def copy_selected(self, direction):
        assert direction in (-1,1)
        src_pane = self._get_focused_pane()
        if src_pane != None:
            dst_pane = src_pane + direction
            assert dst_pane >= 0 and dst_pane < self.num_panes
            paths = self._get_selected_paths(src_pane)
            paths.reverse()
            model = self.model
            for path in paths: #filter(lambda x: x.name!=None, sel):
                iter = model.get_iter(path)
                name = model.value_path(iter, src_pane)
                if name == None:
                    continue
                src = model.value_path(iter, src_pane)
                dst = model.value_path(iter, dst_pane)
                try:
                    if os.path.isfile(src):
                        dstdir = os.path.dirname( dst )
                        if not os.path.exists( dstdir ):
                            os.makedirs( dstdir )
                        shutil.copy( src, dstdir )
                        self.file_created( path, dst_pane)
                    elif os.path.isdir(src):
                        if os.path.exists(dst):
                            if misc.run_dialog( _("'%s' exists.\nOverwrite?") % os.path.basename(dst),
                                    parent = self,
                                    buttonstype = gtk.BUTTONS_OK_CANCEL) != gtk.RESPONSE_OK:
                                continue
                        misc.copytree(src, dst)
                        self.recursively_update( path )
                except OSError, e:
                    misc.run_dialog(_("Error copying '%s' to '%s'\n\n%s.") % (src, dst,e), self)

    def delete_selected(self):
        """Delete all selected files/folders recursively.
        """
        # reverse so paths dont get changed
        pane = self._get_focused_pane()
        if pane != None:
            paths = self._get_selected_paths(pane)
            paths.reverse()
            for path in paths:
                iter = self.model.get_iter(path)
                name = self.model.value_path(iter, pane)
                try:
                    if os.path.isfile(name):
                        os.remove(name)
                        self.file_deleted( path, pane) #xxx
                    elif os.path.isdir(name):
                        if misc.run_dialog(_("'%s' is a directory.\nRemove recusively?") % os.path.basename(name),
                                parent = self,
                                buttonstype=gtk.BUTTONS_OK_CANCEL) == gtk.RESPONSE_OK:
                            shutil.rmtree(name)
                            self.recursively_update( path )
                except OSError, e:
                    misc.run_dialog(_("Error removing %s\n\n%s.") % (name,e), parent = self)

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
        self._update_difmaps()

    def on_treeview_row_collapsed(self, view, me, path):
        self._do_to_others(view, self.treeview, "collapse_row", (path,) )
        self._update_difmaps()

    def on_treeview_focus_in_event(self, tree, event):
        pane = self.treeview.index(tree)
        if pane > 0:
            self.button_copy_left.set_sensitive(1)
        if pane+1 < self.num_panes:
            self.button_copy_right.set_sensitive(1)
        self.button_delete.set_sensitive(1)
    def on_treeview_focus_out_event(self, tree, event):
        self.button_copy_left.set_sensitive(0)
        self.button_copy_right.set_sensitive(0)
        self.button_delete.set_sensitive(0)
        #
        # Toolbar handlers
        #

    def on_button_diff_clicked(self, button):
        self.launch_comparisons_on_selected()

    def on_button_copy_left_clicked(self, button):
        self.copy_selected(-1)
    def on_button_copy_right_clicked(self, button):
        self.copy_selected(1)
    def on_button_delete_clicked(self, button):
        self.delete_selected()

    def _update_state_filter(self, state, idx):
        assert state in (tree.STATE_NEW, tree.STATE_MODIFIED, tree.STATE_NORMAL)
        try:
            self.state_filters.remove( state )
        except ValueError:
            pass
        if active:
            self.state_filters.append( state )
        self.refresh()
    def on_filter_state_normal_toggled(self, button):
        self._update_state_filter( tree.STATE_NORMAL, button.get_active() )
    def on_filter_state_new_toggled(self, button):
        self._update_state_filter( tree.STATE_NEW, button.get_active() )
    def on_filter_state_modified_toggled(self, button):
        self._update_state_filter( tree.STATE_MODIFIED, button.get_active() )

    def _update_type_filter(self, button, idx):
        for i in range(len(self.type_filters)):
            if self.type_filters[i] == self.type_filters_available[idx]:
                self.type_filters.pop(i)
                break
        if button.get_active():
            self.type_filters.append( self.type_filters_available[idx] )
        self.refresh()

    def on_filter_hide_current_clicked(self, button):
        pane = self._get_focused_pane()
        if pane != None:
            paths = self._get_selected_paths(pane)
            paths.reverse()
            for p in paths:
                self.model.remove( self.model.get_iter(p) )

        #
        # Selection
        #
    def _get_selected_paths(self, pane):
        assert pane != None
        selected_paths = []
        self.treeview[pane].get_selection().selected_foreach(lambda store, path, iter: selected_paths.append( path ) )
        return selected_paths

        #
        # Filtering
        #

    def _filter_on_state(self, roots, files):
        """Get state of 'files' for filtering purposes.
           Returns STATE_NORMAL, STATE_NEW or STATE_MODIFIED
       """
        assert len(roots) == self.model.ntree
        ret = []
        for file in files:
            curfiles = [ os.path.join( r, file ) for r in roots ]
            is_present = [ os.path.exists( f ) for f in curfiles ]
            all_present = 0 not in is_present
            if all_present:
                if _files_same( curfiles ):
                    state = tree.STATE_NORMAL
                else:
                    state = tree.STATE_MODIFIED
            else:
                state = tree.STATE_NEW
            if state in self.state_filters:
                ret.append( file )
        return ret

    def _update_item_state(self, iter):
        """Update the state of the item at 'iter'
        """
        files = self.model.value_paths(iter)
        def mtime(f):
            try:
                return os.stat(f).st_mtime
            except OSError:
                return 0
        mod_times = [ mtime( file ) for file in files[:self.num_panes] ]
        newest_index = mod_times.index( max(mod_times) )
        all_present = 0 not in mod_times
        if all_present:
            all_same = _files_same( files )
            all_present_same = all_same
        else:
            lof = []
            for j in range(len(mod_times)):
                if mod_times[j]:
                    lof.append( files[j] )
            all_same = 0
            all_present_same = _files_same( lof )
        filename = os.path.basename(file)
        different = 1
        for j in range(self.model.ntree):
            if mod_times[j]:
                isdir = os.path.isdir( files[j] )
                if all_same:
                    self.model.set_state(iter, j,  tree.STATE_NORMAL, isdir)
                    different = 0
                elif all_present_same:
                    self.model.set_state(iter, j,  tree.STATE_NEW, isdir)
                else:
                    self.model.set_state(iter, j,  tree.STATE_MODIFIED, isdir)
                self.model.set_value(iter,
                    self.model.column_index(COL_NEWER, j),
                    j == newest_index and pixbuf_newer or None)
            else:
                self.model.set_state(iter, j,  tree.STATE_MISSING)
        return different

    def update_diff_maps(self):
        return

    def on_treeview_button_press_event(self, treeview, event):
        # unselect others
        for t in filter(lambda x:x!=treeview, self.treeview[:self.num_panes]):
            t.get_selection().unselect_all()
        if event.button == 3:
            path, col, cellx, celly = treeview.get_path_at_pos( event.x, event.y )
            treeview.grab_focus()
            treeview.set_cursor( path, col, 0)
            self.popup_menu.popup_in_pane( self.treeview.index(treeview) )
            return 1

    def set_num_panes(self, n):
        if n != self.num_panes and n in (1,2,3):
            self.model = DirDiffTreeStore(n)
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
        if root:
            roots = self.model.value_paths(root)
            self.set_locations( roots )

    def recompute_label(self):
        root = self.model.get_iter_root()
        filenames = self.model.value_paths(root)
        shortnames = misc.shorten_names(*filenames)
        self.label_text = " : ".join(shortnames)
        self.label_changed()

    def _update_difmaps(self):
        self.diffmap[0].queue_draw()
        self.diffmap[1].queue_draw()

    def on_diffmap_expose_event(self, area, event):
        diffmapindex = self.diffmap.index(area)
        treeindex = (0, self.num_panes-1)[diffmapindex]
        treeview = self.treeview[treeindex]

        def traverse_states(root):
            todo = [root]
            model = self.model
            while len(todo):
                iter = todo.pop(0)
                #print model.value_path(iter, treeindex), model.get_state(iter, treeindex)
                yield model.get_state(iter, treeindex)
                path = model.get_path(iter)
                if treeview.row_expanded(path):
                    children = []
                    child = model.iter_children(iter)
                    while child:
                        children.append(child)
                        child = model.iter_next(child)
                    todo = children + todo
            yield None # end marker

        chunks = []
        laststate = None
        lastlines = 0
        numlines = -1
        for state in traverse_states( self.model.get_iter_root() ):
            if state != laststate:
                chunks.append( (lastlines, laststate) )
                laststate = state
                lastlines = 1
            else:
                lastlines += 1
            numlines += 1

        if not hasattr(area, "meldgc"):
            assert area.window
            gcd = area.window.new_gc()
            gcd.set_rgb_fg_color( gdk.color_parse(self.prefs.color_delete_bg) )
            gcc = area.window.new_gc()
            gcc.set_rgb_fg_color( gdk.color_parse(self.prefs.color_replace_bg) )
            gce = area.window.new_gc()
            gce.set_rgb_fg_color( gdk.color_parse("yellow") )
            gcb = area.window.new_gc()
            gcb.set_rgb_fg_color( gdk.color_parse("black") )
            area.meldgc = [None, None, gce, None, gcd, gcc, gcc, None, gcb]

        #TODO need gutter of scrollbar - how do we get that?
        size_of_arrow = 14
        hperline = float( area.get_allocation().height - 3*size_of_arrow) / numlines
        scaleit = lambda x,s=hperline,o=size_of_arrow: x*s+o
        x0 = 4
        x1 = area.get_allocation().width - 2*x0

        window = area.window
        window.clear()

        start = 0
        for c in chunks[1:]:
            end = start + c[0]
            s,e = [int(x) for x in (math.floor(scaleit(start)), math.ceil(scaleit(end))) ]
            gc = area.meldgc[ int(c[1]) ]
            if gc:
                window.draw_rectangle( gc, 1, x0, s, x1, e-s)
                window.draw_rectangle( area.meldgc[-1], 0, x0, s, x1, e-s)
            start = end

    def on_diffmap_button_press_event(self, area, event):
        #TODO need gutter of scrollbar - how do we get that?
        if event.button == 1:
            size_of_arrow = 14
            diffmapindex = self.diffmap.index(area)
            index = (0, self.num_panes-1)[diffmapindex]
            height = area.get_allocation().height
            fraction = (event.y - size_of_arrow) / (height - 3.75*size_of_arrow)
            adj = self.scrolledwindow[index].get_vadjustment()
            val = fraction * adj.upper - adj.page_size/2
            upper = adj.upper - adj.page_size
            adj.set_value( max( min(upper, val), 0) )
            return 1

    def on_file_changed(self, filename):
        model = self.model
        iter = model.get_iter_root()
        for pane,path in misc.enumerate( model.value_paths(iter) ):
            if filename.startswith(path): 
                while iter:
                    child = model.iter_children( iter )
                    while child:
                        path = model.value_path(child, pane)
                        if filename == path:
                            self._update_item_state(child)
                            return
                        elif filename.startswith(path):
                            break
                        else:
                            child = self.model.iter_next( child )
                    iter = child
                return

gobject.type_register(DirDiff)
