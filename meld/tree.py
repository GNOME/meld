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

from gi.module import get_introspection_module
from gi.repository import Gdk, GLib, GObject, Pango

from meld.style import colour_lookup_with_fallback
from meld.treehelpers import SearchableTreeStore
from meld.vc._vc import (  # noqa: F401
    CONFLICT_BASE,
    CONFLICT_LOCAL,
    CONFLICT_MERGED,
    CONFLICT_OTHER,
    CONFLICT_REMOTE,
    CONFLICT_THIS,
    STATE_CONFLICT,
    STATE_EMPTY,
    STATE_ERROR,
    STATE_IGNORED,
    STATE_MAX,
    STATE_MISSING,
    STATE_MODIFIED,
    STATE_NEW,
    STATE_NOCHANGE,
    STATE_NONE,
    STATE_NONEXIST,
    STATE_NORMAL,
    STATE_REMOVED,
    STATE_SPINNER,
)

_GIGtk = None

try:
    _GIGtk = get_introspection_module('Gtk')
except Exception:
    pass

COL_PATH, COL_STATE, COL_TEXT, COL_ICON, COL_TINT, COL_FG, COL_STYLE, \
    COL_WEIGHT, COL_STRIKE, COL_END = list(range(10))

COL_TYPES = (str, str, str, str, Gdk.RGBA, Gdk.RGBA, Pango.Style,
             Pango.Weight, bool)


class DiffTreeStore(SearchableTreeStore):

    def __init__(self, ntree, types):
        full_types = []
        for col_type in (COL_TYPES + tuple(types)):
            full_types.extend([col_type] * ntree)
        super().__init__(*full_types)
        self._none_of_cols = {
            col_num: GObject.Value(col_type, None)
            for col_num, col_type in enumerate(full_types)
        }
        self.ntree = ntree
        self._setup_default_styles()

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
            (None,   italic, normal, None),  # STATE_SPINNER
        ]

        self.icon_details = [
            # file-icon, folder-icon, file-tint
            ("text-x-generic", "folder", None),    # IGNORED
            ("text-x-generic", "folder", None),    # NONE
            ("text-x-generic", "folder", None),    # NORMAL
            ("text-x-generic", "folder", None),    # NOCHANGE
            ("dialog-warning-symbolic", None, None),    # ERROR
            (None, None, None),    # EMPTY
            ("text-x-generic", "folder", new_fg),    # NEW
            ("text-x-generic", "folder", mod_fg),    # MODIFIED
            ("text-x-generic", "folder", mod_fg),    # RENAMED
            ("text-x-generic", "folder", con_fg),    # CONFLICT
            ("text-x-generic", "folder", del_fg),    # REMOVED
            (None, "folder", unk_fg),  # MISSING
            (None, "folder", unk_fg),  # NONEXIST
            ("text-x-generic", "folder", None),    # SPINNER
        ]

        assert len(self.icon_details) == len(self.text_attributes) == STATE_MAX

    def value_paths(self, it):
        return [self.value_path(it, i) for i in range(self.ntree)]

    def value_path(self, it, pane):
        return self.get_value(it, self.column_index(COL_PATH, pane))

    def is_folder(self, it, pane, path):
        # A folder may no longer exist, and is only tracked by VC.
        # Therefore, check the icon instead, as the pane already knows.
        icon = self.get_value(it, self.column_index(COL_ICON, pane))
        return icon == "folder" or (bool(path) and os.path.isdir(path))

    def column_index(self, col, pane):
        return self.ntree * col + pane

    def add_entries(self, parent, names):
        it = self.append(parent)
        for pane, path in enumerate(names):
            self.unsafe_set(it, pane, {COL_PATH: path})
        return it

    def add_empty(self, parent, text="empty folder"):
        it = self.append(parent)
        for pane in range(self.ntree):
            self.set_state(it, pane, STATE_EMPTY, text)
        return it

    def add_error(self, parent, msg, pane, defaults={}):
        it = self.append(parent)
        key_values = {COL_STATE: str(STATE_ERROR)}
        key_values.update(defaults)
        for i in range(self.ntree):
            self.unsafe_set(it, i, key_values)
        self.set_state(it, pane, STATE_ERROR, msg)

    def set_path_state(self, it, pane, state, isdir=0, display_text=None):
        if not display_text:
            fullname = self.get_value(it, self.column_index(COL_PATH, pane))
            display_text = GLib.markup_escape_text(os.path.basename(fullname))
        self.set_state(it, pane, state, display_text, isdir)

    def set_state(self, it, pane, state, label, isdir=0):
        icon = self.icon_details[state][1 if isdir else 0]
        tint = None if isdir else self.icon_details[state][2]
        fg, style, weight, strike = self.text_attributes[state]
        self.unsafe_set(it, pane, {
            COL_STATE: str(state),
            COL_TEXT: label,
            COL_ICON: icon,
            COL_TINT: tint,
            COL_FG: fg,
            COL_STYLE: style,
            COL_WEIGHT: weight,
            COL_STRIKE: strike
        })

    def get_state(self, it, pane):
        state_idx = self.column_index(COL_STATE, pane)
        try:
            return int(self.get_value(it, state_idx))
        except TypeError:
            return None

    def _find_next_prev_diff(self, start_path):
        def match_func(it):
            # TODO: It works, but matching on the first pane only is very poor
            return self.get_state(it, 0) not in (
                STATE_NORMAL, STATE_NOCHANGE, STATE_EMPTY)

        return self.get_previous_next_paths(start_path, match_func)

    def state_rows(self, states):
        """Generator of rows in one of the given states

        Tree iterators are returned in depth-first tree order.
        """
        root = self.get_iter_first()
        for it in self.inorder_search_down(root):
            state = self.get_state(it, 0)
            if state in states:
                yield it

    def unsafe_set(self, treeiter, pane, keys_values):
        """ This must be fastest than super.set,
        at the cost that may crash the application if you don't
        know what your're passing here.
        ie: pass treeiter or column as None crash meld

        treeiter: Gtk.TreeIter
        keys_values: dict<column, value>
            column: Int col index
            value: Str (UTF-8), Int, Float, Double, Boolean, None or GObject

        return None
        """
        safe_keys_values = {
            self.column_index(col, pane):
            val if val is not None
            else self._none_of_cols.get(self.column_index(col, pane))
            for col, val in keys_values.items()
        }
        if _GIGtk and treeiter:
            columns = [col for col in safe_keys_values.keys()]
            values = [val for val in safe_keys_values.values()]
            _GIGtk.TreeStore.set(self, treeiter, columns, values)
        else:
            self.set(treeiter, safe_keys_values)


