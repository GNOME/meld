### Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2010-2011 Kai Willadsen <kai.willadsen@gmail.com>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
### USA.

from gettext import gettext as _

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

from . import filters
from .ui import gnomeglade
from .ui import listwidget
from .util import prefs

from meld.settings import settings


TIMESTAMP_RESOLUTION_PRESETS = [('1ns (ext4)', 1),
                                ('100ns (NTFS)', 100),
                                ('1s (ext2/ext3)', 1000000000),
                                ('2s (VFAT)', 2000000000)]


class FilterList(listwidget.ListWidget):

    def __init__(self, key, filter_type):
        default_entry = [_("label"), False, _("pattern"), True]
        listwidget.ListWidget.__init__(self, "EditableList.ui",
                                       "list_alignment", ["EditableListStore"],
                                       "EditableList", default_entry)
        self.key = key
        self.filter_type = filter_type

        self.pattern_column.set_cell_data_func(self.validity_renderer,
                                               self.valid_icon_celldata)

        for filter_params in settings.get_value(self.key):
            filt = filters.FilterEntry.new_from_gsetting(filter_params, filter_type)
            if filt is None:
                continue
            valid = filt.filter is not None
            self.model.append([filt.label, filt.active,
                               filt.filter_string, valid])

        for signal in ('row-changed', 'row-deleted', 'row-inserted',
                       'rows-reordered'):
            self.model.connect(signal, self._update_filter_string)

        self._update_sensitivity()

    def valid_icon_celldata(self, col, cell, model, it, user_data=None):
        is_valid = model.get_value(it, 3)
        icon_name = "gtk-dialog-warning" if not is_valid else None
        cell.set_property("stock-id", icon_name)

    def on_name_edited(self, ren, path, text):
        self.model[path][0] = text

    def on_cellrenderertoggle_toggled(self, ren, path):
        self.model[path][1] = not ren.get_active()

    def on_pattern_edited(self, ren, path, text):
        filt = filters.FilterEntry.compile_filter(text, self.filter_type)
        valid = filt is not None
        self.model[path][2] = text
        self.model[path][3] = valid

    def _update_filter_string(self, *args):
        value = [(row[0], row[1], row[2]) for row in self.model]
        settings.set_value(self.key, GLib.Variant('a(sbs)', value))


class ColumnList(listwidget.ListWidget):

    available_columns = set((
        "size",
        "modification time",
        "permissions",
    ))

    def __init__(self, key):
        listwidget.ListWidget.__init__(self, "EditableList.ui",
                                       "columns_ta", ["ColumnsListStore"],
                                       "columns_treeview")
        self.key = key

        # Unwrap the variant
        prefs_columns = [(k, v) for k, v in settings.get_value(self.key)]
        missing = self.available_columns - set([c[0] for c in prefs_columns])
        prefs_columns.extend([(m, False) for m in missing])
        for column_name, visibility in prefs_columns:
            self.model.append([visibility, _(column_name.capitalize())])

        for signal in ('row-changed', 'row-deleted', 'row-inserted',
                       'rows-reordered'):
            self.model.connect(signal, self._update_columns)

        self._update_sensitivity()

    def on_cellrenderertoggle_toggled(self, ren, path):
        self.model[path][0] = not ren.get_active()

    def _update_columns(self, *args):
        value = [(c[1].lower(), c[0]) for c in self.model]
        settings.set_value(self.key, GLib.Variant('a(sb)', value))


class GSettingsComboBox(Gtk.ComboBox):

    def __init__(self):
        Gtk.ComboBox.__init__(self)
        self.connect('notify::gsettings-value', self._setting_changed)
        self.connect('notify::active', self._active_changed)

    def bind_to(self, key):
        settings.bind(
            key, self, 'gsettings-value', Gio.SettingsBindFlags.DEFAULT)

    def _setting_changed(self, obj, val):
        column = self.get_property('gsettings-column')
        value = self.get_property('gsettings-value')

        for row in self.get_model():
            if value == row[column]:
                idx = row.path[0]
                break
        else:
            idx = 0

        if self.get_property('active') != idx:
            self.set_property('active', idx)

    def _active_changed(self, obj, val):
        column = self.get_property('gsettings-column')
        value = self.get_model()[self.get_active_iter()][column]
        self.set_property('gsettings-value', value)


class GSettingsIntComboBox(GSettingsComboBox):

    __gtype_name__ = "GSettingsIntComboBox"

    gsettings_column = GObject.property(type=int, default=1)
    gsettings_value = GObject.property(type=int)


