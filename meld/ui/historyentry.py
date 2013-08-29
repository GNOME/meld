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

import os
import sys

import glib
import gio
import gtk
import gobject
import pango
import atk
# gconf is also imported; see end of HistoryEntry class for details
from gettext import gettext as _

from ..util.compat import text_type

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


class HistoryEntry(gtk.ComboBoxEntry, HistoryWidget):
    __gtype_name__ = "HistoryEntry"

    __gproperties__ = {
        "history-id": (str, "History ID",
                       "Identifier associated with entry's history store",
                       None, gobject.PARAM_READWRITE),
    }

    def __init__(self, history_id=None, enable_completion=False, **kwargs):
        super(HistoryEntry, self).__init__(**kwargs)
        HistoryWidget.__init__(self, history_id, enable_completion)
        self.props.text_column = 0


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



def _expand_filename(filename, default_dir):
    if not filename:
        return ""
    if os.path.isabs(filename):
        return filename
    expanded = os.path.expanduser(filename)
    if expanded != filename:
        return expanded
    elif default_dir:
        return os.path.expanduser(os.path.join(default_dir, filename))
    else:
        return os.path.join(os.getcwd(), filename)


last_open = {}


class HistoryFileEntry(gtk.HBox, gtk.Editable):
    __gtype_name__ = "HistoryFileEntry"

    __gsignals__ = {
        "browse_clicked" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),
        "activate" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, [])
    }

    __gproperties__ = {
        "dialog-title":    (str, "Default path",
                            "Default path for file chooser",
                            "~", gobject.PARAM_READWRITE),
        "default-path":    (str, "Default path",
                            "Default path for file chooser",
                            "~", gobject.PARAM_READWRITE),
        "directory-entry": (bool, "File or directory entry",
                            "Whether the created file chooser should select directories instead of files",
                            False, gobject.PARAM_READWRITE),
        "filename":        (str, "Filename",
                            "Filename of the selected file",
                            "", gobject.PARAM_READWRITE),
        "history-id":      (str, "History ID",
                            "Identifier associated with entry's history store",
                            None, gobject.PARAM_READWRITE),
        "modal":           (bool, "File chooser modality",
                            "Whether the created file chooser is modal",
                            False, gobject.PARAM_READWRITE),
    }


    def __init__(self, **kwargs):
        super(HistoryFileEntry, self).__init__(**kwargs)

        self.fsw = None
        self.__browse_dialog_title = None
        self.__filechooser_action = gtk.FILE_CHOOSER_ACTION_OPEN
        self.__default_path = "~"
        self.__directory_entry = False
        self.__modal = False

        self.set_spacing(3)

        # TODO: completion would be nice, but some quirks make it currently too irritating to turn on by default
        self.__gentry = HistoryEntry()
        entry = self.__gentry.get_entry()
        entry.connect("changed", lambda *args: self.emit("changed"))
        entry.connect("activate", lambda *args: self.emit("activate"))

        # We need to get rid of the pre-existing drop site on the entry
        self.__gentry.get_entry().drag_dest_unset()
        self.drag_dest_set(gtk.DEST_DEFAULT_MOTION |
                           gtk.DEST_DEFAULT_HIGHLIGHT |
                           gtk.DEST_DEFAULT_DROP,
                           [], gtk.gdk.ACTION_COPY)
        self.drag_dest_add_uri_targets()
        self.connect("drag_data_received",
                     self.history_entry_drag_data_received)

        self.pack_start(self.__gentry, True, True, 0)
        self.__gentry.show()

        button = gtk.Button(_("_Browse..."))
        button.connect("clicked", self.__browse_clicked)
        self.pack_start(button, False, False, 0)
        button.show()

        access_entry = self.__gentry.get_accessible()
        access_button = button.get_accessible()
        if access_entry and access_button:
            access_entry.set_name(_("Path"))
            access_entry.set_description(_("Path to file"))
            access_button.set_description(_("Pop up a file selector to choose a file"))
            access_button.add_relationship(atk.RELATION_CONTROLLER_FOR, access_entry)
            access_entry.add_relationship(atk.RELATION_CONTROLLED_BY, access_button)

    def do_get_property(self, pspec):
        if pspec.name == "dialog-title":
            return self.__browse_dialog_title
        elif pspec.name == "default-path":
            return self.__default_path
        elif pspec.name == "directory-entry":
            return self.__directory_entry
        elif pspec.name == "filename":
            return self.get_full_path()
        elif pspec.name == "history-id":
            return self.__gentry.props.history_id
        elif pspec.name == "modal":
            return self.__modal
        else:
            raise AttributeError("Unknown property: %s" % pspec.name)

    def do_set_property(self, pspec, value):
        if pspec.name == "dialog-title":
            self.__browse_dialog_title = value
        elif pspec.name == "default-path":
            if value:
                self.__default_path = os.path.abspath(value)
            else:
                self.__default_path = None
        elif pspec.name == "directory-entry":
            self.__directory_entry = value
        elif pspec.name == "filename":
            self.set_filename(value)
        elif pspec.name == "history-id":
            self.__gentry.props.history_id = value
        elif pspec.name == "modal":
            self.__modal = value
        else:
            raise AttributeError("Unknown property: %s" % pspec.name)

    def _get_last_open(self):
        try:
            return last_open[self.props.history_id]
        except KeyError:
            return None

    def _set_last_open(self, path):
        last_open[self.props.history_id] = path

    def append_history(self, text):
        self.__gentry.append_history(text)

    def prepend_history(self, text):
        self.__gentry.prepend_history(text)

    def focus_entry(self):
        self.__gentry.focus_entry()

    def set_default_path(self, path):
        if path:
            self.__default_path = os.path.abspath(path)
        else:
            self.__default_path = None

    def set_directory_entry(self, is_directory_entry):
        self.directory_entry = is_directory_entry

    def get_directory_entry(self):
        return self.directory_entry

    def _get_default(self):
        default = self.__default_path
        last_path = self._get_last_open()
        if last_path and os.path.exists(last_path):
            default = last_path
        return default

    def get_full_path(self):
        text = self.__gentry.get_entry().get_text()
        if not text:
            return None
        sys_text = gobject.filename_from_utf8(text)
        filename = _expand_filename(sys_text, self._get_default())
        if not filename:
            return None
        return filename

    def set_filename(self, filename):
        self.__gentry.get_entry().set_text(filename)

    def __browse_dialog_ok(self, filewidget):
        filename = filewidget.get_filename()
        if not filename:
            return

        encoding = sys.getfilesystemencoding()
        if encoding:
            filename = text_type(filename, encoding)
        entry = self.__gentry.get_entry()
        entry.set_text(filename)
        self._set_last_open(filename)
        entry.activate()

    def __browse_dialog_response(self, widget, response):
        if response == gtk.RESPONSE_ACCEPT:
            self.__browse_dialog_ok(widget)
        widget.destroy()
        self.fsw = None

    def __build_filename(self):
        default = self._get_default()

        text = self.__gentry.get_entry().get_text()
        if not text:
            return default + os.sep

        locale_text = gobject.filename_from_utf8(text)
        if not locale_text:
            return default + os.sep

        filename = _expand_filename(locale_text, default)
        if not filename:
            return default + os.sep

        if not filename.endswith(os.sep) and (self.__directory_entry or os.path.isdir(filename)):
            filename += os.sep
        return filename

    def __browse_clicked(self, *args):
        if self.fsw:
            self.fsw.show()
            if self.fsw.window:
                self.fsw.window.raise_()
            return

        if self.__directory_entry:
            action = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
            filefilter = gtk.FileFilter()
            filefilter.add_mime_type("x-directory/normal")
            title = self.__browse_dialog_title or _("Select directory")
        else:
            action = self.__filechooser_action
            filefilter = None
            title = self.__browse_dialog_title or _("Select file")

        if action == gtk.FILE_CHOOSER_ACTION_SAVE:
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
        else:
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_ACCEPT)

        self.fsw = gtk.FileChooserDialog(title, None, action, buttons, None)
        self.fsw.props.filter = filefilter
        self.fsw.set_default_response(gtk.RESPONSE_ACCEPT)
        self.fsw.set_filename(self.__build_filename())
        self.fsw.connect("response", self.__browse_dialog_response)

        toplevel = self.get_toplevel()
        modal_fentry = False
        if toplevel.flags() & gtk.TOPLEVEL:
            self.fsw.set_transient_for(toplevel)
            modal_fentry = toplevel.get_modal()
        if self.__modal or modal_fentry:
            self.fsw.set_modal(True)

        self.fsw.show()

    def history_entry_drag_data_received(self, widget, context, x, y, selection_data, info, time):
        uris = selection_data.data.split()
        if not uris:
            context.finish(False, False, time)
            return

        for uri in uris:
            path = gio.File(uri=uri).get_path()
            if path:
                break
        else:
            context.finish(False, False, time)
            return

        entry = self.__gentry.get_entry()
        entry.set_text(path)
        context.finish(True, False, time)
        self._set_last_open(path)
        entry.activate()
