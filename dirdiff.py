### Copyright (C) 2002-2003 Stephen Kennedy <stevek@gnome.org>

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

import paths
import diffutil
import errno
import gnomeglade
import gobject
import gtk
import gtk.keysyms
import math
import misc
import os
import shutil
import melddoc
import tree
import filecmp
import re
import stat
import time

gdk = gtk.gdk

################################################################################
#
# Local Functions
#
################################################################################

def uniq(l):
    i = iter(l)
    a = i.next()
    yield a
    while 1:
        b = i.next()
        if a != b:
            yield b
            a = b

_cache = {}

def _files_same(lof, regexes):
    """Return 1 if all the files in 'lof' have the same contents.
       If the files are the same after the regular expression substitution, return 2.
       Finally, return 0 if the files still differ.
    """
    # early out if only one file
    if len(lof) <= 1:
        return 1
    # get sigs
    lof = tuple(lof)
    def sig(f):
        s = os.stat(f)
        return misc.struct(mode=stat.S_IFMT(s.st_mode), size=s.st_size, time=s.st_mtime)
    def all_same(l):
        for i in l[1:]:
            if l[0] != i:
                return 0
        return 1
    sigs = tuple( [ sig(f) for f in lof ] )
    # check for directories
    arefiles = [ stat.S_ISREG(s.mode) for s in sigs ]
    if arefiles.count(0) == len(arefiles): # all dirs
        return 1
    elif arefiles.count(0): # mixture
        return 0
    # if no substitutions look for different sizes
    if len(regexes) == 0 and all_same( [s.size for s in sigs] ) == 0:
        return 0
    # try cache
    try:
        cache = _cache[ lof ]
    except KeyError:
        pass
    else:
        if cache.sigs == sigs: # up to date
            return cache.result
    # do it
    contents = [ open(f, "r").read() for f in lof ]
    if all_same(contents):
        result = 1
    else:
        for r in regexes:
            contents = [ re.sub(r, "", c) for c in contents ]
        result = all_same(contents) and 2
    _cache[ lof ] = misc.struct(sigs=sigs, result=result)
    return result

def _not_none(l):
    """Return list with Nones filtered out"""
    return filter(lambda x: x!=None, l)

join = os.path.join

COL_EMBLEM = tree.COL_END + 1
pixbuf_newer = gnomeglade.load_pixbuf( paths.share_dir("glade2/pixmaps/tree-file-newer.png"), 14)
TYPE_PIXBUF = type(pixbuf_newer)

################################################################################
#
# DirDiffTreeStore
#
################################################################################
class DirDiffTreeStore(tree.DiffTreeStore):
    def __init__(self, ntree):
        types = [type("")] * COL_EMBLEM * ntree
        types[tree.COL_ICON*ntree:tree.COL_ICON*ntree+ntree] = [TYPE_PIXBUF] * ntree
        types[COL_EMBLEM*ntree:COL_EMBLEM*ntree+ntree] = [TYPE_PIXBUF] * ntree
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
        gladefile = paths.share_dir("glade2/dirdiff.glade")
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
    def on_popup_edit_activate(self, menuitem):
        self.parent.on_button_edit_clicked( None )

################################################################################
#
# TypeFilter
#
################################################################################

class TypeFilter(object):
    __slots__ = ("label", "filter", "active")
    def __init__(self, label, active, filter):
        self.label = label
        self.active = active
        self.filter = filter

################################################################################
#
# DirDiff
#
################################################################################

