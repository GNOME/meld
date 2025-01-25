from gi.repository import Gio, GLib, GObject, Peas

from meld.conf import _
from meld.filediff import FileDiff
from meld.meldbuffer import newline_from_newline_type
from meld.pluginmanager import PluginMenu


class TextSortPlugin(GObject.Object, Peas.Activatable):
    __gtype_name__ = "TextSortPlugin"

    object = GObject.Property(type=GObject.Object)

    def do_activate(self):
        self.api = self.object
        self._comparison_created_signal = self.api.app.connect(
            "comparison-created", self.on_comparison_created
        )

        item = Gio.MenuItem.new(
            label=_("Sort Text"),
            detailed_action="view.sort-text(-1)",
        )
        self.api.add_menu_item(PluginMenu.app_comparison, "sort-text", item)

    def do_deactivate(self):
        self.api.app.disconnect(self._comparison_created_signal)
        self.api.remove_menu_item(PluginMenu.app_comparison, "sort-text")

    def on_comparison_created(self, app, window, page):
        if not isinstance(page, FileDiff):
            return

        action = Gio.SimpleAction.new("sort-text", GLib.VariantType.new("i"))
        action.connect("activate", self.sort_text, page)
        page.view_action_group.add_action(action)
        self.api.add_pane_action_button(page, "Sort Text", "view.sort-text")

    def sort_text(self, action, params: GLib.Variant, filediff):
        pane = params.get_int32()
        if pane == -1:
            pane = filediff._get_focused_pane()
        if pane == -1:
            return

        lines = filediff.buffer_texts[pane]
        buf = filediff.textbuffer[pane]
        newline_type = buf.data.sourcefile.get_newline_type()
        newline = newline_from_newline_type(newline_type)

        sorted_text = newline.join(sorted(lines))
        buf.set_text(sorted_text)
        filediff.refresh_comparison()
