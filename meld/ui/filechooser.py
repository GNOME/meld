# Copyright (C) 2016 Kai Willadsen <kai.willadsen@gmail.com>
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

"""This module provides file choosers that let users select a text encoding."""

from gi.repository import Gtk
from gi.repository import GtkSource


FILE_ACTIONS = {
    Gtk.FileChooserAction.OPEN,
    Gtk.FileChooserAction.SAVE,
}


class MeldFileChooserDialog(Gtk.FileChooserDialog):

    """A simple GTK+ file chooser dialog with a text encoding combo box."""

    __gtype_name__ = 'MeldFileChooserDialog'

    def __init__(
            self, title=None, transient_for=None,
            action=Gtk.FileChooserAction.OPEN):
        super().__init__(
          title=title, transient_for=transient_for, action=action)

        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        if action == Gtk.FileChooserAction.SAVE:
            self.add_button(Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT)
        else:
            self.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT)

        self.encoding_store = Gtk.ListStore(str, str)
        self.connect("notify::action", self.action_changed_cb)

        # We only have sufficient Gio support for remote operations in
        # file comparisons, not in folder or version-control.
        self.props.local_only = action not in FILE_ACTIONS

    def make_encoding_combo(self):
        """Create the combo box for text encoding selection"""
        codecs = []
        current = GtkSource.encoding_get_current()
        codecs.append((current.to_string(), current.get_charset()))
        codecs.append((None, None))
        for encoding in GtkSource.encoding_get_all():
            codecs.append((encoding.to_string(), encoding.get_charset()))

        self.encoding_store.clear()
        for entry in codecs:
            self.encoding_store.append(entry)

        combo = Gtk.ComboBox()
        combo.set_model(self.encoding_store)
        cell = Gtk.CellRendererText()
        combo.pack_start(cell, True)
        combo.add_attribute(cell, 'text', 0)
        combo.set_row_separator_func(
            lambda model, it, data: not model.get_value(it, 1), None)
        combo.props.active = 0
        return combo

    def get_encoding(self):
        """Return the currently-selected text file encoding"""
        combo = self.props.extra_widget
        if not combo:
            return None
        charset = self.encoding_store.get_value(combo.get_active_iter(), 1)
        return GtkSource.Encoding.get_from_charset(charset)

    def action_changed_cb(self, *args):
        if self.props.action in (Gtk.FileChooserAction.OPEN,
                                 Gtk.FileChooserAction.SAVE):
            self.props.extra_widget = self.make_encoding_combo()
        else:
            self.props.extra_widget = None