class PreferencesDialog(gnomeglade.Component):

    def __init__(self, parent, prefs):
        gnomeglade.Component.__init__(self, "preferences.ui",
                                      "preferencesdialog",
                                      ["adjustment1", "adjustment2", "fileorderstore",
                                       "sizegroup_editor"])
        self.widget.set_transient_for(parent)
        self.prefs = prefs

        bindings = [
            ('use-system-font', self.checkbutton_default_font, 'active'),
            ('custom-font', self.fontpicker, 'font'),
            ('indent-width', self.spinbutton_tabsize, 'value'),
            ('insert-spaces-instead-of-tabs', self.checkbutton_spaces_instead_of_tabs, 'active'),
            ('highlight-current-line', self.checkbutton_highlight_current_line, 'active'),
            ('show-line-numbers', self.checkbutton_show_line_numbers, 'active'),
            ('highlight-syntax', self.checkbutton_use_syntax_highlighting, 'active'),
            ('use-system-editor', self.system_editor_checkbutton, 'active'),
            ('custom-editor-command', self.custom_edit_command_entry, 'text'),
            ('folder-shallow-comparison', self.checkbutton_shallow_compare, 'active'),
            ('folder-ignore-symlinks', self.checkbutton_ignore_symlinks, 'active'),
            ('vc-show-commit-margin', self.checkbutton_show_commit_margin, 'active'),
            ('vc-commit-margin', self.spinbutton_commit_margin, 'value'),
            ('vc-break-commit-message', self.checkbutton_break_commit_lines, 'active'),
            # Sensitivity bindings must come after value bindings, or the key
            # writability in gsettings overrides manual sensitivity setting.
            ('vc-show-commit-margin', self.spinbutton_commit_margin, 'sensitive'),
            ('vc-show-commit-margin', self.checkbutton_break_commit_lines, 'sensitive'),
        ]
        for key, obj, attribute in bindings:
            settings.bind(key, obj, attribute, Gio.SettingsBindFlags.DEFAULT)

        settings.bind(
            'use-system-editor', self.custom_edit_command_entry, 'sensitive',
            Gio.SettingsBindFlags.DEFAULT | Gio.SettingsBindFlags.INVERT_BOOLEAN)
        settings.bind(
            'use-system-font', self.fontpicker, 'sensitive',
            Gio.SettingsBindFlags.DEFAULT | Gio.SettingsBindFlags.INVERT_BOOLEAN)

        # TODO: Fix once bind_with_mapping is available
        self.checkbutton_show_whitespace.set_active(
            bool(settings.get_flags('draw-spaces')))
        # TODO: This doesn't restore the state of character wrapping when word
        # wrapping is disabled, but this is hard with our existing gconf keys
        if self.prefs.edit_wrap_lines != Gtk.WrapMode.NONE:
            if self.prefs.edit_wrap_lines == Gtk.WrapMode.CHAR:
                self.checkbutton_split_words.set_active(False)
            self.checkbutton_wrap_text.set_active(True)

        # file filters
        self.filefilter = FilterList("filename-filters", filters.FilterEntry.SHELL)
        self.file_filters_tab.pack_start(self.filefilter.widget, True, True, 0)

        # text filters
        self.textfilter = FilterList("text-filters", filters.FilterEntry.REGEX)
        self.text_filters_tab.pack_start(self.textfilter.widget, True, True, 0)
        self.checkbutton_ignore_blank_lines.set_active( self.prefs.ignore_blank_lines )
        # encoding
        self.entry_text_codecs.set_text( self.prefs.text_codecs )

        columnlist = ColumnList("folder-columns")
        self.column_list_vbox.pack_start(columnlist.widget, True, True, 0)

        model = Gtk.ListStore(str, int)
        for i, entry in enumerate(TIMESTAMP_RESOLUTION_PRESETS):
            model.append(entry)
        # FIXME: This should all be in the glade
        self.combo_timestamp.set_model(model)
        cell = Gtk.CellRendererText()
        self.combo_timestamp.pack_start(cell, False)
        self.combo_timestamp.add_attribute(cell, 'text', 0)
        self.combo_timestamp.bind_to('folder-time-resolution')

        self.combo_file_order.set_active(
            1 if self.prefs.vc_left_is_local else 0)


        self.widget.show()

    def on_checkbutton_wrap_text_toggled(self, button):
        if not self.checkbutton_wrap_text.get_active():
            self.prefs.edit_wrap_lines = 0
            self.checkbutton_split_words.set_sensitive(False)
        else:
            self.checkbutton_split_words.set_sensitive(True)
            if self.checkbutton_split_words.get_active():
                self.prefs.edit_wrap_lines = 2
            else:
                self.prefs.edit_wrap_lines = 1

    def on_checkbutton_show_whitespace_toggled(self, widget):
        value = GtkSource.DrawSpacesFlags.ALL if widget.get_active() else 0
        settings.set_flags('draw-spaces', value)

    def on_checkbutton_ignore_blank_lines_toggled(self, check):
        self.prefs.ignore_blank_lines = check.get_active()

    def on_entry_text_codecs_activate(self, entry, *args):
        # Called on "activate" and "focus-out-event"
        self.prefs.text_codecs = entry.props.text

    def on_combo_file_order_changed(self, combo):
        file_order = combo.get_model()[combo.get_active_iter()][0]
        self.prefs.vc_left_is_local = True if file_order else False

    def on_response(self, dialog, response_id):
        self.widget.destroy()


class MeldPreferences(prefs.Preferences):
    defaults = {
        "window_size_x": prefs.Value(prefs.INT, 600),
        "window_size_y": prefs.Value(prefs.INT, 600),
        "edit_wrap_lines" : prefs.Value(prefs.INT, 0),
        "text_codecs": prefs.Value(prefs.STRING, "utf8 latin1"),
        "vc_console_visible": prefs.Value(prefs.BOOL, 0),
        "ignore_blank_lines" : prefs.Value(prefs.BOOL, False),
        "vc_left_is_local": prefs.Value(prefs.BOOL, False),
    }

    def __init__(self):
        super(MeldPreferences, self).__init__("/apps/meld", self.defaults)
