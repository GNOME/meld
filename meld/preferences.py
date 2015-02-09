# Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.conf import _
from meld.filters import FilterEntry
from meld.settings import settings
from meld.ui.gnomeglade import Component
from meld.ui.listwidget import ListWidget


class FilterList(ListWidget):

    def __init__(self, key, filter_type):
        default_entry = [_("label"), False, _("pattern"), True]
        ListWidget.__init__(self, "EditableList.ui",
                            "list_vbox", ["EditableListStore"],
                            "EditableList", default_entry)
        self.key = key
        self.filter_type = filter_type

        self.pattern_column.set_cell_data_func(self.validity_renderer,
                                               self.valid_icon_celldata)

        for filter_params in settings.get_value(self.key):
            filt = FilterEntry.new_from_gsetting(filter_params, filter_type)
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
        filt = FilterEntry.compile_filter(text, self.filter_type)
        valid = filt is not None
        self.model[path][2] = text
        self.model[path][3] = valid

    def _update_filter_string(self, *args):
        value = [(row[0], row[1], row[2]) for row in self.model]
        settings.set_value(self.key, GLib.Variant('a(sbs)', value))


class ColumnList(ListWidget):

    available_columns = {
        "size": _("Size"),
        "modification time": _("Modification time"),
        "permissions": _("Permissions"),
    }

    def __init__(self, key):
        ListWidget.__init__(self, "EditableList.ui",
                            "columns_ta", ["ColumnsListStore"],
                            "columns_treeview")
        self.key = key

        # Unwrap the variant
        prefs_columns = [(k, v) for k, v in settings.get_value(self.key)]
        column_vis = {}
        column_order = {}
        for sort_key, (column_name, visibility) in enumerate(prefs_columns):
            column_vis[column_name] = bool(int(visibility))
            column_order[column_name] = sort_key

        columns = [(column_vis.get(name, True), name, label) for
                   name, label in self.available_columns.items()]
        columns = sorted(columns, key=lambda c: column_order.get(c[1], 0))

        for visibility, name, label in columns:
            self.model.append([visibility, name, label])

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
        active_iter = self.get_active_iter()
        if active_iter is None:
            return
        column = self.get_property('gsettings-column')
        value = self.get_model()[active_iter][column]
        self.set_property('gsettings-value', value)


class GSettingsIntComboBox(GSettingsComboBox):

    __gtype_name__ = "GSettingsIntComboBox"

    gsettings_column = GObject.property(type=int, default=0)
    gsettings_value = GObject.property(type=int)


class GSettingsBoolComboBox(GSettingsComboBox):

    __gtype_name__ = "GSettingsBoolComboBox"

    gsettings_column = GObject.property(type=int, default=0)
    gsettings_value = GObject.property(type=bool, default=False)


class GSettingsStringComboBox(GSettingsComboBox):

    __gtype_name__ = "GSettingsStringComboBox"

    gsettings_column = GObject.property(type=int, default=0)
    gsettings_value = GObject.property(type=str, default="")


class PreferencesDialog(Component):

    def __init__(self, parent):
        Component.__init__(self, "preferences.ui", "preferencesdialog",
                           ["adjustment1", "adjustment2", "fileorderstore",
                            "sizegroup_editor", "timestampstore",
                            "mergeorderstore", "sizegroup_file_order_labels",
                            "sizegroup_file_order_combos",
                            'syntaxschemestore'])
        self.widget.set_transient_for(parent)

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
            ('folder-filter-text', self.checkbutton_folder_filter_text, 'active'),
            ('folder-ignore-symlinks', self.checkbutton_ignore_symlinks, 'active'),
            ('vc-show-commit-margin', self.checkbutton_show_commit_margin, 'active'),
            ('vc-commit-margin', self.spinbutton_commit_margin, 'value'),
            ('vc-break-commit-message', self.checkbutton_break_commit_lines, 'active'),
            ('ignore-blank-lines', self.checkbutton_ignore_blank_lines, 'active'),
            # Sensitivity bindings must come after value bindings, or the key
            # writability in gsettings overrides manual sensitivity setting.
            ('vc-show-commit-margin', self.spinbutton_commit_margin, 'sensitive'),
            ('vc-show-commit-margin', self.checkbutton_break_commit_lines, 'sensitive'),
        ]
        for key, obj, attribute in bindings:
            settings.bind(key, obj, attribute, Gio.SettingsBindFlags.DEFAULT)

        invert_bindings = [
            ('use-system-editor', self.custom_edit_command_entry, 'sensitive'),
            ('use-system-font', self.fontpicker, 'sensitive'),
            ('folder-shallow-comparison', self.checkbutton_folder_filter_text, 'sensitive'),
        ]
        for key, obj, attribute in invert_bindings:
            settings.bind(
                key, obj, attribute, Gio.SettingsBindFlags.DEFAULT |
                Gio.SettingsBindFlags.INVERT_BOOLEAN)

        self.checkbutton_wrap_text.bind_property(
            'active', self.checkbutton_wrap_word, 'sensitive',
            GObject.BindingFlags.DEFAULT)

        # TODO: Fix once bind_with_mapping is available
        self.checkbutton_show_whitespace.set_active(
            bool(settings.get_flags('draw-spaces')))

        wrap_mode = settings.get_enum('wrap-mode')
        self.checkbutton_wrap_text.set_active(wrap_mode != Gtk.WrapMode.NONE)
        self.checkbutton_wrap_word.set_active(wrap_mode == Gtk.WrapMode.WORD)

        filefilter = FilterList("filename-filters", FilterEntry.SHELL)
        self.file_filters_vbox.pack_start(filefilter.widget, True, True, 0)

        textfilter = FilterList("text-filters", FilterEntry.REGEX)
        self.text_filters_vbox.pack_start(textfilter.widget, True, True, 0)

        columnlist = ColumnList("folder-columns")
        self.column_list_vbox.pack_start(columnlist.widget, True, True, 0)

        self.combo_timestamp.bind_to('folder-time-resolution')
        self.combo_file_order.bind_to('vc-left-is-local')
        self.combo_merge_order.bind_to('vc-merge-file-order')

        # Fill color schemes
        manager = GtkSource.StyleSchemeManager.get_default()
        for scheme_id in manager.get_scheme_ids():
            scheme = manager.get_scheme(scheme_id)
            self.syntaxschemestore.append([scheme_id, scheme.get_name()])
        self.combobox_style_scheme.bind_to('style-scheme')

        self.widget.show()

    def on_checkbutton_wrap_text_toggled(self, button):
        if not self.checkbutton_wrap_text.get_active():
            wrap_mode = Gtk.WrapMode.NONE
        elif self.checkbutton_wrap_word.get_active():
            wrap_mode = Gtk.WrapMode.WORD
        else:
            wrap_mode = Gtk.WrapMode.CHAR
        settings.set_enum('wrap-mode', wrap_mode)

    def on_checkbutton_show_whitespace_toggled(self, widget):
        value = GtkSource.DrawSpacesFlags.ALL if widget.get_active() else 0
        settings.set_flags('draw-spaces', value)

    def on_response(self, dialog, response_id):
        self.widget.destroy()
