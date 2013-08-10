# Copyright (C) 2008-2009 Kai Willadsen <kai.willadsen@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

import glib
import gtk
import gobject
import pango
# gconf is also imported; see end of HistoryEntry class for details

# This file is a Python translation of:
#  * gedit/gedit/gedit-history-entry.c
#  * libgnomeui/libgnomeui/gnome-file-entry.c
# roughly based on Colin Walters' Python translation of msgarea.py from Hotwire

MIN_ITEM_LEN = 3
HISTORY_ENTRY_HISTORY_LENGTH_DEFAULT = 10


def _remove_item(store, text):
    if text is None:
        return False

    for row in store:
        if row[0] == text:
            store.remove(row.iter)
            return True
    return False


def _clamp_list_store(liststore, max_items):
    try:
        # -1 because TreePath counts from 0
        it = liststore.get_iter(max_items - 1)
    except ValueError:
        return
    valid = True
    while valid:
        valid = liststore.remove(it)


def _escape_cell_data_func(col, renderer, model, it, escape_func):
    string = model.get(it, 0)
    escaped = escape_func(string)
    renderer.set("text", escaped)


class HistoryWidget(object):

    def __init__(self, history_id=None, enable_completion=False, **kwargs):
        self._history_id = history_id
        self._history_length = HISTORY_ENTRY_HISTORY_LENGTH_DEFAULT
        self._completion = None
        self._get_gconf_client()

        self.set_model(gtk.ListStore(str))
        self.set_enable_completion(enable_completion)

    def do_get_property(self, pspec):
        if pspec.name == "history-id":
            return self._history_id
        else:
            raise AttributeError("Unknown property: %s" % pspec.name)

    def do_set_property(self, pspec, value):
        if pspec.name == "history-id":
            # FIXME: if we change history-id after our store is populated, odd
            # things might happen
            store = self.get_model()
            store.clear()
            self._history_id = value
            self._load_history()
        else:
            raise AttributeError("Unknown property: %s" % pspec.name)

    def _get_gconf_client(self):
        self._gconf_client = gconf.client_get_default()

    def _get_history_key(self):
        # We store data under /apps/gnome-settings/ like GnomeEntry did.
        if not self._history_id:
            return None
        key = ''.join(["/apps/gnome-settings/", "meld", "/history-",
                       gconf.escape_key(self._history_id, -1)])
        return key

    def _save_history(self):
        key = self._get_history_key()
        if key is None:
            return
        gconf_items = [row[0] for row in self.get_model()]
        self._gconf_client.set_list(key, gconf.VALUE_STRING, gconf_items)

    def _insert_history_item(self, text, prepend):
        if len(text) <= MIN_ITEM_LEN:
            return

        store = self.get_model()
        if not _remove_item(store, text):
            _clamp_list_store(store, self._history_length - 1)

        if (prepend):
            store.insert(0, (text,))
        else:
            store.append((text,))
        self._save_history()

    def prepend_history(self, text):
        if not text:
            return
        self._insert_history_item(text, True)

    def append_history(self, text):
        if not text:
            return
        self._insert_history_item(text, False)

    def _load_history(self):
        key = self._get_history_key()
        if key is None:
            return
        gconf_items = self._gconf_client.get_list(key, gconf.VALUE_STRING)

        store = self.get_model()
        store.clear()

        for item in gconf_items[:self._history_length - 1]:
            store.append((item,))

    def clear(self):
        store = self.get_model()
        store.clear()
        self._save_history()

    def set_history_length(self, max_saved):
        if max_saved <= 0:
            return
        self._history_length = max_saved
        if len(self.get_model()) > max_saved:
            self._load_history()

    def get_history_length(self):
        return self._history_length

    def set_enable_completion(self, enable):
        if enable:
            if self._completion is not None:
                return
            self._completion = gtk.EntryCompletion()
            self._completion.set_model(self.get_model())
            self._completion.set_text_column(0)
            self._completion.set_minimum_key_length(MIN_ITEM_LEN)
            self._completion.set_popup_completion(False)
            self._completion.set_inline_completion(True)
            self.child.set_completion(self._completion)
        else:
            if self._completion is None:
                return
            self.get_entry().set_completion(None)
            self._completion = None

    def get_enable_completion(self):
        return self._completion is not None

    def get_entry(self):
        return self.child

    def focus_entry(self):
        self.child.grab_focus()

    def set_escape_func(self, escape_func):
        cells = self.get_cells()
        # We only have one cell renderer
        if len(cells) == 0 or len(cells) > 1:
            return

        if escape_func is not None:
            self.set_cell_data_func(cells[0], _escape_cell_data_func, escape_func)
        else:
            self.set_cell_data_func(cells[0], None, None)


# TODO: There is no point having this separation now

class HistoryCombo(gtk.ComboBox, HistoryWidget):
    __gtype_name__ = "HistoryCombo"

    __gproperties__ = {
        "history-id": (str, "History ID",
                       "Identifier associated with entry's history store",
                       None, gobject.PARAM_READWRITE),
    }

    def __init__(self, history_id=None, **kwargs):
        super(HistoryCombo, self).__init__(**kwargs)
        HistoryWidget.__init__(self, history_id)
        self.set_model(gtk.ListStore(str, str))
        rentext = gtk.CellRendererText()
        rentext.props.width_chars = 60
        rentext.props.ellipsize = pango.ELLIPSIZE_END
        self.pack_start(rentext, True)
        self.set_attributes(rentext, text=0)

    def _save_history(self):
        key = self._get_history_key()
        if key is None:
            return
        gconf_items = [row[1] for row in self.get_model()]
        self._gconf_client.set_list(key, gconf.VALUE_STRING, gconf_items)

    def _insert_history_item(self, text, prepend):
        if len(text) <= MIN_ITEM_LEN:
            return

        # Redefining here to key off the full text, not the first line
        def _remove_item(store, text):
            if text is None:
                return False

            for row in store:
                if row[1] == text:
                    store.remove(row.iter)
                    return True
            return False

        store = self.get_model()
        if not _remove_item(store, text):
            _clamp_list_store(store, self._history_length - 1)

        row = (text.splitlines()[0], text)

        if (prepend):
            store.insert(0, row)
        else:
            store.append(row)
        self._save_history()

    def _load_history(self):
        key = self._get_history_key()
        if key is None:
            return
        gconf_items = self._gconf_client.get_list(key, gconf.VALUE_STRING)

        store = self.get_model()
        store.clear()

        # This override is here to handle multi-line commit messages, and is
        # specific to HistoryCombo use in VcView.
        for item in gconf_items[:self._history_length - 1]:
            firstline = item.splitlines()[0]
            store.append((firstline, item))


try:
    import gconf
    # Verify that gconf is actually working (bgo#666136)
    client = gconf.client_get_default()
    key = '/apps/meld/gconf-test'
    client.set_int(key, os.getpid())
    client.unset(key)
except (ImportError, glib.GError):
    do_nothing = lambda *args: None
    for m in ('_save_history', '_load_history', '_get_gconf_client'):
        setattr(HistoryWidget, m, do_nothing)
        setattr(HistoryCombo, m, do_nothing)

