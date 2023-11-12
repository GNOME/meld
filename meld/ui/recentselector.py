# Copyright (C) 2019 Kai Willadsen <kai.willadsen@gmail.com>
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


from gi.repository import Gio, GObject, Gtk

from meld.recent import get_recent_comparisons


class RecentListModelEntry(GObject.Object):
    """ an entry in the recent list model, contains a Gtk.RecentInfo """

    def __init__(self, item):
        GObject.Object.__init__(self)
        self.item = item

class RecentListModel(GObject.Object, Gio.ListModel):
    """ recent list model, contains a list of recent files """

    items = []

    def __init__(self):
        GObject.Object.__init__(self)

    def do_get_item(self, position):
        """ get item in model """

        if position < len(self.items):
            item = self.items[position]
            return item

        return None

    def do_get_n_items(self):
        """ get model item list length """
        size = len(self.items)
        return size

    def append(self, item):
        """ append item to model """
        if item.exists():
            try:
                _, _ = get_recent_comparisons().read(item.get_uri())
                self.items.append(RecentListModelEntry(item))
            except (IOError, ValueError):
                pass

class RecentFilter(Gtk.Filter):
    """ recent list filter """

    filter_text = ""

    def __init__(self):
        Gtk.Filter.__init__(self)

    def set_filter_text(self, text):
        self.filter_text = text.lower()
        self.emit("changed", Gtk.FilterChange.DIFFERENT)

    def do_match(self, item):
        match = self.filter_text in item.item.get_display_name().lower()
        return match


@Gtk.Template(resource_path='/org/gnome/meld/ui/recent-selector.ui')
class RecentSelector(Gtk.Grid):

    __gtype_name__ = 'RecentSelector'

    @GObject.Signal(
        flags=(
            GObject.SignalFlags.RUN_FIRST |
            GObject.SignalFlags.ACTION
        ),
        arg_types=(str,),
    )
    def open_recent(self, uri: str) -> None:
        ...

    recent_chooser = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    open_button = Gtk.Template.Child()

    model = None
    filter_model = None
    filter = None

    def do_realize(self):
        self.filter_text = ''
        self.recent_manager = Gtk.RecentManager.get_default()
        items = self.recent_manager.get_items()
        self.model = RecentListModel()
        self.filter = RecentFilter()
        self.filter_model = Gtk.FilterListModel()
        self.filter_model.set_filter(self.filter)
        self.filter_model.set_model(self.model)

        for item in items:
            self.model.append(item)
        self.recent_chooser.bind_model(self.filter_model, self.create_widget)

        self.filter.emit("changed", Gtk.FilterChange.DIFFERENT)

        return Gtk.Grid.do_realize(self)

    def create_widget(self, item):
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_label(item.item.get_display_name())
        return label

    @Gtk.Template.Callback()
    def on_filter_text_changed(self, *args):
        self.filter.set_filter_text(self.search_entry.get_text())

    @Gtk.Template.Callback()
    def on_selection_changed(self, _widget, row):
        self.open_button.set_sensitive(row is not None)

    @Gtk.Template.Callback()
    def on_row_activate(self, _widget, row):
        item = self.model.do_get_item(row.get_index())
        self.open_recent.emit(item.item.get_uri())
        self.get_parent().get_parent().popdown()

    @Gtk.Template.Callback()
    def on_activate(self, _button):
        row = self.recent_chooser.get_selected_row()
        item = self.model.do_get_item(row.get_index())
        self.open_recent.emit(item.item.get_uri())
        self.get_parent().get_parent().popdown()
