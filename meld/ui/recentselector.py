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


from gi.repository import GObject, Gtk

from meld.recent import RecentFiles


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

    def do_realize(self):
        self.filter_text = ''
        self.recent_chooser.set_filter(self.make_recent_filter())

        return Gtk.Grid.do_realize(self)

    def custom_recent_filter_func(
            self, filter_info: Gtk.RecentFilterInfo) -> bool:
        """Filter function for Meld-specific files

        Normal GTK recent filter rules are all OR-ed together to check
        whether an entry should be shown. This filter instead only ever
        shows Meld-specific entries, and then filters down from there.
        """

        if filter_info.mime_type != RecentFiles.mime_type:
            return False

        if self.filter_text not in filter_info.display_name.lower():
            return False

        return True

    def make_recent_filter(self) -> Gtk.RecentFilter:
        recent_filter = Gtk.RecentFilter()
        recent_filter.add_custom(
            (
                Gtk.RecentFilterFlags.MIME_TYPE |
                Gtk.RecentFilterFlags.DISPLAY_NAME
            ),
            self.custom_recent_filter_func,
        )
        return recent_filter

    @Gtk.Template.Callback()
    def on_filter_text_changed(self, *args):
        self.filter_text = self.search_entry.get_text().lower()

        # This feels unnecessary, but there's no other good way to get
        # the RecentChooser to re-evaluate the filter.
        self.recent_chooser.set_filter(self.make_recent_filter())

    @Gtk.Template.Callback()
    def on_selection_changed(self, *args):
        have_selection = bool(self.recent_chooser.get_current_uri())
        self.open_button.set_sensitive(have_selection)

    @Gtk.Template.Callback()
    def on_activate(self, *args):
        uri = self.recent_chooser.get_current_uri()
        if uri:
            self.open_recent.emit(uri)

        self.get_parent().popdown()
