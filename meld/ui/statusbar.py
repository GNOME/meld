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

from meld.conf import _
from meld.ui.bufferselectors import EncodingSelector
from meld.ui.bufferselectors import SourceLangSelector


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

    label = GObject.Property(
        type=str,
        nick="The GtkSourceLanguage displayed in the status bar",
        default=None,
        getter=get_label,
        setter=set_label,
    )

    def __init__(self):
        super().__init__()

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
        'start-go-to-line': (
            GObject.SignalFlags.ACTION, None, tuple()),
        'go-to-line': (
            GObject.SignalFlags.RUN_FIRST, None, (int,)),
        'encoding-changed': (
            GObject.SignalFlags.RUN_FIRST, None, (GtkSource.Encoding,)),
    }

    cursor_position = GObject.Property(
        type=object,
        nick="The position of the cursor displayed in the status bar",
        default=None,
    )

    source_encoding = GObject.Property(
        type=GtkSource.Encoding,
        nick="The file encoding displayed in the status bar",
        default=None,
    )

    source_language = GObject.Property(
        type=GtkSource.Language,
        nick="The GtkSourceLanguage displayed in the status bar",
        default=None,
    )

    # Abbreviation for line, column so that it will fit in the status bar
    _line_column_text = _("Ln %i, Col %i")

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

        self.box_box = Gtk.HBox(homogeneous=False, spacing=6)
        self.pack_end(self.box_box, False, True, 0)
        self.box_box.pack_end(
            self.construct_line_display(), False, True, 0)
        self.box_box.pack_end(
            self.construct_highlighting_selector(), False, True, 0)
        self.box_box.pack_end(
            self.construct_encoding_selector(), False, True, 0)
        self.box_box.show_all()

    def construct_line_display(self):

        # Note that we're receiving one-based line numbers from the
        # user and storing and emitting zero-base line numbers.

        def go_to_line_text(text):
            try:
                line = int(text)
            except ValueError:
                return
            self.emit('go-to-line', max(0, line - 1))

        def line_entry_mapped(entry):
            line, offset = self.props.cursor_position
            entry.set_text(str(line + 1))

        def line_entry_insert_text(entry, new_text, length, position):
            if not new_text.isdigit():
                GObject.signal_stop_emission_by_name(entry, 'insert-text')
                return

        def line_entry_changed(entry):
            go_to_line_text(entry.get_text())

        def line_entry_activated(entry):
            go_to_line_text(entry.get_text())
            pop.popdown()

        entry = Gtk.Entry()
        entry.set_tooltip_text(_('Line you want to move the cursor to'))
        entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.PRIMARY, 'go-jump-symbolic')
        entry.set_icon_activatable(Gtk.EntryIconPosition.PRIMARY, False)
        entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        entry.connect('map', line_entry_mapped)
        entry.connect('insert-text', line_entry_insert_text)
        entry.connect('changed', line_entry_changed)
        entry.connect('activate', line_entry_activated)

        selector = Gtk.Grid()
        selector.set_border_width(6)
        selector.add(entry)
        selector.show_all()

        pop = Gtk.Popover()
        pop.set_position(Gtk.PositionType.TOP)
        pop.add(selector)

        def format_cursor_position(binding, cursor):
            line, offset = cursor
            return self._line_column_text % (line + 1, offset + 1)

        button = MeldStatusMenuButton()
        self.bind_property(
            'cursor_position', button, 'label', GObject.BindingFlags.DEFAULT,
            format_cursor_position)
        self.connect('start-go-to-line', lambda *args: button.clicked())
        button.set_popover(pop)
        button.show()

        return button

    def construct_encoding_selector(self):
        def change_encoding(selector, encoding):
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
            # TODO: Our other GObject properties are expected to be
            # updated through a bound state from our parent. This is
            # the only place where we assign to them instead of
            # emitting a signal, and it makes the class logic as a
            # whole kind of confusing.
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
