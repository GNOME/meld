# Copyright (C) 2019, 2024 Kai Willadsen <kai.willadsen@gmail.com>
# Copyright (C) 2023 Philipp Unger <philipp.unger.1988@gmail.com>
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
    """An entry in the recent list model derived from a Gtk.RecentInfo"""

    display_name = GObject.Property(type=str, default="")
    uri = GObject.Property(type=str, default="")

    @classmethod
    def from_recent_info(cls, recent_info: Gtk.RecentInfo):
        return cls(
            display_name=recent_info.get_display_name(),
            uri=recent_info.get_uri(),
        )


@Gtk.Template(resource_path="/org/gnome/meld/ui/recent-selector.ui")
class RecentSelector(Gtk.Grid):
    __gtype_name__ = "RecentSelector"

    @GObject.Signal(
        flags=(GObject.SignalFlags.RUN_FIRST | GObject.SignalFlags.ACTION),
        arg_types=(str,),
    )
    def open_recent(self, uri: str) -> None: ...

    recent_chooser = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    open_button = Gtk.Template.Child()

    model: Gio.ListStore
    model_filter: Gtk.StringFilter
    filter_model: Gtk.FilterListModel

    def do_realize(self):
        self.model = Gio.ListStore()
        self.model_filter = Gtk.StringFilter(
            expression=Gtk.PropertyExpression.new(
                RecentListModelEntry, None, "display_name"
            )
        )
        self.search_entry.bind_property("text", self.model_filter, "search")
        self.filter_model = Gtk.FilterListModel(
            filter=self.model_filter,
            model=self.model,
        )

        self.recent_manager = Gtk.RecentManager.get_default()
        self.recent_manager.connect("changed", self.update_model)
        self.update_model()

        def make_recent_entry_label(item):
            return Gtk.Label(halign=Gtk.Align.START, label=item.display_name)

        self.recent_chooser.bind_model(self.filter_model, make_recent_entry_label)

        return Gtk.Grid.do_realize(self)

    def update_model(self, *args):
        self.model.remove_all()

        items = [item for item in self.recent_manager.get_items() if item.exists()]
        for item in items:
            try:
                # We're only checking that we can read this item as validation
                get_recent_comparisons().read(item.get_uri())
                self.model.append(RecentListModelEntry.from_recent_info(item))
            except (IOError, ValueError):
                pass

    @Gtk.Template.Callback()
    def on_selection_changed(self, _widget, row):
        self.open_button.set_sensitive(row is not None)

    def activate_row(self, row):
        item = self.model.get_item(row.get_index())
        self.open_recent.emit(item.uri)
        self.get_parent().get_parent().popdown()

    @Gtk.Template.Callback()
    def on_row_activate(self, _widget, row):
        self.activate_row(row)

    @Gtk.Template.Callback()
    def on_open_clicked(self, _button):
        row = self.recent_chooser.get_selected_row()
        self.activate_row(row)
