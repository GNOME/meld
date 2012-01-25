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
import gobject
import gtk

COL_PATH, COL_STATE, COL_TEXT, COL_ICON, COL_TINT, COL_END = range(6)

from meld.vc._vc import \
    STATE_IGNORED, STATE_NONE, STATE_NORMAL, STATE_NOCHANGE, \
    STATE_ERROR, STATE_EMPTY, STATE_NEW, \
    STATE_MODIFIED, STATE_CONFLICT, STATE_REMOVED, \
    STATE_MISSING, STATE_MAX


class DiffTreeStore(gtk.TreeStore):

    def __init__(self, ntree, types):
        gtk.TreeStore.__init__(self, *types)
        self.ntree = ntree
        self._setup_default_styles()

    def _setup_default_styles(self):
        self.textstyle = [
            '<span foreground="#888888">%s</span>', # STATE_IGNORED
            '<span foreground="#888888">%s</span>', # STATE_NONE
            '%s', # STATE_NORMAL
            '<span style="italic">%s</span>', # STATE_NOCHANGE
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
            ("text-x-generic", "folder"), # IGNORED
            ("text-x-generic", "folder"), # NONE
            ("text-x-generic", "folder"), # NORMAL
            ("text-x-generic", "folder"), # NOCHANGE
            (None,             None),     # ERROR
            (None,             None),     # EMPTY
            ("text-x-generic", "folder"), # NEW
            ("text-x-generic", "folder"), # MODIFIED
            ("text-x-generic", "folder"), # CONFLICT
            ("text-x-generic", "folder"), # REMOVED
            ("text-x-generic", "folder"), # MISSING
        ]

        self.icon_tints = [
            (None,      None),      # IGNORED
            (None,      None),      # NONE
            (None,      None),      # NORMAL
            (None,      None),      # NOCHANGE
            (None,      None),      # ERROR
            (None,      None),      # EMPTY
            ("#00ff00", None),      # NEW
            ("#ff0000", None),      # MODIFIED
            ("#ff0000", None),      # CONFLICT
            ("#ff0000", None),      # REMOVED
            ("#ffffff", "#ffffff"), # MISSING
        ]

        assert len(self.pixstyle) == len(self.icon_tints) == STATE_MAX

    def add_entries(self, parent, names):
        child = self.append(parent)
        for i,f in enumerate(names):
            self.set_value( child, self.column_index(COL_PATH,i), f)
        return child

    def add_empty(self, parent, text="empty folder"):
        child = self.append(parent)
        for i in range(self.ntree):
            self.set_value(child, self.column_index(COL_PATH, i), None)
            self.set_value(child, self.column_index(COL_STATE, i), str(STATE_EMPTY))
            self.set_value(child, self.column_index(COL_ICON, i), self.pixstyle[STATE_EMPTY][0])
            self.set_value(child, self.column_index(COL_TEXT, i), self.textstyle[STATE_EMPTY] % gobject.markup_escape_text(text))
        return child

    def add_error(self, parent, msg, pane):
        err = self.append(parent)
        for i in range(self.ntree):
            self.set_value(err, self.column_index(COL_STATE, i), str(STATE_ERROR))
        self.set_value(err, self.column_index(COL_ICON, pane), self.pixstyle[STATE_ERROR][0] )
        self.set_value(err, self.column_index(COL_TINT, pane),
                       self.icon_tints[STATE_ERROR][0])
        self.set_value(err, self.column_index(COL_TEXT, pane), self.textstyle[STATE_ERROR] % gobject.markup_escape_text(msg))

    def value_paths(self, it):
        return [self.value_path(it, i) for i in range(self.ntree)]
    def value_path(self, it, pane):
        return self.get_value(it, self.column_index(COL_PATH, pane))
    def column_index(self, col, pane):
        return self.ntree * col + pane

    def set_state(self, it, pane, state, isdir=0):
        fullname = self.get_value(it, self.column_index(COL_PATH,pane))
        name = gobject.markup_escape_text(os.path.basename(fullname))
        STATE = self.column_index(COL_STATE, pane)
        TEXT  = self.column_index(COL_TEXT,  pane)
        ICON  = self.column_index(COL_ICON,  pane)
        TINT  = self.column_index(COL_TINT,  pane)
        self.set_value(it, STATE, str(state))
        self.set_value(it, TEXT,  self.textstyle[state] % name)
        self.set_value(it, ICON,  self.pixstyle[state][isdir])
        self.set_value(it, TINT,  self.icon_tints[state][isdir])

    def get_state(self, it, pane):
        STATE = self.column_index(COL_STATE, pane)
        return int(self.get_value(it, STATE))

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

    def _find_next_prev_diff(self, start_path):
        prev_path, next_path = None, None
        start_iter = self.get_iter(start_path)

        for it in self.inorder_search_up(start_iter):
            state = self.get_state(it, 0)
            if state not in (STATE_NORMAL, STATE_EMPTY):
                prev_path = self.get_path(it)
                break

        for it in self.inorder_search_down(start_iter):
            state = self.get_state(it, 0)
            if state not in (STATE_NORMAL, STATE_EMPTY):
                next_path = self.get_path(it)
                break

        return prev_path, next_path
