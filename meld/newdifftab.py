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

import os

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from .ui import gnomeglade

from meld.recent import recent_comparisons


class NewDiffTab(GObject.GObject, gnomeglade.Component):

    __gtype_name__ = "NewDiffTab"

    __gsignals__ = {
        'close': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        'diff-created': (GObject.SignalFlags.RUN_FIRST, None,
                         (object,)),
    }

    def __init__(self, parentapp):
        GObject.GObject.__init__(self)
        gnomeglade.Component.__init__(self, "tab-placeholder.ui",
                                      "new_comparison_tab")
        self.map_widgets_into_lists(["file_chooser", "dir_chooser",
                                     "vc_chooser"])
        self.button_types = [self.button_type_file, self.button_type_dir,
                             self.button_type_vc]
        self.diff_methods = (parentapp.append_filediff,
                             parentapp.append_dirdiff,
                             parentapp.append_vcview)
        self.diff_type = -1

        default_path = GLib.get_home_dir()
        for chooser in self.file_chooser:
            chooser.set_current_folder(default_path)

        self.widget.show()

    def on_button_type_toggled(self, button, *args):
        if not button.get_active():
            if not any([b.get_active() for b in self.button_types]):
                button.set_active(True)
            return

        for b in self.button_types:
            if b is not button:
                b.set_active(False)

        self.diff_type = self.button_types.index(button)
        self.choosers_notebook.set_current_page(self.diff_type + 1)
        # FIXME: Add support for new blank for VcView
        self.button_new_blank.set_sensitive(self.diff_type in (0, 1))
        self.button_compare.set_sensitive(True)

    def on_three_way_checkbutton_toggled(self, button, *args):
        if button is self.file_three_way_checkbutton:
            self.file_chooser2.set_sensitive(button.get_active())
        else:  # button is self.dir_three_way_checkbutton
            self.dir_chooser2.set_sensitive(button.get_active())

    def on_file_set(self, button, *args):
        filename = button.get_filename()
        if not filename:
            return

        parent = os.path.dirname(filename)
        if os.path.isdir(parent):
            for chooser in self.file_chooser:
                if not chooser.get_filename():
                    chooser.set_current_folder(parent)

        # TODO: We could do checks here to prevent errors: check to see if
        # we've got binary files; check for null file selections; sniff text
        # encodings; check file permissions.

    def _get_num_paths(self):
        if self.diff_type in (0, 1):
            three_way_buttons = (self.file_three_way_checkbutton,
                                 self.dir_three_way_checkbutton)
            three_way = three_way_buttons[self.diff_type].get_active()
            num_paths = 3 if three_way else 2
        else:  # self.diff_type == 2
            num_paths = 1
        return num_paths

    def on_button_compare_clicked(self, *args):
        type_choosers = (self.file_chooser, self.dir_chooser, self.vc_chooser)

        compare_paths = []
        num_paths = self._get_num_paths()
        for chooser in type_choosers[self.diff_type][:num_paths]:
            gfile = chooser.get_file()
            path = gfile.get_path() if gfile else ""
            compare_paths.append(path)

        # TODO: We should be migrating to passing around either GFiles
        # or raw (i.e., not decoded) paths. Currently VcView is the
        # only thing that expects this.
        if self.diff_type in (0, 1):
            compare_paths = [p.decode('utf8') for p in compare_paths]

        tab = self.diff_methods[self.diff_type](compare_paths)
        recent_comparisons.add(tab)
        self.emit('diff-created', tab)

    def on_button_new_blank_clicked(self, *args):
        # TODO: This doesn't work the way I'd like for DirDiff and VCView.
        # It should do something similar to FileDiff; give a tab with empty
        # file entries and no comparison done.
        compare_paths = [""] * self._get_num_paths()
        tab = self.diff_methods[self.diff_type](compare_paths)
        self.emit('diff-created', tab)

    def on_container_switch_in_event(self, *args):
        pass

    def on_container_switch_out_event(self, *args):
        pass

    def on_delete_event(self, *args):
        self.emit('close', 0)
        return Gtk.ResponseType.OK
