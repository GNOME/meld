### Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2010-2011 Kai Willadsen <kai.willadsen@gmail.com>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


import gnomeglade
from meld import paths


class ListWidget(gnomeglade.Component):

    def __init__(self, new_row_data=None):
        gnomeglade.Component.__init__(self, paths.ui_dir("EditableList.ui"),
                                      "list_alignment", ["EditableListStore"])
        self.new_row_data = new_row_data
        self.model = self.EditableList.get_model()
        selection = self.EditableList.get_selection()
        selection.connect("changed", self._update_sensitivity)

    def _update_sensitivity(self, *args):
        (model, it, path) = self._get_selected()
        if not it:
            self.remove.set_sensitive(False)
            self.move_up.set_sensitive(False)
            self.move_down.set_sensitive(False)
        else:
            self.remove.set_sensitive(True)
            self.move_up.set_sensitive(path > 0)
            self.move_down.set_sensitive(path < len(model) - 1)

    def _get_selected(self):
        (model, it) = self.EditableList.get_selection().get_selected()
        if it:
            path = model.get_path(it)[0]
        else:
            path = None
        return (model, it, path)

    def on_add_clicked(self, button):
        self.model.append(self.new_row_data)

    def on_remove_clicked(self, button):
        (model, it, path) = self._get_selected()
        self.model.remove(it)

    def on_move_up_clicked(self, button):
        (model, it, path) = self._get_selected()
        model.swap(it, model.get_iter(path - 1))

    def on_move_down_clicked(self, button):
        (model, it, path) = self._get_selected()
        model.swap(it, model.get_iter(path + 1))

