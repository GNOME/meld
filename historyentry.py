# Copyright (C) 2008 Kai Willadsen <kai.willadsen@gmail.com>
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
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import os

import gtk
import gobject
import atk
# gconf is also imported; see end of HistoryEntry class for details
# gnomevfs is also imported; see end of HistoryFileEntry class for details
from gettext import gettext as _

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
        it = liststore.get_iter(max_items - 1) # -1 because TreePath counts from 0
    except ValueError:
        return
    valid = True
    while valid:
        valid = liststore.remove(it)

def _escape_cell_data_func(col, renderer, model, iter, escape_func):
    string = model.get(iter, 0)
    escaped = escape_func(string)
    renderer.set("text", escaped)


class HistoryEntry(gtk.ComboBoxEntry):

    def __init__(self, history_id=None, enable_completion=False, **kwargs):
        super(HistoryEntry, self).__init__(**kwargs)

        self.__history_id = history_id
        self.__history_length = HISTORY_ENTRY_HISTORY_LENGTH_DEFAULT
        self.__completion = None
        self._get_gconf_client()

        self.set_model(gtk.ListStore(str))
        self.props.text_column = 0

        self._load_history()
        self.set_enable_completion(enable_completion)

    def _get_gconf_client(self):
        self.__gconf_client = gconf.client_get_default()

    def __get_history_store(self):
        return self.get_model()

    def __get_history_key(self):
        # We store data under /apps/gnome-settings/ like GnomeEntry did.
        if not self.__history_id:
            return None
        key = ''.join(["/apps/gnome-settings/","meld","/history-",
                          gconf.escape_key(self.__history_id, -1)])
        return key

    def __get_history_list(self):
        return [row[0] for row in self.__get_history_store()]

    def _save_history(self):
        key = self.__get_history_key()
        if key is None:
            return
        gconf_items = self.__get_history_list()
        self.__gconf_client.set_list(key, gconf.VALUE_STRING, gconf_items)

    def __insert_history_item(self, text, prepend):
        if len(text) <= MIN_ITEM_LEN:
            return

        store = self.__get_history_store()
        if not _remove_item(store, text):
            _clamp_list_store(store, self.__history_length - 1)

        if (prepend):
            store.insert(0, (text,))
        else:
            store.append((text,))
        self._save_history()

    def prepend_text(self, text):
        if not text:
            return
        self.__insert_history_item(text, True)

    def append_text(self, text):
        if not text:
            return
        self.__insert_history_item(text, False)

    def _load_history(self):
        key = self.__get_history_key()
        if key is None:
            return
        gconf_items = self.__gconf_client.get_list(key, gconf.VALUE_STRING)

        store = self.__get_history_store()
        store.clear()

        for item in gconf_items[:self.__history_length - 1]:
            store.append((item,))

    def clear(self):
        store = self.__get_history_store()
        store.clear()
        self._save_history()

    def set_history_length(self, max_saved):
        if max_saved <= 0:
            return
        self.__history_length = max_saved
        if len(self.__get_history_store()) > max_saved:
            self._load_history()

    def get_history_length(self):
        return self.__history_length

    def get_history_id(self):
        return self.__history_id

    def __set_history_id(self, history_id):
        self.__history_id = history_id
        self._load_history()

    def set_enable_completion(self, enable):
        if enable:
            if self.__completion is not None:
                return
            self.__completion = gtk.EntryCompletion()
            self.__completion.set_model(self.__get_history_store())
            self.__completion.set_text_column(0)
            self.__completion.set_minimum_key_length(MIN_ITEM_LEN)
            self.__completion.set_popup_completion(False)
            self.__completion.set_inline_completion(True)
            self.child.set_completion(self.__completion)
        else:
            if self.__completion is None:
                return
            self.get_entry().set_completion(None)
            self.__completion = None

    def get_enable_completion(self):
        return self.__completion is not None

    def get_entry(self):
        return self.child

    def set_escape_func(self, escape_func):
        cells = self.get_cells()
        # We only have one cell renderer
        if len(cells) == 0 or len(cells) > 1:
            return

        if escape_func is not None:
            self.set_cell_data_func(cells[0], _escape_cell_data_func, escape_func)
        else:
            self.set_cell_data_func(cells[0], None, None)

    history_id = gobject.property(get_history_id, __set_history_id, type=str)
    max_saved = gobject.property(get_history_length, set_history_length, type=int)

