# Copyright (C) 2008-2011, 2013 Kai Willadsen <kai.willadsen@gmail.com>
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

import configparser
import os
import sys

from gi.repository import GLib, GObject, Gtk, Pango

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


class HistoryCombo(Gtk.ComboBox):
    __gtype_name__ = "HistoryCombo"

    history_id = GObject.Property(
        type=str,
        nick="History ID",
        blurb="Identifier associated with entry's history store",
        default=None,
        flags=GObject.ParamFlags.READWRITE,
    )

    history_length = GObject.Property(
        type=int,
        nick="History length",
        blurb="Number of history items to display in the combo",
        minimum=1, maximum=20,
        default=HISTORY_ENTRY_HISTORY_LENGTH_DEFAULT,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if sys.platform == "win32":
            pref_dir = os.path.join(os.getenv("APPDATA"), "Meld")
        else:
            pref_dir = os.path.join(GLib.get_user_config_dir(), "meld")

        if not os.path.exists(pref_dir):
            os.makedirs(pref_dir)

        self.history_file = os.path.join(pref_dir, "history.ini")
        self.config = configparser.RawConfigParser()
        if os.path.exists(self.history_file):
            self.config.read(self.history_file, encoding='utf8')

        self.set_model(Gtk.ListStore(str, str))
        rentext = Gtk.CellRendererText()
        rentext.props.width_chars = 60
        rentext.props.ellipsize = Pango.EllipsizeMode.END
        self.pack_start(rentext, True)
        self.add_attribute(rentext, 'text', 0)

        self.connect('notify::history-id',
                     lambda *args: self._load_history())
        self.connect('notify::history-length',
                     lambda *args: self._load_history())

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
            _clamp_list_store(store, self.props.history_length - 1)

        row = (text.splitlines()[0], text)

        if prepend:
            store.insert(0, row)
        else:
            store.append(row)
        self._save_history()

    def _load_history(self):
        section_key = self.props.history_id
        if section_key is None or not self.config.has_section(section_key):
            return

        store = self.get_model()
        store.clear()
        messages = sorted(self.config.items(section_key))
        for key, message in messages[:self.props.history_length - 1]:
            message = message.encode('utf8')
            message = message.decode('unicode-escape')
            firstline = message.splitlines()[0]
            store.append((firstline, message))

    def _save_history(self):
        section_key = self.props.history_id
        if section_key is None:
            return

        self.config.remove_section(section_key)
        self.config.add_section(section_key)
        for i, row in enumerate(self.get_model()):
            # This dance is to avoid newline, etc. issues in the ini file
            message = row[1].encode('unicode-escape')
            message = message.decode('utf8')
            self.config.set(section_key, "item%d" % i, message)
        with open(self.history_file, 'w', encoding='utf8') as f:
            self.config.write(f)
