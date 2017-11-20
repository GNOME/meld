# Copyright (C) 2012-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource
from gi.repository import Pango

from meld.ui.bufferselectors import EncodingSelector
from meld.ui.bufferselectors import SourceLangSelector


Gtk.rc_parse_string(
    """
    style "meld-statusbar-style" {
        GtkStatusbar::shadow-type = GTK_SHADOW_NONE
    }
    class "MeldStatusBar" style "meld-statusbar-style"
    """)


class MeldStatusMenuButton(Gtk.MenuButton):
    """Compact menu button with arrow indicator for use in a status bar

    Implementation based on gedit-status-menu-button.c
    Copyright (C) 2008 - Jesse van den Kieboom
    """

    __gtype_name__ = "MeldStatusMenuButton"

    style = b"""
    * {
      padding: 1px 8px 2px 4px;
      border: 0;
      outline-width: 0;
    }
    """

    css_provider = Gtk.CssProvider()
    css_provider.load_from_data(style)

    def get_label(self):
        return self._label.get_text()

    def set_label(self, markup):
        if markup == self._label.get_text():
            return
        self._label.set_markup(markup)

    label = GObject.property(
        type=str,
        nick="The GtkSourceLanguage displayed in the status bar",
        default=None,
        getter=get_label,
        setter=set_label,
    )

    def __init__(self):
        Gtk.MenuButton.__init__(self)

        style_context = self.get_style_context()
        style_context.add_provider(
            self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        style_context.add_class('flat')

        # Ideally this would be a template child, but there's still no
        # Python support for this.
        label = Gtk.Label()
        label.props.single_line_mode = True
        label.props.halign = Gtk.Align.START
        label.props.valign = Gtk.Align.BASELINE

        arrow = Gtk.Image.new_from_icon_name(
            'pan-down-symbolic', Gtk.IconSize.SMALL_TOOLBAR)
        arrow.props.valign = Gtk.Align.BASELINE

        box = Gtk.Box()
        box.set_spacing(3)
        box.add(label)
        box.add(arrow)
        box.show_all()

        self.remove(self.get_child())
        self.add(box)

        self._label = label


class MeldStatusBar(Gtk.Statusbar):
    __gtype_name__ = "MeldStatusBar"

    __gsignals__ = {
        'encoding-changed': (
            GObject.SignalFlags.RUN_FIRST, None, (GtkSource.Encoding,)),
    }

    source_encoding = GObject.property(
        type=GtkSource.Encoding,
        nick="The file encoding displayed in the status bar",
        default=None,
    )

    source_language = GObject.property(
        type=GtkSource.Language,
        nick="The GtkSourceLanguage displayed in the status bar",
        default=None,
    )

    def __init__(self):
        GObject.GObject.__init__(self)
        self.props.margin = 0
        self.props.spacing = 6

        hbox = self.get_message_area()
        label = hbox.get_children()[0]
        hbox.props.spacing = 6
        label.props.ellipsize = Pango.EllipsizeMode.NONE
        hbox.remove(label)
        hbox.pack_end(label, False, True, 0)

        alignment = Gtk.Alignment.new(
            xalign=1.0, yalign=0.5, xscale=1.0, yscale=1.0)
        self.info_box = Gtk.HBox(homogeneous=False, spacing=12)
        self.info_box.show()
        alignment.add(self.info_box)
        self.pack_end(alignment, False, True, 0)
        alignment.show()

        self.box_box = Gtk.HBox(homogeneous=False, spacing=6)
        self.pack_end(self.box_box, False, True, 0)
        self.box_box.pack_end(self.construct_highlighting_selector(), False, True, 0)
        self.box_box.pack_end(self.construct_encoding_selector(), False, True, 0)
        self.box_box.show_all()

    def construct_encoding_selector(self):
        def change_encoding(selector, encoding):
            self.props.source_encoding = encoding
            self.emit('encoding-changed', encoding)
            pop.hide()

        def set_initial_encoding(selector):
            selector.select_value(self.props.source_encoding)

        selector = EncodingSelector()
        selector.connect('encoding-selected', change_encoding)
        selector.connect('map', set_initial_encoding)

        pop = Gtk.Popover()
        pop.set_position(Gtk.PositionType.TOP)
        pop.add(selector)

        button = MeldStatusMenuButton()
        self.bind_property(
            'source-encoding', button, 'label', GObject.BindingFlags.DEFAULT,
            lambda binding, enc: selector.get_value_label(enc))
        button.set_popover(pop)
        button.show()

        return button

    def construct_highlighting_selector(self):
        def change_language(selector, lang):
            self.props.source_language = lang
            pop.hide()

        def set_initial_language(selector):
            selector.select_value(self.props.source_language)

        selector = SourceLangSelector()
        selector.connect('language-selected', change_language)
        selector.connect('map', set_initial_language)

        pop = Gtk.Popover()
        pop.set_position(Gtk.PositionType.TOP)
        pop.add(selector)

        button = MeldStatusMenuButton()
        self.bind_property(
            'source-language', button, 'label', GObject.BindingFlags.DEFAULT,
            lambda binding, enc: selector.get_value_label(enc))
        button.set_popover(pop)
        button.show()

        return button

    def set_info_box(self, widgets):
        for child in self.info_box.get_children():
            self.info_box.remove(child)
        for widget in widgets:
            self.info_box.pack_end(widget, False, True, 0)
