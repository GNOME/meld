import json

from gi.repository import Gio, GLib, GObject, Gtk, Peas

from meld.conf import _
from meld.filediff import FileDiff
from meld.pluginmanager import PluginMenu


class FormatJSON(GObject.Object, Peas.Activatable):
    __gtype_name__ = "FormatJSON"

    object = GObject.Property(type=GObject.Object)

    def do_activate(self):
        self.api = self.object
        self._comparison_created_signal = self.api.app.connect(
            "comparison-created", self.on_comparison_created
        )

        item = Gio.MenuItem.new(
            label=_("Format JSON"),
            detailed_action="view.format-json(-1)",
        )
        self.api.add_menu_item(PluginMenu.app_comparison, "format-json", item)

    def do_deactivate(self):
        self.api.app.disconnect(self._comparison_created_signal)
        self.api.remove_menu_item(PluginMenu.app_comparison, "format-json")

    def on_comparison_created(self, app, window, page):
        if not isinstance(page, FileDiff):
            return

        action = Gio.SimpleAction.new("format-json", GLib.VariantType.new("i"))
        action.connect("activate", self.format_json, page)
        page.view_action_group.add_action(action)

        self.api.add_pane_action_button(page, "Format as JSON", "view.format-json")

    def format_json(self, action, params: GLib.Variant, filediff):
        pane = params.get_int32()
        if pane == -1:
            pane = filediff._get_focused_pane()
        if pane == -1:
            return

        buf = filediff.textbuffer[pane]
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

        try:
            text = json.dumps(json.loads(text), indent=2)
        except ValueError:
            # TODO: Make this a toast once we are using libadwaita
            dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text=_("Couldn't parse this file as JSON"),
            )
            dialog.run()
            dialog.destroy()
            return

        buf.set_text(text)
        filediff.refresh_comparison()
