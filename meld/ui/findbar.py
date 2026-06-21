# Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2012-2026 Kai Willadsen <kai.willadsen@gmail.com>
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

from typing import Any, ClassVar

from gi.repository import GObject, Gtk, GtkSource

from meld.signalhelpers import block_signal_handlers
from meld.ui.gtkutil import GTK_STYLE_CLASS_ERROR


@Gtk.Template(resource_path="/org/gnome/meld/ui/findbar.ui")
class FindBar(Gtk.Grid):
    __gtype_name__ = "FindBar"

    find_entry = Gtk.Template.Child()
    find_next_button = Gtk.Template.Child()
    find_previous_button = Gtk.Template.Child()
    match_case = Gtk.Template.Child()
    regex = Gtk.Template.Child()
    replace_all_button = Gtk.Template.Child()
    replace_button = Gtk.Template.Child()
    replace_entry = Gtk.Template.Child()
    whole_word = Gtk.Template.Child()
    wrap_box = Gtk.Template.Child()

    replace_mode = GObject.Property(type=bool, default=False)
    _cached_search: ClassVar[str | None] = None

    @GObject.Signal(
        name="activate-secondary",
        flags=(GObject.SignalFlags.RUN_FIRST | GObject.SignalFlags.ACTION),
    )
    def activate_secondary(self) -> None:
        self._find_text(backwards=True)

    def __init__(self):
        super().__init__()

        # Track all textviews for highlighting, and the current textview for
        # search tracking
        self.textviews = []
        self.textview = None
        self.search_contexts = {}
        self.search_context = None
        self.notify_id = None

        # Create and bind our GtkSourceSearchSettings
        settings = GtkSource.SearchSettings()
        self.match_case.bind_property("active", settings, "case-sensitive")
        self.whole_word.bind_property("active", settings, "at-word-boundaries")
        self.regex.bind_property("active", settings, "regex-enabled")
        self.find_entry.bind_property("text", settings, "search-text")
        settings.set_wrap_around(True)
        self.search_settings = settings

        # Bind visibility and layout for find-and-replace mode
        self.bind_property("replace_mode", self.replace_entry, "visible")
        self.bind_property("replace_mode", self.replace_all_button, "visible")
        self.bind_property("replace_mode", self.replace_button, "visible")
        self.bind_property(
            "replace_mode",
            self,
            "row-spacing",
            GObject.BindingFlags.DEFAULT,
            lambda binding, replace_mode: 6 if replace_mode else 0,
        )

    def hide(self) -> None:
        self.search_context.disconnect(self.notify_id)
        self.textview = None
        self.search_context = None
        self.wrap_box.set_visible(False)
        Gtk.Widget.hide(self)

    def update_match_state(self, *args: Any) -> None:
        # We only show an error state for the active pane results, even if
        # there are matches in other panes. Also, an occurrences_count of -1
        # implies that the search is still running.
        no_matches = (
            self.search_context
            and self.search_context.props.occurrences_count == 0
            and self.search_settings.props.search_text
        )
        if no_matches:
            self.find_entry.add_css_class(GTK_STYLE_CLASS_ERROR)
        else:
            self.find_entry.remove_css_class(GTK_STYLE_CLASS_ERROR)

    def set_text_views(self, textviews: list[Gtk.TextView]) -> None:
        self.textviews = list(textviews)
        self.search_contexts = {}

        for textview in self.textviews:
            context = GtkSource.SearchContext.new(
                textview.get_buffer(), self.search_settings
            )
            context.set_highlight(True)
            self.search_contexts[textview] = context

    def set_text_view(self, textview: Gtk.TextView) -> None:
        """Set the active textview that find/replace acts on"""
        self.textview = textview
        self.search_context = self.search_contexts.get(textview)
        self.notify_id = self.search_context.connect(
            "notify::occurrences-count", self.update_match_state
        )
        self.update_match_state()

    def start_find(self, *, textview: Gtk.TextView, replace: bool, text: str) -> None:
        self.replace_mode = replace
        self.set_text_view(textview)

        prefilled_text = text or FindBar._cached_search
        if prefilled_text:
            # Setting the text triggers GtkSearchEntry "changed" handlers which
            # end up deselecting our entry text that we select below.
            with block_signal_handlers(
                self.find_entry.get_delegate(),
                signal_id=GObject.signal_lookup("changed", Gtk.Text),
            ):
                self.find_entry.set_text(prefilled_text)
            self.find_entry.select_region(0, -1)
            FindBar._cached_search = prefilled_text

        self.show()
        self.find_entry.grab_focus()

    def start_find_next(self, textview: Gtk.TextView) -> None:
        self.set_text_view(textview)
        self._find_text()

    def start_find_previous(self, textview: Gtk.TextView) -> None:
        self.set_text_view(textview)
        self._find_text(backwards=True)

    @Gtk.Template.Callback()
    def on_find_next_button_clicked(self, button: Gtk.Button) -> None:
        self._find_text()

    @Gtk.Template.Callback()
    def on_find_previous_button_clicked(self, button: Gtk.Button) -> None:
        self._find_text(backwards=True)

    @Gtk.Template.Callback()
    def on_replace_button_clicked(self, widget: Gtk.Widget) -> None:
        buf = self.textview.get_buffer()
        oldsel = buf.get_selection_bounds()
        match = self._find_text(0)
        newsel = buf.get_selection_bounds()
        # Only replace if there is an already-selected match at the cursor
        if (
            match
            and oldsel
            and oldsel[0].equal(newsel[0])
            and oldsel[1].equal(newsel[1])
        ):
            self.search_context.replace(
                newsel[0], newsel[1], self.replace_entry.get_text(), -1
            )
            self._find_text(0)

    @Gtk.Template.Callback()
    def on_replace_all_button_clicked(self, button: Gtk.Button) -> None:
        buf = self.textview.get_buffer()
        saved_insert = buf.create_mark(
            None, buf.get_iter_at_mark(buf.get_insert()), True
        )
        self.search_context.replace_all(self.replace_entry.get_text(), -1)
        if not saved_insert.get_deleted():
            buf.place_cursor(buf.get_iter_at_mark(saved_insert))
            self.textview.scroll_to_mark(buf.get_insert(), 0.25, True, 0.5, 0.5)

    @Gtk.Template.Callback()
    def on_toggle_replace_button_clicked(self, button: Gtk.Button) -> None:
        self.replace_mode = not self.replace_mode

    @Gtk.Template.Callback()
    def on_find_entry_changed(self, search_entry: Gtk.SearchEntry) -> None:
        FindBar._cached_search = search_entry.get_text()
        self._find_text(0)

    @Gtk.Template.Callback()
    def on_stop_search(self, search_entry: Gtk.SearchEntry) -> None:
        self.hide()

    def _find_text(self, start_offset: int = 1, backwards: bool = False) -> bool:
        if not self.textview or not self.search_context:
            return False

        buf = self.textview.get_buffer()
        insert = buf.get_iter_at_mark(buf.get_insert())

        start, end = buf.get_bounds()
        self.wrap_box.set_visible(False)
        if not backwards:
            insert.forward_chars(start_offset)
            match, start, end, wrapped = self.search_context.forward(insert)
        else:
            match, start, end, wrapped = self.search_context.backward(insert)

        if match:
            self.wrap_box.set_visible(wrapped)
            buf.place_cursor(start)
            buf.move_mark(buf.get_selection_bound(), end)
            self.textview.scroll_to_mark(buf.get_insert(), 0.25, True, 0.5, 0.5)
            return True
        else:
            buf.place_cursor(buf.get_iter_at_mark(buf.get_insert()))
            self.wrap_box.set_visible(False)
            return False


FindBar.set_css_name("meld-find-bar")
