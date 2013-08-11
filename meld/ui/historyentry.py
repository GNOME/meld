# Copyright (C) 2008-2009, 2013 Kai Willadsen <kai.willadsen@gmail.com>
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

import ConfigParser
import os
import sys

import glib
import gobject
import gtk
import pango

# This file started off as a Python translation of:
#  * gedit/gedit/gedit-history-entry.c
#  * libgnomeui/libgnomeui/gnome-file-entry.c
# roughly based on Colin Walters' Python translation of msgarea.py from Hotwire

MIN_ITEM_LEN = 3
HISTORY_ENTRY_HISTORY_LENGTH_DEFAULT = 10


def _remove_item(store, text):
    if text is None:
        return False

    for row in store:
        if row[1] == text:
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


class HistoryCombo(gtk.ComboBox):
    __gtype_name__ = "HistoryCombo"

    __gproperties__ = {
        "history-id": (str, "History ID",
                       "Identifier associated with entry's history store",
                       None,
                       gobject.PARAM_CONSTRUCT_ONLY | gobject.PARAM_READWRITE),
        "history-length": (int, "History length",
                           "Number of history items to display in the combo",
                           1, 20, HISTORY_ENTRY_HISTORY_LENGTH_DEFAULT,
                           gobject.PARAM_READWRITE),
    }

    def __init__(self, **kwargs):
        super(HistoryCombo, self).__init__(**kwargs)

        if sys.platform == "win32":
            pref_dir = os.path.join(os.getenv("APPDATA"), "Meld")
        else:
            pref_dir = os.path.join(glib.get_user_config_dir(), "meld")

        if not os.path.exists(pref_dir):
            os.makedirs(pref_dir)

        self.history_file = os.path.join(pref_dir, "history.ini")
        self.config = ConfigParser.SafeConfigParser()
        if os.path.exists(self.history_file):
            self.config.read(self.history_file)

        self._history_id = None
        self._history_length = HISTORY_ENTRY_HISTORY_LENGTH_DEFAULT

        self.set_model(gtk.ListStore(str, str))
        rentext = gtk.CellRendererText()
        rentext.props.width_chars = 60
        rentext.props.ellipsize = pango.ELLIPSIZE_END
        self.pack_start(rentext, True)
        self.set_attributes(rentext, text=0)

    def do_get_property(self, pspec):
        if pspec.name == "history-id":
            return self._history_id
        elif pspec.name == "history-length":
            return self._history_length
        else:
            raise AttributeError("Unknown property: %s" % pspec.name)

    def do_set_property(self, pspec, value):
        if pspec.name == "history-id":
            self._history_id = value
            self._load_history()
        elif pspec.name == "history-length":
            if value <= 0:
                raise ValueError("History length cannot be less than one")
            self._history_length = value
            if len(self.get_model()) > self._history_length:
                self._load_history()
        else:
            raise AttributeError("Unknown property: %s" % pspec.name)

    def prepend_history(self, text):
        self._insert_history_item(text, True)

    def append_history(self, text):
        self._insert_history_item(text, False)

    def clear(self):
        self.get_model().clear()
        self._save_history()

    def _insert_history_item(self, text, prepend):
        if not text or len(text) <= MIN_ITEM_LEN:
            return

        store = self.get_model()
        if not _remove_item(store, text):
            _clamp_list_store(store, self._history_length - 1)

        row = (text.splitlines()[0], text)

        if prepend:
            store.insert(0, row)
        else:
            store.append(row)
        self._save_history()

    def _load_history(self):
        section_key = self._history_id
        if section_key is None or not self.config.has_section(section_key):
            return

        store = self.get_model()
        store.clear()
        paths = sorted(self.config.items(section_key))
        for key, path in paths[:self._history_length - 1]:
            path = path.decode("string-escape")
            firstline = path.splitlines()[0]
            store.append((firstline, path))

    def _save_history(self):
        section_key = self._history_id
        if section_key is None:
            return

        self.config.remove_section(section_key)
        self.config.add_section(section_key)
        for i, row in enumerate(self.get_model()):
            message = row[1].encode('string-escape')
            self.config.set(section_key, "item%d" % i, message)
        with open(self.history_file, 'w') as f:
            self.config.write(f)