class TreeviewCommon:

    def on_treeview_popup_menu(self, treeview):
        cursor_path, cursor_col = treeview.get_cursor()
        if not cursor_path:
            self.popup_menu.popup_at_pointer(None)
            return True

        # We always want to pop up to the right of the first column,
        # ignoring the actual cursor column location.
        rect = treeview.get_background_area(
            cursor_path, treeview.get_column(0))

        self.popup_menu.popup_at_rect(
            treeview.get_bin_window(),
            rect,
            Gdk.Gravity.SOUTH_EAST,
            Gdk.Gravity.NORTH_WEST,
            None,
        )
        return True

    def on_treeview_button_press_event(self, treeview, event):

        # If we have multiple treeviews, unselect clear other tree selections
        num_panes = getattr(self, 'num_panes', 1)
        if num_panes > 1:
            for t in self.treeview[:self.num_panes]:
                if t != treeview:
                    t.get_selection().unselect_all()

        if (event.triggers_context_menu() and
                event.type == Gdk.EventType.BUTTON_PRESS):

            treeview.grab_focus()

            path = treeview.get_path_at_pos(int(event.x), int(event.y))
            if path is None:
                return False

            selection = treeview.get_selection()
            model, rows = selection.get_selected_rows()

            if path[0] not in rows:
                selection.unselect_all()
                selection.select_path(path[0])
                treeview.set_cursor(path[0])

            self.popup_menu.popup_at_pointer(event)
            return True
        return False


def treeview_search_cb(model, column, key, it, data):
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
