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
from meld.recent import recent_comparisons
from meld.ui.util import map_widgets_into_lists


class DiffType(enum.IntEnum):
    # TODO: This should probably live in MeldWindow
    Unselected = -1
    File = 0
    Folder = 1
    Version = 2

    def supports_blank(self):
        return self in (self.File, self.Folder)


@Gtk.Template(resource_path='/org/gnome/meld/ui/new-diff-tab.ui')
class NewDiffTab(Gtk.Alignment, LabeledObjectMixin):

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

    def __init__(self, parentapp):
        super().__init__()
        map_widgets_into_lists(
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

        default_path = GLib.get_home_dir()
        for chooser in self.file_chooser:
            chooser.set_current_folder(default_path)

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

    @Gtk.Template.Callback()
    def on_file_set(self, filechooser, *args):
        gfile = filechooser.get_file()
        if not gfile:
            return

        parent = gfile.get_parent()
        if not parent:
            return

        if parent.query_file_type(
                Gio.FileQueryInfoFlags.NONE, None) == Gio.FileType.DIRECTORY:
            for chooser in self.file_chooser:
                if not chooser.get_file():
                    chooser.set_current_folder_file(parent)

        # TODO: We could do checks here to prevent errors: check to see if
        # we've got binary files; check for null file selections; sniff text
        # encodings; check file permissions.

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
        compare_gfiles = [chooser.get_file() for chooser in choosers]

        compare_kwargs = {}

        tab = self.diff_methods[self.diff_type](
            compare_gfiles, **compare_kwargs)
        recent_comparisons.add(tab)
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

    def on_file_changed(self, filename: str):
        pass

    def on_delete_event(self, *args):
        self.close_signal.emit(0)
        return Gtk.ResponseType.OK
