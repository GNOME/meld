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

from gi.repository import Gio, GLib, GObject, Gtk, GtkSource

from meld.conf import _
from meld.filters import FilterEntry
from meld.settings import settings
from meld.ui.listwidget import EditableListWidget


@Gtk.Template(resource_path='/org/gnome/meld/ui/filter-list.ui')
class FilterList(Gtk.Box, EditableListWidget):

    __gtype_name__ = "FilterList"

    treeview = Gtk.Template.Child()
    remove = Gtk.Template.Child()
    move_up = Gtk.Template.Child()
    move_down = Gtk.Template.Child()
    pattern_column = Gtk.Template.Child()
    validity_renderer = Gtk.Template.Child()

    default_entry = [_("label"), False, _("pattern"), True]

    filter_type = GObject.Property(
        type=int,
        flags=(
            GObject.ParamFlags.READABLE |
            GObject.ParamFlags.WRITABLE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    settings_key = GObject.Property(
        type=str,
        flags=(
            GObject.ParamFlags.READABLE |
            GObject.ParamFlags.WRITABLE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.model = self.treeview.get_model()

        self.pattern_column.set_cell_data_func(
            self.validity_renderer, self.valid_icon_celldata)

        for filter_params in settings.get_value(self.settings_key):
            filt = FilterEntry.new_from_gsetting(
                filter_params, self.filter_type)
            if filt is None:
                continue
            valid = filt.filter is not None
            self.model.append(
                [filt.label, filt.active, filt.filter_string, valid])

        for signal in ('row-changed', 'row-deleted', 'row-inserted',
                       'rows-reordered'):
            self.model.connect(signal, self._update_filter_string)

        self.setup_sensitivity_handling()

    def valid_icon_celldata(self, col, cell, model, it, user_data=None):
        is_valid = model.get_value(it, 3)
        icon_name = "dialog-warning-symbolic" if not is_valid else None
        cell.set_property("icon-name", icon_name)

    @Gtk.Template.Callback()
    def on_add_clicked(self, button):
        self.add_entry()

    @Gtk.Template.Callback()
    def on_remove_clicked(self, button):
        self.remove_selected_entry()

    @Gtk.Template.Callback()
    def on_move_up_clicked(self, button):
        self.move_up_selected_entry()

    @Gtk.Template.Callback()
    def on_move_down_clicked(self, button):
        self.move_down_selected_entry()

    @Gtk.Template.Callback()
    def on_name_edited(self, ren, path, text):
        self.model[path][0] = text

    @Gtk.Template.Callback()
    def on_cellrenderertoggle_toggled(self, ren, path):
        self.model[path][1] = not ren.get_active()

    @Gtk.Template.Callback()
    def on_pattern_edited(self, ren, path, text):
        valid = FilterEntry.check_filter(text, self.filter_type)
        self.model[path][2] = text
        self.model[path][3] = valid

    def _update_filter_string(self, *args):
        value = [(row[0], row[1], row[2]) for row in self.model]
        settings.set_value(self.settings_key, GLib.Variant('a(sbs)', value))


@Gtk.Template(resource_path='/org/gnome/meld/ui/column-list.ui')
class ColumnList(Gtk.Box, EditableListWidget):

    __gtype_name__ = "ColumnList"

    treeview = Gtk.Template.Child()
    remove = Gtk.Template.Child()
    move_up = Gtk.Template.Child()
    move_down = Gtk.Template.Child()

    default_entry = [_("label"), False, _("pattern"), True]

    available_columns = {
        "size": _("Size"),
        "modification time": _("Modification time"),
        "iso-time": _("Modification time (ISO)"),
        "permissions": _("Permissions"),
    }

    settings_key = GObject.Property(
        type=str,
        flags=(
            GObject.ParamFlags.READABLE |
            GObject.ParamFlags.WRITABLE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.model = self.treeview.get_model()

        # Unwrap the variant
        prefs_columns = [
            (k, v) for k, v in settings.get_value(self.settings_key)
        ]
        column_vis = {}
        column_order = {}
        for sort_key, (column_name, visibility) in enumerate(prefs_columns):
            column_vis[column_name] = bool(int(visibility))
            column_order[column_name] = sort_key

        columns = [
            (column_vis.get(name, False), name, label)
            for name, label in self.available_columns.items()
        ]
        columns = sorted(
            columns,
            key=lambda c: column_order.get(c[1], len(self.available_columns)),
        )

        for visibility, name, label in columns:
            self.model.append([visibility, name, label])

        for signal in ('row-changed', 'row-deleted', 'row-inserted',
                       'rows-reordered'):
            self.model.connect(signal, self._update_columns)

        self.setup_sensitivity_handling()

    @Gtk.Template.Callback()
    def on_move_up_clicked(self, button):
        self.move_up_selected_entry()

    @Gtk.Template.Callback()
    def on_move_down_clicked(self, button):
        self.move_down_selected_entry()

    @Gtk.Template.Callback()
    def on_cellrenderertoggle_toggled(self, ren, path):
        self.model[path][0] = not ren.get_active()

    def _update_columns(self, *args):
        value = [(c[1].lower(), c[0]) for c in self.model]
        settings.set_value(self.settings_key, GLib.Variant('a(sb)', value))


class GSettingsComboBox(Gtk.ComboBox):

    def __init__(self):
        super().__init__()
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

    gsettings_column = GObject.Property(type=int, default=0)
    gsettings_value = GObject.Property(type=int)


class GSettingsBoolComboBox(GSettingsComboBox):

    __gtype_name__ = "GSettingsBoolComboBox"

    gsettings_column = GObject.Property(type=int, default=0)
    gsettings_value = GObject.Property(type=bool, default=False)


class GSettingsStringComboBox(GSettingsComboBox):

    __gtype_name__ = "GSettingsStringComboBox"

    gsettings_column = GObject.Property(type=int, default=0)
    gsettings_value = GObject.Property(type=str, default="")


@Gtk.Template(resource_path='/org/gnome/meld/ui/preferences.ui')
class PreferencesDialog(Gtk.Dialog):

    __gtype_name__ = "PreferencesDialog"

    checkbutton_break_commit_lines = Gtk.Template.Child()
    checkbutton_default_font = Gtk.Template.Child()
    checkbutton_folder_filter_text = Gtk.Template.Child()
    checkbutton_highlight_current_line = Gtk.Template.Child()
    checkbutton_ignore_blank_lines = Gtk.Template.Child()
    checkbutton_ignore_symlinks = Gtk.Template.Child()
    checkbutton_prefer_dark_theme = Gtk.Template.Child()
    checkbutton_shallow_compare = Gtk.Template.Child()
    checkbutton_show_commit_margin = Gtk.Template.Child()
    checkbutton_show_line_numbers = Gtk.Template.Child()
    checkbutton_show_overview_map = Gtk.Template.Child()
    checkbutton_show_whitespace = Gtk.Template.Child()
    checkbutton_spaces_instead_of_tabs = Gtk.Template.Child()
    checkbutton_use_syntax_highlighting = Gtk.Template.Child()
    checkbutton_wrap_text = Gtk.Template.Child()
    checkbutton_wrap_word = Gtk.Template.Child()
    column_list_vbox = Gtk.Template.Child()
    combo_file_order = Gtk.Template.Child()
    combo_merge_order = Gtk.Template.Child()
    combo_overview_map = Gtk.Template.Child()
    combo_timestamp = Gtk.Template.Child()
    combobox_style_scheme = Gtk.Template.Child()
    custom_edit_command_entry = Gtk.Template.Child()
    file_filters_vbox = Gtk.Template.Child()
    fontpicker = Gtk.Template.Child()
    spinbutton_commit_margin = Gtk.Template.Child()
    spinbutton_tabsize = Gtk.Template.Child()
    syntaxschemestore = Gtk.Template.Child()
    system_editor_checkbutton = Gtk.Template.Child()
    text_filters_vbox = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        bindings = [
            ('use-system-font', self.checkbutton_default_font, 'active'),
            ('custom-font', self.fontpicker, 'font'),
            ('indent-width', self.spinbutton_tabsize, 'value'),
            ('insert-spaces-instead-of-tabs', self.checkbutton_spaces_instead_of_tabs, 'active'),  # noqa: E501
            ('highlight-current-line', self.checkbutton_highlight_current_line, 'active'),  # noqa: E501
            ('show-line-numbers', self.checkbutton_show_line_numbers, 'active'),  # noqa: E501
            ('prefer-dark-theme', self.checkbutton_prefer_dark_theme, 'active'),  # noqa: E501
            ('highlight-syntax', self.checkbutton_use_syntax_highlighting, 'active'),  # noqa: E501
            ('enable-space-drawer', self.checkbutton_show_whitespace, 'active'),  # noqa: E501
            ('use-system-editor', self.system_editor_checkbutton, 'active'),
            ('custom-editor-command', self.custom_edit_command_entry, 'text'),
            ('folder-shallow-comparison', self.checkbutton_shallow_compare, 'active'),  # noqa: E501
            ('folder-filter-text', self.checkbutton_folder_filter_text, 'active'),  # noqa: E501
            ('folder-ignore-symlinks', self.checkbutton_ignore_symlinks, 'active'),  # noqa: E501
            ('vc-show-commit-margin', self.checkbutton_show_commit_margin, 'active'),  # noqa: E501
            ('show-overview-map', self.checkbutton_show_overview_map, 'active'),  # noqa: E501
            ('vc-commit-margin', self.spinbutton_commit_margin, 'value'),
            ('vc-break-commit-message', self.checkbutton_break_commit_lines, 'active'),  # noqa: E501
            ('ignore-blank-lines', self.checkbutton_ignore_blank_lines, 'active'),  # noqa: E501
            # Sensitivity bindings must come after value bindings, or the key
            # writability in gsettings overrides manual sensitivity setting.
            ('vc-show-commit-margin', self.spinbutton_commit_margin, 'sensitive'),  # noqa: E501
            ('vc-show-commit-margin', self.checkbutton_break_commit_lines, 'sensitive'),  # noqa: E501
        ]
        for key, obj, attribute in bindings:
            settings.bind(key, obj, attribute, Gio.SettingsBindFlags.DEFAULT)

        invert_bindings = [
            ('use-system-editor', self.custom_edit_command_entry, 'sensitive'),
            ('use-system-font', self.fontpicker, 'sensitive'),
            ('folder-shallow-comparison', self.checkbutton_folder_filter_text, 'sensitive'),  # noqa: E501
        ]
        for key, obj, attribute in invert_bindings:
            settings.bind(
                key, obj, attribute, Gio.SettingsBindFlags.DEFAULT |
                Gio.SettingsBindFlags.INVERT_BOOLEAN)

        self.checkbutton_wrap_text.bind_property(
            'active', self.checkbutton_wrap_word, 'sensitive',
            GObject.BindingFlags.DEFAULT)

        wrap_mode = settings.get_enum('wrap-mode')
        self.checkbutton_wrap_text.set_active(wrap_mode != Gtk.WrapMode.NONE)
        self.checkbutton_wrap_word.set_active(wrap_mode == Gtk.WrapMode.WORD)

        filefilter = FilterList(
            filter_type=FilterEntry.SHELL,
            settings_key="filename-filters",
        )
        self.file_filters_vbox.pack_start(filefilter, True, True, 0)

        textfilter = FilterList(
            filter_type=FilterEntry.REGEX,
            settings_key="text-filters",
        )
        self.text_filters_vbox.pack_start(textfilter, True, True, 0)

        columnlist = ColumnList(settings_key="folder-columns")
        self.column_list_vbox.pack_start(columnlist, True, True, 0)

        self.combo_timestamp.bind_to('folder-time-resolution')
        self.combo_file_order.bind_to('vc-left-is-local')
        self.combo_overview_map.bind_to('overview-map-style')
        self.combo_merge_order.bind_to('vc-merge-file-order')

        # Fill color schemes
        manager = GtkSource.StyleSchemeManager.get_default()
        for scheme_id in manager.get_scheme_ids():
            scheme = manager.get_scheme(scheme_id)
            self.syntaxschemestore.append([scheme_id, scheme.get_name()])
        self.combobox_style_scheme.bind_to('style-scheme')

        self.show()

    @Gtk.Template.Callback()
    def on_checkbutton_wrap_text_toggled(self, button):
        if not self.checkbutton_wrap_text.get_active():
            wrap_mode = Gtk.WrapMode.NONE
        elif self.checkbutton_wrap_word.get_active():
            wrap_mode = Gtk.WrapMode.WORD
        else:
            wrap_mode = Gtk.WrapMode.CHAR
        settings.set_enum('wrap-mode', wrap_mode)

    @Gtk.Template.Callback()
    def on_response(self, dialog, response_id):
        self.destroy()
