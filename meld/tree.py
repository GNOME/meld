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
import pango

COL_PATH, COL_STATE, COL_TEXT, COL_ICON, COL_TINT, COL_FG, COL_STYLE, \
    COL_WEIGHT, COL_STRIKE, COL_END = range(10)

COL_TYPES = (str, str, str, str, str, gtk.gdk.Color, pango.Style,
             pango.Weight, bool)


from meld.vc._vc import \
    STATE_IGNORED, STATE_NONE, STATE_NORMAL, STATE_NOCHANGE, \
    STATE_ERROR, STATE_EMPTY, STATE_NEW, \
    STATE_MODIFIED, STATE_CONFLICT, STATE_REMOVED, \
    STATE_MISSING, STATE_MAX


class DiffTreeStore(gtk.TreeStore):

    def __init__(self, ntree, types):
        full_types = []
        for col_type in (COL_TYPES + tuple(types)):
            full_types.extend([col_type] * ntree)
        gtk.TreeStore.__init__(self, *full_types)
        self.ntree = ntree
        self._setup_default_styles()

    def on_style_set(self, widget, prev_style):
        style = widget.get_style()
        self._setup_default_styles(style)

    def _setup_default_styles(self, style=None):
        roman, italic = pango.STYLE_NORMAL, pango.STYLE_ITALIC
        normal, bold = pango.WEIGHT_NORMAL, pango.WEIGHT_BOLD

        if style:
            lookup = lambda color_id, default: style.lookup_color(color_id)
        else:
            lookup = lambda color_id, default: gtk.gdk.color_parse(default)

        unk_fg = lookup("unknown-text", "#888888")
        new_fg = lookup("insert-text", "#008800")
        mod_fg = lookup("replace-text", "#0044dd")
        del_fg = lookup("delete-text", "#880000")
        err_fg = lookup("error-text", "#ffff00")
        con_fg = lookup("conflict-text", "#ff0000")

        self.text_attributes = [
            # foreground, style, weight, strikethrough
            (unk_fg, roman,  normal, None),  # STATE_IGNORED
            (unk_fg, roman,  normal, None),  # STATE_NONE
            (None,   roman,  normal, None),  # STATE_NORMAL
            (None,   italic, normal, None),  # STATE_NOCHANGE
            (err_fg, roman,  bold,   None),  # STATE_ERROR
            (unk_fg, italic, normal, None),  # STATE_EMPTY
            (new_fg, roman,  bold,   None),  # STATE_NEW
            (mod_fg, roman,  bold,   None),  # STATE_MODIFIED
            (con_fg, roman,  bold,   None),  # STATE_CONFLICT
            (del_fg, roman,  bold,   True),  # STATE_REMOVED
            (unk_fg, roman,  normal, True),  # STATE_MISSING
        ]

        self.icon_details = [
            # file-icon, folder-icon, file-tint, folder-tint
            ("text-x-generic", "folder", None,   None),    # IGNORED
            ("text-x-generic", "folder", None,   None),    # NONE
            ("text-x-generic", "folder", None,   None),    # NORMAL
            ("text-x-generic", "folder", None,   None),    # NOCHANGE
            ("dialog-warning", None    , None,   None),    # ERROR
            (None,             None    , None,   None),    # EMPTY
            ("text-x-generic", "folder", new_fg, None),    # NEW
            ("text-x-generic", "folder", mod_fg, None),    # MODIFIED
            ("text-x-generic", "folder", con_fg, None),    # CONFLICT
            ("text-x-generic", "folder", del_fg, None),    # REMOVED
            ("text-x-generic", "folder", unk_fg, unk_fg),  # MISSING
        ]

        assert len(self.icon_details) == len(self.text_attributes) == STATE_MAX

    def value_paths(self, it):
        return [self.value_path(it, i) for i in range(self.ntree)]

    def value_path(self, it, pane):
        return self.get_value(it, self.column_index(COL_PATH, pane))

    def column_index(self, col, pane):
        return self.ntree * col + pane

    def add_entries(self, parent, names):
        child = self.append(parent)
        for pane, path in enumerate(names):
            self.set_value(child, self.column_index(COL_PATH, pane), path)
        return child

    def add_empty(self, parent, text="empty folder"):
        it = self.append(parent)
        for pane in range(self.ntree):
            self.set_value(it, self.column_index(COL_PATH, pane), None)
            self.set_state(it, pane, STATE_EMPTY, text)

    def add_error(self, parent, msg, pane):
        it = self.append(parent)
        for i in range(self.ntree):
            self.set_value(it, self.column_index(COL_STATE, i),
                           str(STATE_ERROR))
        self.set_state(it, pane, STATE_ERROR, msg)

    def set_path_state(self, it, pane, state, isdir=0):
        fullname = self.get_value(it, self.column_index(COL_PATH,pane))
        name = gobject.markup_escape_text(os.path.basename(fullname))
        self.set_state(it, pane, state, name, isdir)

    def set_state(self, it, pane, state, label, isdir=0):
        STATE = self.column_index(COL_STATE, pane)
        TEXT  = self.column_index(COL_TEXT,  pane)
        ICON  = self.column_index(COL_ICON,  pane)
        TINT  = self.column_index(COL_TINT,  pane)
        self.set_value(it, STATE, str(state))
        self.set_value(it, TEXT, gobject.markup_escape_text(label))
        self.set_value(it, ICON,  self.icon_details[state][1 if isdir else 0])
        self.set_value(it, TINT,  self.icon_details[state][3 if isdir else 2])

        state_attr = self.text_attributes[state]
        self.set_value(it, self.column_index(COL_FG, pane), state_attr[0])
        self.set_value(it, self.column_index(COL_STYLE, pane), state_attr[1])
        self.set_value(it, self.column_index(COL_WEIGHT, pane), state_attr[2])
        self.set_value(it, self.column_index(COL_STRIKE, pane), state_attr[3])

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
