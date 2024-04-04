# Copyright (C) 2015-2019 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import Gdk, Gio, GObject, Gtk

KEYBINDING_FLAGS = GObject.SignalFlags.RUN_LAST | GObject.SignalFlags.ACTION


class MeldNotebook(Gtk.Notebook):
    """Notebook subclass with tab switch and reordering behaviour

    MeldNotebook implements some fairly generic tab switching shortcuts
    and a popup menu for simple tab controls, as well as some
    Meld-specific tab label handling.
    """

    __gtype_name__ = "MeldNotebook"

    __gsignals__ = {
        'tab-switch': (KEYBINDING_FLAGS, None, (int,)),
        'page-label-changed': (0, None, (GObject.TYPE_STRING,)),
    }

    # Python 3.4; no bytes formatting
    css = (
        b"""
        @binding-set TabSwitchBindings {
          bind "<Alt>1" { "tab-switch" (0) };
          bind "<Alt>2" { "tab-switch" (1) };
          bind "<Alt>3" { "tab-switch" (2) };
          bind "<Alt>4" { "tab-switch" (3) };
          bind "<Alt>5" { "tab-switch" (4) };
          bind "<Alt>6" { "tab-switch" (5) };
          bind "<Alt>7" { "tab-switch" (6) };
          bind "<Alt>8" { "tab-switch" (7) };
          bind "<Alt>9" { "tab-switch" (8) };
          bind "<Alt>0" { "tab-switch" (9) };
        }
        notebook.meld-notebook { -gtk-key-bindings: TabSwitchBindings; }
        """
    )

    ui = """
      <?xml version="1.0" encoding="UTF-8"?>
      <interface>
        <menu id="tab-menu">
          <item>
            <attribute name="label" translatable="yes">Move _Left</attribute>
            <attribute name="action">popup.tabmoveleft</attribute>
          </item>
          <item>
            <attribute name="label" translatable="yes">Move _Right</attribute>
            <attribute name="action">popup.tabmoveright</attribute>
          </item>
          <item>
            <attribute name="label" translatable="yes">_Close</attribute>
            <attribute name="action">win.close</attribute>
          </item>
        </menu>
      </interface>
    """

    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.action_group = Gio.SimpleActionGroup()

        actions = (
            ("tabmoveleft", self.on_tab_move_left),
            ("tabmoveright", self.on_tab_move_right),
        )
        for (name, callback) in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.action_group.add_action(action)

        self.insert_action_group("popup", self.action_group)

        builder = Gtk.Builder.new_from_string(self.ui, -1)
        self.popup_menu = builder.get_object("tab-menu")

        stylecontext = self.get_style_context()
        stylecontext.add_class('meld-notebook')

        self.connect('button-press-event', self.on_button_press_event)
        self.connect('popup-menu', self.on_popup_menu)
        self.connect('page-added', self.on_page_added)
        self.connect('page-removed', self.on_page_removed)

    def do_tab_switch(self, page_num):
        self.set_current_page(page_num)

    def on_popup_menu(self, widget, event=None):
        self.action_group.lookup_action("tabmoveleft").set_enabled(
            self.get_current_page() > 0)
        self.action_group.lookup_action("tabmoveright").set_enabled(
            self.get_current_page() < self.get_n_pages() - 1)

        popup = Gtk.Menu.new_from_model(self.popup_menu)
        popup.attach_to_widget(widget, None)
        popup.show_all()

        if event:
            popup.popup_at_pointer(event)
        else:
            popup.popup_at_widget(
                widget,
                Gdk.Gravity.NORTH_WEST,
                Gdk.Gravity.NORTH_WEST,
                event,
            )
        return True

    def on_button_press_event(self, widget, event):
        if (event.triggers_context_menu() and
                event.type == Gdk.EventType.BUTTON_PRESS):
            return self.on_popup_menu(widget, event)
        return False

    def on_tab_move_left(self, *args):
        page_num = self.get_current_page()
        child = self.get_nth_page(page_num)
        page_num = page_num - 1 if page_num > 0 else 0
        self.reorder_child(child, page_num)

    def on_tab_move_right(self, *args):
        page_num = self.get_current_page()
        child = self.get_nth_page(page_num)
        self.reorder_child(child, page_num + 1)

    def on_page_added(self, notebook, child, page_num, *args):
        child.connect("label-changed", self.on_label_changed)
        self.props.show_tabs = self.get_n_pages() > 1

    def on_page_removed(self, notebook, child, page_num, *args):
        child.disconnect_by_func(self.on_label_changed)
        self.props.show_tabs = self.get_n_pages() > 1

    def on_label_changed(self, page, text: str, tooltip: str) -> None:
        nbl = self.get_tab_label(page)
        nbl.props.label_text = text
        nbl.set_tooltip_text(tooltip)

        # Only update the window title if the current page is active
        if self.get_current_page() == self.page_num(page):
            self.emit('page-label-changed', text)
        self.child_set_property(page, "menu-label", text)
