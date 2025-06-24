# Copyright (C) 2011-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

import enum

from gi.repository import Gio, GLib, GObject, Gtk

from meld.conf import _
from meld.melddoc import LabeledObjectMixin, MeldDoc
from meld.recent import get_recent_comparisons
from meld.ui.util import map_widgets_into_lists, map_widgets_to_dict


class DiffType(enum.IntEnum):
    # TODO: This should probably live in MeldWindow
    Unselected = -1
    File = 0
    Folder = 1
    Version = 2

    def supports_blank(self):
        return self in (self.File, self.Folder)


@Gtk.Template(resource_path='/org/gnome/meld/ui/new-diff-tab.ui')
class NewDiffTab(Gtk.Box, LabeledObjectMixin):

    __gtype_name__ = "NewDiffTab"

    __gsignals__ = {
        'diff-created': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    close_signal = MeldDoc.close_signal
    label_changed_signal = LabeledObjectMixin.label_changed

    label_text = _("New comparison")

    button_compare = Gtk.Template.Child()
    button_new_blank = Gtk.Template.Child()
    button_type_dir = Gtk.Template.Child()
    button_type_file = Gtk.Template.Child()
    button_type_vc = Gtk.Template.Child()
    choosers_notebook = Gtk.Template.Child()
    dir_chooser0 = Gtk.Template.Child()
    dir_chooser1 = Gtk.Template.Child()
    dir_chooser2 = Gtk.Template.Child()
    dir_three_way_checkbutton = Gtk.Template.Child()
    file_chooser0 = Gtk.Template.Child()
    file_chooser1 = Gtk.Template.Child()
    file_chooser2 = Gtk.Template.Child()
    file_three_way_checkbutton = Gtk.Template.Child()
    vc_chooser0 = Gtk.Template.Child()

    file_chooser_dialogs = {}
    dir_chooser_dialogs = {}
    vc_chooser_dialogs = {}

    def __init__(self, parentapp):
        super().__init__()
        map_widgets_into_lists(
            self,
            ["file_chooser", "dir_chooser", "vc_chooser"]
        )
        map_widgets_to_dict(
            self,
            ["file_chooser", "dir_chooser", "vc_chooser"]
        )
        self.button_types = [
            self.button_type_file,
            self.button_type_dir,
            self.button_type_vc,
        ]
        self.diff_methods = {
            DiffType.File: parentapp.append_filediff,
            DiffType.Folder: parentapp.append_dirdiff,
            DiffType.Version: parentapp.append_vcview,
        }
        self.diff_type = DiffType.Unselected

        self.show()

    @Gtk.Template.Callback()
    def on_button_type_toggled(self, button, *args):
        if not button.get_active():
            if not any([b.get_active() for b in self.button_types]):
                button.set_active(True)
            return

        for b in self.button_types:
            if b is not button:
                b.set_active(False)

        self.diff_type = DiffType(self.button_types.index(button))
        self.choosers_notebook.set_current_page(self.diff_type + 1)
        # FIXME: Add support for new blank for VcView
        self.button_new_blank.set_sensitive(
            self.diff_type.supports_blank())
        self.button_compare.set_sensitive(True)

    @Gtk.Template.Callback()
    def on_three_way_checkbutton_toggled(self, button, *args):
        if button is self.file_three_way_checkbutton:
            self.file_chooser2.set_sensitive(button.get_active())
        else:  # button is self.dir_three_way_checkbutton
            self.dir_chooser2.set_sensitive(button.get_active())

    def show_file_dialog(self, title, action, button, dialogs):
        if button not in dialogs:
            parent = self.get_root()
            dialog = Gtk.FileChooserNative.new(
                title=title,
                parent=parent,
                action=action)
            dialog.connect("response", self.on_file_set)

            # set default path
            if len(dialogs) > 0:
                another_dialog = list(dialogs.values())[0]
                default_path = another_dialog.get_current_folder()
            else:
                default_path = Gio.File.new_for_path(GLib.get_home_dir())
            dialog.set_current_folder(default_path)

            dialogs[button] = dialog
        else:
            dialog = dialogs[button]

        dialog.show()

    @Gtk.Template.Callback()
    def on_file_chooser_clicked(self, button):
        title = button.get_label()

        self.show_file_dialog(title, Gtk.FileChooserAction.OPEN, button, self.file_chooser_dialogs)

    @Gtk.Template.Callback()
    def on_dir_chooser_clicked(self, button):
        title = button.get_label()

        self.show_file_dialog(title, Gtk.FileChooserAction.SELECT_FOLDER, button, self.dir_chooser_dialogs)

    @Gtk.Template.Callback()
    def on_vc_chooser_clicked(self, button):
        title = button.get_label()

        self.show_file_dialog(title, Gtk.FileChooserAction.SELECT_FOLDER, button, self.vc_chooser_dialogs)

    def on_file_set(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = dialog.get_file()
            if not gfile:
                return

            if dialog in self.file_chooser_dialogs.values():
                button = list(self.file_chooser_dialogs.keys())[list(self.file_chooser_dialogs.values()).index(dialog)]
                values = self.file_chooser_values
            elif dialog in self.dir_chooser_dialogs.values():
                button = list(self.dir_chooser_dialogs.keys())[list(self.dir_chooser_dialogs.values()).index(dialog)]
                values = self.dir_chooser_values
            elif dialog in self.vc_chooser_dialogs.values():
                button = list(self.vc_chooser_dialogs.keys())[list(self.vc_chooser_dialogs.values()).index(dialog)]
                values = self.vc_chooser_values

            if button is not None:
                button.set_label(gfile.get_basename())
                values[button] = gfile

            parent = gfile.get_parent()
            if not parent:
                return

            if parent.query_file_type(
                    Gio.FileQueryInfoFlags.NONE, None) == Gio.FileType.DIRECTORY:
                dialog.set_current_folder(parent)

            # TODO: We could do checks here to prevent errors: check to see if
            # we've got binary files; check for null file selections; sniff text
            # encodings; check file permissions.

        else:
            # current folder gets reset to "recent" on cancel
            current_folder = dialog.get_current_folder()
            dialog.set_current_folder(current_folder)

    def _get_num_paths(self):
        if self.diff_type in (DiffType.File, DiffType.Folder):
            three_way_buttons = (
                self.file_three_way_checkbutton,
                self.dir_three_way_checkbutton,
            )
            three_way = three_way_buttons[self.diff_type].get_active()
            num_paths = 3 if three_way else 2
        else:  # DiffType.Version
            num_paths = 1
        return num_paths

    @Gtk.Template.Callback()
    def on_button_compare_clicked(self, *args):
        type_choosers = (self.file_chooser, self.dir_chooser, self.vc_chooser)
        choosers = type_choosers[self.diff_type][:self._get_num_paths()]
        values = (self.file_chooser_values, self.dir_chooser_values, self.vc_chooser_values)[self.diff_type]
        compare_gfiles = []

        for button in choosers:
            compare_gfiles.append(values[button])

        compare_kwargs = {}

        tab = self.diff_methods[self.diff_type](
            compare_gfiles, **compare_kwargs)
        get_recent_comparisons().add(tab)
        self.emit('diff-created', tab)

    @Gtk.Template.Callback()
    def on_button_new_blank_clicked(self, *args):
        # TODO: This doesn't work the way I'd like for DirDiff and VCView.
        # It should do something similar to FileDiff; give a tab with empty
        # file entries and no comparison done.

        # File comparison wants None for its paths here. Folder mode
        # needs an actual directory.
        if self.diff_type == DiffType.File:
            gfiles = [None] * self._get_num_paths()
        else:
            gfiles = [Gio.File.new_for_path("")] * self._get_num_paths()
        tab = self.diff_methods[self.diff_type](gfiles)
        self.emit('diff-created', tab)

    def on_container_switch_in_event(self, window):
        self.label_changed.emit(self.label_text, self.tooltip_text)

        window.text_filter_button.set_visible(False)
        window.folder_filter_button.set_visible(False)
        window.vc_filter_button.set_visible(False)
        window.next_conflict_button.set_visible(False)
        window.previous_conflict_button.set_visible(False)

    def on_container_switch_out_event(self, *args):
        pass

    def on_delete_event(self, *args):
        self.close_signal.emit(0)
        return Gtk.ResponseType.OK
