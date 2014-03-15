# Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2008-2009, 2013 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import Gtk
from gi.repository import Pango

from meld.conf import _


class NotebookLabel(Gtk.HBox):
    __gtype_name__ = "NotebookLabel"

    css = """
    * {
        -GtkButton-default-border : 0;
        -GtkButton-default-outside-border : 0;
        -GtkButton-inner-border: 0;
        -GtkWidget-focus-line-width : 0;
        -GtkWidget-focus-padding : 0;
        padding : 0;
    }
    """
    tab_width_in_chars = 30

    def __init__(self, iconname, text, onclose):
        Gtk.HBox.__init__(self, homogeneous=False, spacing=4)

        label = Gtk.Label(label=text)
        # FIXME: ideally, we would use custom ellipsization that ellipsized the
        # two paths separately, but that requires significant changes to label
        # generation in many different parts of the code
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        label.set_single_line_mode(True)
        label.set_alignment(0.0, 0.5)
        label.set_padding(0, 0)

        context = self.get_pango_context()
        font_desc = self.get_style_context().get_font(Gtk.StateFlags.NORMAL)
        metrics = context.get_metrics(font_desc, context.get_language())
        char_width = metrics.get_approximate_char_width() / Pango.SCALE
        valid, w, h = Gtk.icon_size_lookup_for_settings(self.get_settings(), Gtk.IconSize.MENU)
        # FIXME: PIXELS replacement
        self.set_size_request(self.tab_width_in_chars * char_width + 2 * w, -1)

        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_focus_on_click(False)
        icon = Gio.ThemedIcon.new_with_default_fallbacks('window-close-symbolic')
        image = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.MENU)
        image.set_tooltip_text(_("Close tab"))
        button.add(image)
        button.set_name("meld-tab-close-button")
        button.connect("clicked", onclose)

        context = button.get_style_context()
        provider = Gtk.CssProvider()
        provider.load_from_data(self.css)
        context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        icon = Gtk.Image.new_from_icon_name(iconname, Gtk.IconSize.MENU)

        label_box = Gtk.EventBox()
        label_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        label_box.props.visible_window = False
        label_box.connect("button-press-event", self.on_label_clicked)
        label_box.add(label)

        self.pack_start(icon, False, True, 0)
        self.pack_start(label_box, True, True, 0)
        self.pack_start(button, False, True, 0)
        self.set_tooltip_text(text)
        self.show_all()

        self.__label = label
        self.__onclose = onclose

    def on_label_clicked(self, box, event):
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 2:
            self.__onclose(None)

    def get_label_text(self):
        return self.__label.get_text()

    def set_label_text(self, text):
        self.__label.set_text(text)
        self.set_tooltip_text(text)
