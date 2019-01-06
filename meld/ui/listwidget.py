# Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2011, 2013, 2018 Kai Willadsen <kai.willadsen@gmail.com>
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


class EditableListWidget:

    """Helper class with behaviour for simple editable lists

    The entire point of this is to handle simple list item addition,
    removal, and rearrangement, and the associated sensitivity handling.

    This requires template children to be bound as:
      * `treeview`
      * `remove`
      * `move_up`
      * `move_down`
    """

    def setup_sensitivity_handling(self):
        model = self.treeview.get_model()
        model.connect("row-inserted", self._update_sensitivity)
        model.connect("rows-reordered", self._update_sensitivity)
        self.treeview.get_selection().connect(
            "changed", self._update_sensitivity)
        self._update_sensitivity()

    def _update_sensitivity(self, *args):
        model, it, path = self._get_selected()
        if not it:
            self.remove.set_sensitive(False)
            self.move_up.set_sensitive(False)
            self.move_down.set_sensitive(False)
        else:
            self.remove.set_sensitive(True)
            self.move_up.set_sensitive(path > 0)
            self.move_down.set_sensitive(path < len(model) - 1)

    def _get_selected(self):
        model, it = self.treeview.get_selection().get_selected()
        path = model.get_path(it)[0] if it else None
        return (model, it, path)

    def add_entry(self):
        self.treeview.get_model().append(self.default_entry)

    def remove_selected_entry(self):
        model, it, path = self._get_selected()
        model.remove(it)

    def move_up_selected_entry(self):
        model, it, path = self._get_selected()
        model.swap(it, model.get_iter(path - 1))

    def move_down_selected_entry(self):
        model, it, path = self._get_selected()
        model.swap(it, model.get_iter(path + 1))
