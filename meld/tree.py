# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2011-2015 Kai Willadsen <kai.willadsen@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
from gi.repository import GLib
from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import Pango

COL_PATH, COL_STATE, COL_TEXT, COL_ICON, COL_TINT, COL_FG, COL_STYLE, \
    COL_WEIGHT, COL_STRIKE, COL_END = list(range(10))

COL_TYPES = (str, str, str, str, str, Gdk.RGBA, Pango.Style,
             Pango.Weight, bool)

from meld.misc import colour_lookup_with_fallback
from meld.vc._vc import \
    STATE_IGNORED, STATE_NONE, STATE_NORMAL, STATE_NOCHANGE, \
    STATE_ERROR, STATE_EMPTY, STATE_NEW, \
    STATE_MODIFIED, STATE_CONFLICT, STATE_REMOVED, \
    STATE_MISSING, STATE_NONEXIST, STATE_MAX, \
    CONFLICT_BASE, CONFLICT_LOCAL, CONFLICT_REMOTE, \
    CONFLICT_MERGED, CONFLICT_OTHER, CONFLICT_THIS


class DiffTreeStore(Gtk.TreeStore):

    def __init__(self, ntree, types):
        full_types = []
        for col_type in (COL_TYPES + tuple(types)):
            full_types.extend([col_type] * ntree)
        Gtk.TreeStore.__init__(self, *full_types)
        self.ntree = ntree
        self._setup_default_styles()

    def on_style_updated(self, widget):
        style = widget.get_style_context()
        self._setup_default_styles(style)

    def _setup_default_styles(self, style=None):
        roman, italic = Pango.Style.NORMAL, Pango.Style.ITALIC
        normal, bold = Pango.Weight.NORMAL, Pango.Weight.BOLD

        lookup = colour_lookup_with_fallback
        unk_fg = lookup("meld:unknown-text", "foreground")
        new_fg = lookup("meld:insert", "foreground")
        mod_fg = lookup("meld:replace", "foreground")
        del_fg = lookup("meld:delete", "foreground")
        err_fg = lookup("meld:error", "foreground")
        con_fg = lookup("meld:conflict", "foreground")

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
            (mod_fg, roman,  normal, None),  # STATE_RENAMED
            (con_fg, roman,  bold,   None),  # STATE_CONFLICT
            (del_fg, roman,  bold,   True),  # STATE_REMOVED
            (del_fg, roman,  bold,   True),  # STATE_MISSING
            (unk_fg, roman,  normal, True),  # STATE_NONEXIST
        ]

        self.icon_details = [
            # file-icon, folder-icon, file-tint, folder-tint
            ("text-x-generic", "folder", None,   None),    # IGNORED
            ("text-x-generic", "folder", None,   None),    # NONE
            ("text-x-generic", "folder", None,   None),    # NORMAL
            ("text-x-generic", "folder", None,   None),    # NOCHANGE
            ("dialog-warning", None,     None,   None),    # ERROR
            (None,             None,     None,   None),    # EMPTY
            ("text-x-generic", "folder", new_fg, None),    # NEW
            ("text-x-generic", "folder", mod_fg, None),    # MODIFIED
            ("text-x-generic", "folder", mod_fg, None),    # RENAMED
            ("text-x-generic", "folder", con_fg, None),    # CONFLICT
            ("text-x-generic", "folder", del_fg, None),    # REMOVED
            ("text-x-generic", "folder", unk_fg, unk_fg),  # MISSING
            ("text-x-generic", "folder", unk_fg, unk_fg),  # NONEXIST
        ]

        assert len(self.icon_details) == len(self.text_attributes) == STATE_MAX

    def value_paths(self, it):
        return [self.value_path(it, i) for i in range(self.ntree)]

    def value_path(self, it, pane):
        path = self.get_value(it, self.column_index(COL_PATH, pane))
        if path is not None:
            path = path.decode('utf8')
        return path

    def is_folder(self, it, pane, path):
        # A folder may no longer exist, and is only tracked by VC.
        # Therefore, check the icon instead, as the pane already knows.
        icon = self.get_value(it, self.column_index(COL_ICON, pane))
        return icon == "folder" or os.path.isdir(path)

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
        fullname = self.get_value(it, self.column_index(COL_PATH, pane))
        name = GLib.markup_escape_text(os.path.basename(fullname))
        self.set_state(it, pane, state, name, isdir)

    def set_state(self, it, pane, state, label, isdir=0):
        col_idx = self.column_index
        icon = self.icon_details[state][1 if isdir else 0]
        tint = self.icon_details[state][3 if isdir else 2]
        self.set_value(it, col_idx(COL_STATE, pane), str(state))
        self.set_value(it, col_idx(COL_TEXT,  pane), label)
        self.set_value(it, col_idx(COL_ICON,  pane), icon)
        # FIXME: This is horrible, but EmblemCellRenderer crashes
        # if you try to give it a Gdk.Color property
        if tint:
            tint = tint.to_string() if tint else None
        self.set_value(it, col_idx(COL_TINT, pane), tint)

        fg, style, weight, strike = self.text_attributes[state]
        self.set_value(it, col_idx(COL_FG, pane), fg)
        self.set_value(it, col_idx(COL_STYLE, pane), style)
        self.set_value(it, col_idx(COL_WEIGHT, pane), weight)
        self.set_value(it, col_idx(COL_STRIKE, pane), strike)

    def get_state(self, it, pane):
        STATE = self.column_index(COL_STATE, pane)
        try:
            return int(self.get_value(it, STATE))
        except TypeError:
            return None

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
                path = path[:-1] + [path[-1] - 1]
                it = self.get_iter(path)
                while 1:
                    nc = self.iter_n_children(it)
                    if nc:
                        it = self.iter_nth_child(it, nc - 1)
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

    def treeview_search_cb(self, model, column, key, it, data):
        # If the key contains a path separator, search the whole path,
        # otherwise just use the filename. If the key is all lower-case, do a
        # case-insensitive match.
        abs_search = '/' in key
        lower_key = key.islower()

        for path in model.value_paths(it):
            if not path:
                continue
            text = path if abs_search else os.path.basename(path)
            text = text.lower() if lower_key else text
            if key in text:
                return False
        return True