try:
    import gconf
except ImportError:
    do_nothing = lambda *args: None
    for m in ('_save_history', '_load_history', '_get_gconf_client'):
        setattr(HistoryEntry, m, do_nothing)



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


class HistoryFileEntry(gtk.HBox, gtk.Editable):
    __gsignals__ = {
        "browse_clicked" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, []),
        "activate" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, [])
    }

    def __init__(self, history_id=None, browse_dialog_title=None, **kwargs):
        super(HistoryFileEntry, self).__init__(**kwargs)

        self.fsw = None
        self.__default_path = "~"
        # TODO: completion would be nice, but some quirks make it currently too irritating to turn on by default
        self.__gentry = HistoryEntry(history_id, False)
        self.browse_dialog_title = browse_dialog_title
        self.__filechooser_action = gtk.FILE_CHOOSER_ACTION_OPEN
        self.__is_modal = False
        self.directory_entry = False

        self.set_spacing(3)

        self.gtk_entry.connect("changed", self.__entry_changed_signal)
        self.gtk_entry.connect("activate", self.__entry_activate_signal)

        self._setup_dnd()

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

    def _setup_dnd(self):
        # we must get rid of gtk's drop site on the entry else weird stuff can happen
        self.gtk_entry.drag_dest_unset()
        self.drag_dest_set(gtk.DEST_DEFAULT_MOTION |
                           gtk.DEST_DEFAULT_HIGHLIGHT |
                           gtk.DEST_DEFAULT_DROP,
                           [], gtk.gdk.ACTION_COPY)
        self.drag_dest_add_uri_targets()
        self.connect("drag_data_received", self.history_entry_drag_data_received)

    def gnome_entry(self):
        return self.__gentry

    def gtk_entry(self):
        return self.__gentry.child

    def set_title(self, browse_dialog_title):
        self.browse_dialog_title = browse_dialog_title

    def set_default_path(self, path):
        if path:
            self.__default_path = os.path.abspath(path)
        else:
            self.__default_path = None

    def set_directory_entry(self, is_directory_entry):
        self.directory_entry = is_directory_entry

    def get_directory_entry(self):
        return self.directory_entry

    def get_full_path(self, file_must_exist=False):
        text = self.__gentry.child.get_text()
        if not text:
            return None

        sys_text = gobject.filename_from_utf8(text)
        filename = _expand_filename(sys_text, self.__default_path)
        if not filename:
            return None

        if file_must_exist:
            if self.directory_entry:
                if os.path.isdir(filename):
                    return filename

                d = os.path.dirname(filename)
                if os.path.isdir(d):
                    return d

                return None
            elif os.path.isfile(filename):
                return filename
            return None
        else:
            return filename

    def set_filename(self, filename):
        self.__gentry.child.set_text(filename)

    def set_modal(self, is_modal):
        self.__is_modal = is_modal

    def get_modal(self):
        return self.__is_modal

    def __browse_dialog_ok(self, filewidget):
        locale_filename = filewidget.get_filename()
        if not locale_filename:
            return

        encoding = os.getenv("G_FILENAME_ENCODING")
        if encoding:
            # FIXME: This isn't tested.
            locale_filename = unicode(locale_filename, encoding)
        self.gtk_entry.set_text(locale_filename)
        self.gtk_entry.emit("changed")
        self.gtk_entry.activate()
        filewidget.hide()

    def __browse_dialog_response(self, widget, response):
        if response == gtk.RESPONSE_ACCEPT:
            self.__browse_dialog_ok(widget)
        else:
            widget.hide()

    def __setup_filter(self, filechooser, *args):
        filefilter = gtk.FileFilter()
        filefilter.add_mime_type("x-directory/normal")
        filechooser.set_filter(filefilter)

    def __build_filename(self):
        text = self.gtk_entry.get_text()

        if text is None or len(text) == 0:
            return self.__default_path + os.sep

        locale_text = gobject.filename_from_utf8(text)
        if locale_text is None:
            return self.__default_path + os.sep

        filename = _expand_filename(locale_text, self.__default_path)
        if not filename:
            return self.__default_path + os.sep

        if len(filename) != 0 and not filename.endswith(os.sep) and (self.directory_entry or os.path.isdir(filename)):
            return filename + os.sep

        return filename

    def __browse_clicked(self, *args):
        if self.fsw:
            self.fsw.show()
            if self.fsw.window:
                self.fsw.window.raise_()

            if self.directory_entry:
                self.fsw.set_action(gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
            else:
                self.fsw.set_action(gtk.FILE_CHOOSER_ACTION_OPEN)

            p = self.__build_filename()
            if p:
                self.fsw.set_filename(p)

            return

        if self.directory_entry:
            action = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
        else:
            action = self.__filechooser_action

        title = self.browse_dialog_title or _("Select file")
        self.fsw = gtk.FileChooserDialog(title, None, action,
                               (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL), None)

        if action == gtk.FILE_CHOOSER_ACTION_SAVE:
            self.fsw.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
        else:
            self.fsw.add_button(gtk.STOCK_OPEN, gtk.RESPONSE_ACCEPT)

        if self.directory_entry:
            self.fsw.connect("size-request", self.__setup_filter, self)

        self.fsw.set_default_response(gtk.RESPONSE_ACCEPT)

        p = self.__build_filename()
        if p:
            self.fsw.set_filename(p)
            self.fsw.connect("response", self.__browse_dialog_response)

        toplevel = self.get_toplevel()
        modal_fentry = False
        if toplevel.flags() & gtk.TOPLEVEL:
            self.fsw.set_transient_for(toplevel)
            modal_fentry = toplevel.get_modal()

        if self.__is_modal or modal_fentry:
            self.fsw.set_modal(True)

        self.fsw.show()

    def __entry_changed_signal(self, widget, *data):
        self.emit("changed")

    def __entry_activate_signal(self, widget, *data):
        self.emit("activate")

    def __get_history_id(self):
        self.__gentry.get_history_id()

    def __set_history_id(self, newid):
        self.__gentry.props.history_id = newid

    def history_entry_drag_data_received(self, widget, context, x, y, selection_data, info, time):
        uris = selection_data.data.split()
        if not uris:
            context.finish(False, False, time)
            return

        for uri in uris:
            path = gnomevfs.get_local_path_from_uri(uri)
            if path:
                break
        else:
            context.finish(False, False, time)
            return

        widget.gtk_entry.set_text(path)
        widget.gtk_entry.emit("changed")
        widget.gtk_entry.activate()

    browse_dialog_title = gobject.property(type=str)
    default_path = gobject.property(lambda self: self.__default_path, set_default_path, type=str)
    directory_entry = gobject.property(type=bool, default=False)
    filechooser_action = gobject.property(type=gobject.GObject) # FIXME: gtk.FileChooserAction with newer pygobject
    filename = gobject.property(get_full_path, set_filename, type=str)
    gnome_entry = gobject.property(gnome_entry, None, type=gobject.GObject) # FIXME: historyentry.Historyentry with newer pygobject
    gtk_entry = gobject.property(gtk_entry, None, type=gobject.GObject) # FIXME: gtk.Entry with newer pygobject
    history_id = gobject.property(__get_history_id, __set_history_id, type=str)
    modal = gobject.property(set_modal, get_modal, type=bool, default=False)
    use_filechooser = gobject.property(type=bool, default=True)

try:
    import gnomevfs
except ImportError:
    do_nothing = lambda *args: None
    setattr(HistoryFileEntry, '_setup_dnd', do_nothing)

def create_fileentry( history_id, dialog_title, is_directory_entry, int2):
    w = HistoryFileEntry(history_id, dialog_title)
    w.directory_entry = is_directory_entry
    return w

def create_entry( history_id, str2, int1, int2):
    w = HistoryEntry(history_id)
    return w

