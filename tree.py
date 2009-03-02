### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>

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

import os
import gtk
import misc
import gnomeglade
import paths

COL_PATH, COL_STATE, COL_TEXT, COL_ICON, COL_END = range(5)

from vc._vc import STATE_IGNORED, STATE_NONE, STATE_NORMAL, STATE_NOCHANGE, \
    STATE_ERROR, STATE_EMPTY, STATE_NEW, \
    STATE_MODIFIED, STATE_CONFLICT, STATE_REMOVED, \
    STATE_MISSING, STATE_MAX

load = lambda x,s=14: gnomeglade.load_pixbuf( paths.share_dir("glade2/pixmaps",x), s)
pixbuf_folder = load("tree-folder-normal.png", 20)
pixbuf_folder_new = load("tree-folder-new.png", 20)
pixbuf_folder_changed = load("tree-folder-changed.png", 20)
pixbuf_file = load("tree-file-normal.png")
pixbuf_file_new = load("tree-file-new.png")
pixbuf_file_changed = load("tree-file-changed.png")

class DiffTreeStore(gtk.TreeStore):
    def __init__(self, ntree = 3, num_col = COL_END):
        types = [type("")] * num_col * ntree
        types[COL_ICON*ntree:COL_ICON*ntree+ntree] = [type(pixbuf_file)] * ntree
        gtk.TreeStore.__init__(self, *types)
        self.ntree = ntree
        self._setup_default_styles()

    def _setup_default_styles(self):
        self.textstyle = [
            '<span foreground="#888888">%s</span>', # STATE_IGNORED
            '<span foreground="#888888">%s</span>', # STATE_NONE
            '<span foreground="black">%s</span>', # STATE_NORMAL
            '<span foreground="black" style="italic">%s</span>', # STATE_NOCHANGE
            '<span foreground="#ff0000" background="yellow" weight="bold">%s</span>', # STATE_ERROR
            '<span foreground="#999999" style="italic">%s</span>', # STATE_EMPTY
            '<span foreground="#008800" weight="bold">%s</span>', # STATE_NEW
            '<span foreground="#880000" weight="bold">%s</span>', # STATE_MODIFIED
            '<span foreground="#ff0000" background="#ffeeee" weight="bold">%s</span>', # STATE_CONFLICT
            '<span foreground="#880000" strikethrough="true" weight="bold">%s</span>', # STATE_REMOVED
            '<span foreground="#888888" strikethrough="true">%s</span>' # STATE_MISSING
        ]
        assert len(self.textstyle) == STATE_MAX
        self.pixstyle = [
            (pixbuf_file, pixbuf_folder), # IGNORED
            (pixbuf_file, pixbuf_folder), # NONE
            (pixbuf_file, pixbuf_folder), # NORMAL
            (pixbuf_file, pixbuf_folder), # NOCHANGE
            (None, None), # ERROR
            (None, None), # EMPTY
            (pixbuf_file_new, pixbuf_folder_new), # NEW
            (pixbuf_file_changed, pixbuf_folder_changed), # MODIFIED
            (pixbuf_file_changed, pixbuf_folder_changed), # CONFLICT
            (pixbuf_file_changed, pixbuf_folder_changed), # REMOVED
            (None, None) # MISSING
        ]
        assert len(self.pixstyle) == STATE_MAX

    def add_entries(self, parent, names):
        child = self.append(parent)
        for i,f in enumerate(names):
            self.set_value( child, self.column_index(COL_PATH,i), f)
        return child

    def add_empty(self, parent, text="empty folder"):
        child = self.append(parent)
        for i in range(self.ntree):
            self.set_value(child, self.column_index(COL_STATE,i), STATE_EMPTY)
            self.set_value(child, self.column_index(COL_PATH,i), self.pixstyle[STATE_EMPTY])
            self.set_value(child, self.column_index(COL_TEXT,i), self.textstyle[STATE_EMPTY] % misc.escape(text) )
        return child

    def add_error(self, parent, msg, pane):
        err = self.append(parent)
        for i in range(self.ntree):
            self.set_value(err, self.column_index(COL_STATE,i), STATE_ERROR)
        self.set_value(err, self.column_index(COL_ICON, pane), self.pixstyle[STATE_ERROR][0] )
        self.set_value(err, self.column_index(COL_TEXT, pane), self.textstyle[STATE_ERROR] % misc.escape(msg) )

    def value_paths(self, iter):
        return [ self.value_path(iter, i) for i in range(self.ntree) ]
    def value_path(self, iter, pane):
        return self.get_value(iter, self.column_index(COL_PATH, pane) )
    def column_index(self, col, pane):
        return self.ntree * col + pane

    def set_state(self, iter, pane, state, isdir=0):
        fullname = self.get_value(iter, self.column_index(COL_PATH,pane))
        name = misc.escape( os.path.basename(fullname) )
        STATE = self.column_index(COL_STATE, pane)
        TEXT  = self.column_index(COL_TEXT,  pane)
        ICON  = self.column_index(COL_ICON,  pane)
        self.set_value(iter, STATE, state)
        self.set_value(iter, TEXT,  self.textstyle[state] % name)
        self.set_value(iter, ICON,  self.pixstyle[state][isdir])

    def get_state(self, iter, pane):
        STATE = self.column_index(COL_STATE, pane)
        return self.get_value(iter, STATE)

    def inorder_search_down(self, it):
        while it:
            child = self.iter_children(it)
            if child:
                it = child
            else:
                next = self.iter_next(it)
                if next:
                    it = next
                else:
                    while 1:
                        it = self.iter_parent(it)
                        if it:
                            next = self.iter_next(it)
                            if next:
                                it = next
                                break
                        else:
                            raise StopIteration()
            yield it

    def inorder_search_up(self, it):
        while it:
            path = self.get_path(it)
            if path[-1]:
                path = path[:-1] + (path[-1]-1,)
                it = self.get_iter(path)
                while 1:
                    nc = self.iter_n_children(it)
                    if nc:
                        it = self.iter_nth_child(it, nc-1)
                    else:
                        break
            else:
                up = self.iter_parent(it)
                if up:
                    it = up
                else:
                    raise StopIteration()
            yield it

