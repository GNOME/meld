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

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource
from gi.repository import Pango

from meld.conf import _, ui_file


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
        self.box_box.show_all()

    def construct_highlighting_selector(self):
        def change_language(selector, lang):
            self.props.source_language = lang
            pop.hide()

        def set_initial_language(selector):
            selector.select_language(self.props.source_language)

        selector = HighlightModeSelector()
        selector.connect('language-selected', change_language)
        selector.connect('map', set_initial_language)

        pop = Gtk.Popover()
        pop.set_position(Gtk.PositionType.TOP)
        pop.add(selector)

        def get_language_label(binding, language, *args):
            if not language:
                return _("Plain Text")
            return language.get_name()

        button = MeldStatusMenuButton()
        self.bind_property(
            'source-language', button, 'label', GObject.BindingFlags.DEFAULT,
            get_language_label)
        button.set_popover(pop)
        button.show()

        return button

    def set_info_box(self, widgets):
        for child in self.info_box.get_children():
            self.info_box.remove(child)
        for widget in widgets:
            self.info_box.pack_end(widget, False, True, 0)


class TemplateHackMixin(object):

    def get_template_child(self, widget_type, name):
        # Taken from an in-progress patch on bgo#701843

        def get_template_child(widget, widget_type, name):
            # Explicitly use gtk_buildable_get_name() because it is masked by
            # gtk_widget_get_name() in GI.
            if isinstance(widget, widget_type) and \
                    isinstance(widget, Gtk.Buildable) and \
                    Gtk.Buildable.get_name(widget) == name:
                return widget

            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    result = get_template_child(child, widget_type, name)
                    if result is not None:
                        return result

        return get_template_child(self, widget_type, name)


# HighlightModeSelector was copied and translated to Python from gedit
# Copyright (C) 2013 - Ignacio Casal Quinteiro
# Python translation and adaptations
# Copyright (C) 2015 Kai Willadsen <kai.willadsen@gmail.com>


class HighlightModeSelector(TemplateHackMixin, Gtk.Grid):

    __gtype_name__ = "HighlightModeSelector"

    __gsignals__ = {
        'language-selected': (
            GObject.SignalFlags.RUN_FIRST | GObject.SignalFlags.ACTION,
            None, (GtkSource.Language,)),
    }

    NAME_COLUMN, LANG_COLUMN = 0, 1

    def __init__(self):
        Gtk.Grid.__init__(self)
        self.init_template()

        self.entry = self.get_template_child(Gtk.SearchEntry, 'entry')
        self.treeview = self.get_template_child(Gtk.TreeView, 'treeview')
        self.treeview_selection = self.treeview.get_selection()
        # FIXME: Should be able to access as a template child, but can't.
        self.listfilter = self.treeview.get_model()
        self.liststore = self.listfilter.get_model()

        self.liststore.append((_("Plain Text"), None))
        manager = GtkSource.LanguageManager.get_default()
        for lang_id in manager.get_language_ids():
            lang = manager.get_language(lang_id)
            self.liststore.append((lang.get_name(), lang))

        self.filter_string = ''
        self.entry.connect('changed', self.on_entry_changed)
        self.listfilter.set_visible_func(self.lang_name_filter)

        self.entry.connect('activate', self.on_activate)
        self.treeview.connect('row-activated', self.on_activate)

    def select_language(self, language):
        if not language:
            return

        for row in self.liststore:
            row_lang = row[self.LANG_COLUMN]
            if row_lang and row_lang.get_id() != language.get_id():
                continue
            self.treeview_selection.select_path(row.path)
            self.treeview.scroll_to_cell(row.path, None, True, 0.5, 0)

    def lang_name_filter(self, model, it, *args):
        if not self.filter_string:
            return True
        lang_name = model.get_value(it, self.NAME_COLUMN).lower()
        return self.filter_string.lower() in lang_name

    def on_entry_changed(self, entry):
        self.filter_string = entry.get_text()
        self.listfilter.refilter()
        first = self.listfilter.get_iter_first()
        if first:
            self.treeview_selection.select_iter(first)

    def on_activate(self, *args):
        model, it = self.treeview_selection.get_selected()
        if not it:
            return
        lang = model.get_value(it, self.LANG_COLUMN)
        self.emit('language-selected', lang)


template = open(ui_file('gedit-highlight-mode-selector.ui'), 'rb').read()
template_bytes = GLib.Bytes.new(template)
HighlightModeSelector.set_template(template_bytes)