class DirDiff(melddoc.MeldDoc, gnomeglade.Component):
    """Two or three way diff of directories"""

    def __init__(self, prefs, num_panes):
        melddoc.MeldDoc.__init__(self, prefs)
        gnomeglade.Component.__init__(self, paths.share_dir("glade2/dirdiff.glade"), "dirdiff")
        self.toolbar.set_style( self.prefs.get_toolbar_style() )
        self._map_widgets_into_lists( ["treeview", "fileentry", "diffmap", "scrolledwindow", "linkmap"] )
        self.popup_menu = DirDiffMenu(self)
        self.set_num_panes(num_panes)
        self.on_treeview_focus_out_event(None, None)
        self.treeview_focussed = None

        for i in range(3):
            self.treeview[i].get_selection().set_mode(gtk.SELECTION_MULTIPLE)
            column = gtk.TreeViewColumn()
            rentext = gtk.CellRendererText()
            renicon = EmblemCellRenderer()
            column.pack_start(renicon, expand=0)
            column.pack_start(rentext, expand=1)
            column.set_attributes(renicon, pixbuf=self.model.column_index(tree.COL_ICON,i),
                                           emblem=self.model.column_index(COL_EMBLEM,i))
            column.set_attributes(rentext, markup=self.model.column_index(tree.COL_TEXT,i))
            self.treeview[i].append_column(column)
            self.scrolledwindow[i].get_vadjustment().connect("value-changed", self._sync_vscroll )
            self.scrolledwindow[i].get_hadjustment().connect("value-changed", self._sync_hscroll )
        self.linediffs = [[], []]
        self.state_filters = [
            tree.STATE_NORMAL,
            tree.STATE_MODIFIED,
            tree.STATE_NEW,
        ]
        self.create_name_filters()
        self.update_regexes()

    def update_regexes(self):
        self.regexes = []
        for r in [ misc.ListItem(i) for i in self.prefs.regexes.split("\n") ]:
            if r.active:
                try:
                    self.regexes.append( re.compile(r.value+"(?m)") )
                except re.error, e:
                    misc.run_dialog(
                        text=_("Error converting pattern '%s' to regular expression") % r.value )

    def create_name_filters(self):
        self.name_filters_available = []
        for f in [misc.ListItem(s) for s in self.prefs.filters.split("\n") ]:
            bits = f.value.split()
            if len(bits) > 1:
                regex = "(%s)$" % ")|(".join( [misc.shell_to_regex(b)[:-1] for b in bits] )
            elif len(bits):
                regex = misc.shell_to_regex(bits[0])
            else: # an empty pattern would match anything, skip it
                continue
            try:
                cregex = re.compile(regex)
            except re.error, e:
                misc.run_dialog( _("Error converting pattern '%s' to regular expression") % pattern, self )
            else:
                func = lambda x, r=cregex : r.match(x) == None
                self.name_filters_available.append( TypeFilter(f.name, f.active, func) )
        self.name_filters = []
        for i,f in misc.enumerate(self.name_filters_available):
            icon = gtk.Image()
            icon.set_from_stock(gtk.STOCK_FIND, gtk.ICON_SIZE_LARGE_TOOLBAR)
            icon.show()
            toggle = self.toolbar.append_element(gtk.TOOLBAR_CHILD_TOGGLEBUTTON, None, f.label,
                _("Hide %s") % f.label, "", icon, self._update_name_filter, i )
            toggle.set_active(f.active)

    def on_preference_changed(self, key, value):
        if key == "toolbar_style":
            self.toolbar.set_style( self.prefs.get_toolbar_style() )
        elif key == "regexes":
            self.update_regexes()

    def _do_to_others(self, master, objects, methodname, args):
        if not hasattr(self, "do_to_others_lock"):
            self.do_to_others_lock = 1
            try:
                for o in filter(lambda x:x!=master, objects[:self.num_panes]):
                    method = getattr(o,methodname)
                    method(*args)
            finally:
                delattr(self, "do_to_others_lock")

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
        self._update_diffmaps()

    def file_created(self, path, pane):
        iter = self.model.get_iter(path)
        while iter and self.model.get_path(iter) != (0,):
            self._update_item_state( iter )
            iter = self.model.iter_parent(iter)
        self._update_diffmaps()

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
        symlinks_followed = {} # only follow symlinks once
        todo = [ rootpath ]
        while len(todo):
            todo.sort() # depth first
            path = todo.pop(0)
            iter = self.model.get_iter( path )
            roots = self.model.value_paths( iter )
            yield _("[%s] Scanning %s") % (self.label_text, roots[0][prefixlen:])
            differences = [0]
            if not self.button_ignore_case.get_active():
                class accum(object):
                    def __init__(self, parent, roots):
                        self.items = []
                        self.n = parent.num_panes
                    def add(self, pane, items):
                        self.items.extend(items)
                    def get(self):
                        self.items.sort()
                        def repeat(s, n):
                            for i in xrange(n):
                                yield s
                        return [ tuple(repeat(i,self.n)) for i in  uniq(self.items) ]
            else:
                canonicalize = lambda x : x.lower()
                class accum(object):
                    def __init__(self, parent, roots):
                        self.items = {} # map canonical names to realnames
                        self.bad = []
                        self.parent = parent
                        self.roots = roots
                        self.default = [None] * self.parent.num_panes
                    def add(self, pane, items):
                        for i in items:
                            ci = canonicalize(i)
                            try:
                                assert self.items[ ci ][pane] == None
                            except KeyError:
                                self.items[ ci ] = self.default[:]
                                self.items[ ci ][pane] = i
                            except AssertionError:
                                self.bad.append( _("'%s' hidden by '%s'") %
                                    ( os.path.join(self.roots[pane], i), self.items[ ci ][pane]) )
                            else:
                                self.items[ ci ][pane] = i
                    def get(self):
                        if len(self.bad):
                            misc.run_dialog(_("You are running a case insensitive comparison on"
                                " a case sensitive filesystem. Some files are not visible:\n%s")
                                % "\n".join( self.bad ), self.parent )
                        keys = self.items.keys()
                        keys.sort()
                        def fixup(key, tuples):
                            return tuple([ t or key for t in tuples ])
                        return [ fixup(k, self.items[k]) for k in keys ]
            accumdirs = accum(self, roots)
            accumfiles = accum(self, roots)
            for pane, root in misc.enumerate(roots):
                if os.path.isdir( root ):
                    try:
                        entries = os.listdir( root )
                    except OSError, err:
                        self.model.add_error( iter, err.strerror, pane )
                        differences = [1]
                    else:
                        for f in self.name_filters:
                            entries = filter(f.filter, entries)
                        for e in entries:
                            s = os.lstat( join(root,e) )
                            files = []
                            dirs = []
                            if stat.S_ISREG(s.st_mode):
                                files.append(e)
                            elif stat.S_ISDIR(s.st_mode):
                                dirs.append(e)
                            elif stat.S_ISLNK(s.st_mode):
                                key = (s.st_dev, s.st_ino)
                                if symlinks_followed.get( key, 0 ) == 0:
                                    symlinks_followed[key] = 1
                                    try:
                                        s = os.stat( join(root,e) )
                                    except OSError, err:
                                        print "ignoring dangling symlink", e
                                        pass
                                    else:
                                        if stat.S_ISREG(s.st_mode):
                                            files.append(e)
                                        elif stat.S_ISDIR(s.st_mode):
                                            dirs.append(e)
                            accumfiles.add( pane, files )
                            accumdirs.add( pane, dirs )

            alldirs = accumdirs.get()
            allfiles = self._filter_on_state( roots, accumfiles.get() )

            # then directories and files
            if len(alldirs) + len(allfiles) != 0:
                def add_entry(names):
                    child = self.model.add_entries( iter, [join(r,n) for r,n in zip(roots, names) ] )
                    differences[0] |= self._update_item_state(child)
                    return child
                map(lambda x : todo.append( self.model.get_path(add_entry(x))), alldirs )
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
        self.emit("create-diff", paths)

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
                except (OSError,IOError), e:
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
                        self.file_deleted( path, pane)
                    elif os.path.isdir(name):
                        if misc.run_dialog(_("'%s' is a directory.\nRemove recusively?") % os.path.basename(name),
                                parent = self,
                                buttonstype=gtk.BUTTONS_OK_CANCEL) == gtk.RESPONSE_OK:
                            shutil.rmtree(name)
                            self.recursively_update( path )
                        self.file_deleted( path, pane)
                except OSError, e:
                    misc.run_dialog(_("Error removing %s\n\n%s.") % (name,e), parent = self)

    def on_treeview_cursor_changed(self, *args):
        pane = self._get_focused_pane()
        if pane == None: return
        paths = self._get_selected_paths(pane)
        if len(paths) > 0:
            def rwx(mode):
                return "".join( [ ((mode& (1<<i)) and "xwr"[i%3] or "-") for i in range(8,-1,-1) ] )
            def nice(deltat):
                # singular,plural 
                times = _("second,seconds:minute,minutes:hour,hours:day,days:week,weeks:month,months:year,years").split(":")
                d = abs(int(deltat))
                for div, time in zip((60,60,24,7,4,12,100), times):
                    if d < div * 5:
                        return "%s%i %s" % (deltat<0 and "-" or "", d, time.split(",")[d != 1])
                    d /= div
            file = self.model.value_path( self.model.get_iter(paths[0]), pane )
            try:
                stat = os.stat(file)
            except OSError:
                self.emit("status-changed", "" )
            else:
                self.emit("status-changed", "%s : %s" % (rwx(stat.st_mode), nice(time.time() - stat.st_mtime) ) )

    def on_switch_event(self):
        if self.treeview_focussed:
            self.scheduler.add_task( self.treeview_focussed.grab_focus )
            self.scheduler.add_task( self.on_treeview_cursor_changed )

    def on_treeview_key_press_event(self, view, event):
        pane = self.treeview.index(view)
        tree = None
        if gtk.keysyms.Right == event.keyval:
            if pane+1 < self.num_panes:
                tree = self.treeview[pane+1]
        elif gtk.keysyms.Left == event.keyval:
            if pane-1 >= 0:
                tree = self.treeview[pane-1]
        if tree != None:
            paths = self._get_selected_paths(pane)
            view.get_selection().unselect_all()
            tree.grab_focus()
            tree.get_selection().unselect_all()
            if len(paths):
                tree.set_cursor(paths[0])
                for p in paths:
                    tree.get_selection().select_path(p)
            tree.emit("cursor-changed")
        return event.keyval in (gtk.keysyms.Left, gtk.keysyms.Right) #handled

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
        self._update_diffmaps()

    def on_treeview_row_collapsed(self, view, me, path):
        self._do_to_others(view, self.treeview, "collapse_row", (path,) )
        self._update_diffmaps()

    def on_treeview_focus_in_event(self, tree, event):
        self.treeview_focussed = tree
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
    def on_button_edit_clicked(self, button):
        pane = self._get_focused_pane()
        if pane != None:
            m = self.model
            files = [ m.value_path( m.get_iter(p), pane ) for p in self._get_selected_paths(pane) ]
            self._edit_files( [f for f in files if os.path.isfile(f)] )

    def on_button_ignore_case_toggled(self, button):
        self.refresh()

    def _update_state_filter(self, state, active):
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

    def _update_name_filter(self, button, idx):
        for i in range(len(self.name_filters)):
            if self.name_filters[i] == self.name_filters_available[idx]:
                self.name_filters.pop(i)
                break
        if button.get_active():
            self.name_filters.append( self.name_filters_available[idx] )
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
        self.treeview[pane].get_selection().selected_foreach(
            lambda store, path, iter: selected_paths.append( path ) )
        return selected_paths

        #
        # Filtering
        #

    def _filter_on_state(self, roots, fileslist):
        """Get state of 'files' for filtering purposes.
           Returns STATE_NORMAL, STATE_NEW or STATE_MODIFIED

               roots - array of root directories
               fileslist - array of filename tuples of length len(roots)
        """
        assert len(roots) == self.model.ntree
        ret = []
        for files in fileslist:
            curfiles = [ os.path.join( r, f ) for r,f in zip(roots,files) ]
            is_present = [ os.path.exists( f ) for f in curfiles ]
            all_present = 0 not in is_present
            if all_present:
                if _files_same( curfiles, self.regexes ):
                    state = tree.STATE_NORMAL
                else:
                    state = tree.STATE_MODIFIED
            else:
                state = tree.STATE_NEW
            if state in self.state_filters:
                ret.append( files )
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
        # find the newest file, checking also that they differ
        mod_times = [ mtime( file ) for file in files[:self.num_panes] ]
        newest_index = mod_times.index( max(mod_times) )
        if mod_times.count( max(mod_times) ) == len(mod_times):
            newest_index = -1 # all same
        all_present = 0 not in mod_times
        if all_present:
            all_same = _files_same( files, self.regexes )
            all_present_same = all_same
        else:
            lof = []
            for j in range(len(mod_times)):
                if mod_times[j]:
                    lof.append( files[j] )
            all_same = 0
            all_present_same = _files_same( lof, self.regexes )
        different = 1
        for j in range(self.model.ntree):
            if mod_times[j]:
                isdir = os.path.isdir( files[j] )
                if all_same == 1:
                    self.model.set_state(iter, j,  tree.STATE_NORMAL, isdir)
                    different = 0
                elif all_same == 2:
                    self.model.set_state(iter, j,  tree.STATE_NOCHANGE, isdir)
                    different = 0
                elif all_present_same:
                    self.model.set_state(iter, j,  tree.STATE_NEW, isdir)
                else:
                    self.model.set_state(iter, j,  tree.STATE_MODIFIED, isdir)
                self.model.set_value(iter,
                    self.model.column_index(COL_EMBLEM, j),
                    j == newest_index and pixbuf_newer or None)
            else:
                self.model.set_state(iter, j,  tree.STATE_MISSING)
        return different

    def on_treeview_button_press_event(self, treeview, event):
        # unselect other panes
        for t in filter(lambda x:x!=treeview, self.treeview[:self.num_panes]):
            t.get_selection().unselect_all()
        if event.button == 3:
            try:
                path, col, cellx, celly = treeview.get_path_at_pos( int(event.x), int(event.y) )
            except TypeError:
                pass # clicked outside tree
            else:
                treeview.grab_focus()
                selected = self._get_selected_paths( self.treeview.index(treeview) )
                if len(selected) <= 1 and event.state == 0:
                    treeview.set_cursor( path, col, 0)
                self.popup_menu.popup_in_pane( self.treeview.index(treeview) )
            return event.state==0

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

    def _update_diffmaps(self):
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
            gcm = area.window.new_gc()
            gcm.set_rgb_fg_color( gdk.color_parse("white") )
            gcb = area.window.new_gc()
            gcb.set_rgb_fg_color( gdk.color_parse("black") )
            area.meldgc = [None, # ignore
                           None, # none
                           None, # normal
                           None, # nochange
                           gce,  # error
                           None, # empty
                           gcd,  # new
                           gcc,  # modified
                           gcc,  # conflict
                           gcc,  # removed
                           gcm,  # missing
                           gcb ] # border
            assert len(area.meldgc) - 1 == tree.STATE_MAX

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

    def on_file_changed(self, changed_filename):
        """When a file has changed, try to find it in our tree
           and update its status if necessary
        """
        model = self.model
        changed_paths = []
        # search each panes tree for changed_filename
        for pane in range(self.num_panes):
            it = model.get_iter_root()
            current = model.value_path(it, pane).split(os.sep)
            changed = changed_filename.split(os.sep)
            # early exit. does filename begin with root?
            try:
                if changed[:len(current)] != current:
                    continue
            except IndexError:
                continue
            changed = changed[len(current):]
            # search the tree component at a time
            for component in changed:
                child = model.iter_children( it )
                while child:
                    leading, name = os.path.split( model.value_path(child, pane) )
                    if component == name : # found it
                        it = child
                        break
                    else:
                        child = self.model.iter_next( child ) # next
                if not it:
                    break
            # save if found and unique
            if it:
                path = model.get_path(it)
                if path not in changed_paths:
                    changed_paths.append(path)
        # do the update
        for path in changed_paths:
            self._update_item_state( model.get_iter(path) )

    def next_diff(self, direction):
        if self.treeview_focussed:
            pane = self.treeview.index( self.treeview_focussed )
        else:
            pane = 0
        start_iter = self.model.get_iter( (self._get_selected_paths(pane) or [(0,)])[-1] )

        def inorder_search_down(model, it):
            while it:
                child = model.iter_children(it)
                if child:
                    it = child
                else:
                    next = model.iter_next(it)
                    if next:
                        it = next
                    else:
                        while 1:
                            it = model.iter_parent(it)
                            if it:
                                next = model.iter_next(it)
                                if next:
                                    it = next
                                    break
                            else:
                                raise StopIteration()
                yield it

        def inorder_search_up(model, it):
            while it:
                path = model.get_path(it)
                if path[-1]:
                    path = path[:-1] + (path[-1]-1,)
                    it = model.get_iter(path)
                    while 1:
                        nc = model.iter_n_children(it)
                        if nc:
                            it = model.iter_nth_child(it, nc-1)
                        else:
                            break
                else:
                    up = model.iter_parent(it)
                    if up:
                        it = up
                    else:
                        raise StopIteration()
                yield it

        def goto_iter(it):
            curpath = self.model.get_path(it)
            for i in range(len(curpath)-1):
                self.treeview[pane].expand_row( curpath[:i+1], 0)
            self.treeview[pane].set_cursor(curpath)

        search = {gdk.SCROLL_UP:inorder_search_up}.get(direction, inorder_search_down)
        for it in search( self.model, start_iter ):
            state = int(self.model.get_state( it, pane ))
            if state != tree.STATE_NORMAL:
                goto_iter(it)
                return

gobject.type_register(DirDiff)
