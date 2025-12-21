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

import enum
from typing import Self

from gi.repository import Adw, Gio, GLib, GObject, Gtk, GtkSource

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


class PreferenceEnum(str, enum.Enum):
    def __new__(cls, value, label, unit):
        obj = str.__new__(cls, [value])
        obj._value_ = value
        obj.label = label
        obj.settings_value = unit
        return obj

    @classmethod
    def from_enum(cls, genum) -> Self:
        for member in cls:
            if member.settings_value == genum:
                return member
        raise ValueError(f"Unsupported {cls} setting value {genum}")


class PreferenceComboRow(Adw.ComboRow):
    __gtype_name__ = "PreferenceComboRow"

    enum_cls_name = GObject.Property(
        type=str,
        flags=GObject.ParamFlags.READWRITE | GObject.ParamFlags.CONSTRUCT_ONLY,
    )
    settings_key = GObject.Property(
        type=str,
        flags=GObject.ParamFlags.READWRITE | GObject.ParamFlags.CONSTRUCT_ONLY,
    )

    def do_realize(self):
        Adw.ComboRow.do_realize(self)

        self.enum_cls = globals()[self.props.enum_cls_name]
        self.connect("notify::selected-item", self.selected_item_changed)
        settings.connect(f"changed::{self.props.settings_key}", self.setting_changed)
        self.setting_changed(settings, None)

        # Need to keep a reference to the closure expression here;
        # self.props.expresion does not appear to do so.
        self._expression = Gtk.ClosureExpression.new(str, self.get_text_wrap_label)
        self.props.expression = self._expression

    def selected_item_changed(self, row, paramspec):
        enum_value = self.enum_cls(row.props.selected_item.get_string())
        if self.enum_cls.setting_type is bool:
            settings.set_boolean(self.props.settings_key, enum_value.settings_value)
        elif self.enum_cls.setting_type is int:
            settings.set_int(self.props.settings_key, enum_value.settings_value)
        elif self.enum_cls.setting_type is str:
            settings.set_enum(self.props.settings_key, enum_value.settings_value)
        else:
            raise NotImplementedError()

    def setting_changed(self, settings, key):
        if self.enum_cls.setting_type is bool:
            setting_value = settings.get_boolean(self.props.settings_key)
        elif self.enum_cls.setting_type is int:
            setting_value = settings.get_int(self.props.settings_key)
        elif self.enum_cls.setting_type is str:
            setting_value = settings.get_enum(self.props.settings_key)
        else:
            raise NotImplementedError(
                f"Unsupported Setting type {self.enum_cls.setting_type}"
            )

        enum_value = self.enum_cls.from_enum(setting_value)
        self.props.selected = self.get_model().find(enum_value._value_)

    def get_text_wrap_label(self, string_object):
        return self.enum_cls(string_object.get_string()).label


class WrapMode(PreferenceEnum):
    setting_type = enum.nonmember(str)

    none = ("none", _("Never"), Gtk.WrapMode.NONE)
    word = ("word", _("At Spaces"), Gtk.WrapMode.WORD)
    char = ("char", _("Anywhere"), Gtk.WrapMode.CHAR)


class StyleVariant(PreferenceEnum):
    setting_type = enum.nonmember(str)

    default = ("default", _("Follow System"), Adw.ColorScheme.DEFAULT)
    force_light = ("force-light", _("Light"), Adw.ColorScheme.FORCE_LIGHT)
    force_ark = ("force-dark", _("Dark"), Adw.ColorScheme.FORCE_DARK)


class TabCharacter(PreferenceEnum):
    setting_type = enum.nonmember(bool)

    tab = ("tab", _("Tab"), False)
    spaces = ("spaces", _("Spaces"), True)


class TimestampResolution(PreferenceEnum):
    setting_type = enum.nonmember(int)

    one_ns = ("one_ns", _("1ns (ext4)"), 1)
    onehundred_ns = ("onehundred_ns", _("100ns (NTFS)"), 100)
    one_s = ("one_s", _("1s (ext2/ext3)"), 1000000000)
    two_s = ("two_s", _("2s (VFAT)"), 2000000000)
    ignore = ("ignore", _("Ignore timestamp"), -1)


class VersionPaneOrder(PreferenceEnum):
    setting_type = enum.nonmember(bool)

    lrrl = ("lrrl", _("Left is remote, right is local"), False)
    llrr = ("llrr", _("Left is local, right is remote"), True)


class MergePaneOrder(PreferenceEnum):
    setting_type = enum.nonmember(str)

    remote_merge_local = ("remote-merge-local", _("Remote, merge, local"), 1)
    local_merge_remote = ("local-merge-remote", _("Local, merge, remote"), 0)


@Gtk.Template(resource_path='/org/gnome/meld/ui/preferences.ui')
class PreferencesDialog(Adw.PreferencesDialog):

    __gtype_name__ = "PreferencesDialog"

    checkbutton_break_commit_lines = Gtk.Template.Child()
    checkbutton_folder_filter_text = Gtk.Template.Child()
    checkbutton_highlight_current_line = Gtk.Template.Child()
    checkbutton_ignore_blank_lines = Gtk.Template.Child()
    checkbutton_ignore_symlinks = Gtk.Template.Child()
    checkbutton_shallow_compare = Gtk.Template.Child()
    checkbutton_show_commit_margin = Gtk.Template.Child()
    checkbutton_show_line_numbers = Gtk.Template.Child()
    checkbutton_show_overview_map = Gtk.Template.Child()
    checkbutton_show_whitespace = Gtk.Template.Child()
    column_list_vbox = Gtk.Template.Child()
    custom_edit_command_entry = Gtk.Template.Child()
    custom_font_switch_row = Gtk.Template.Child()
    file_filters_vbox = Gtk.Template.Child()
    fontpicker = Gtk.Template.Child()
    spinbutton_commit_margin = Gtk.Template.Child()
    spinbutton_tabsize = Gtk.Template.Child()
    style_scheme_chooser_button = Gtk.Template.Child()
    syntax_highlighting_switch_row = Gtk.Template.Child()
    system_editor_checkbutton = Gtk.Template.Child()
    text_wrapping_combo_row = Gtk.Template.Child()
    text_filters_vbox = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        bindings = [
            ('custom-font', self.fontpicker, 'font'),
            ('indent-width', self.spinbutton_tabsize, 'value'),
            ('highlight-current-line', self.checkbutton_highlight_current_line, 'active'),  # noqa: E501
            ('show-line-numbers', self.checkbutton_show_line_numbers, 'active'),  # noqa: E501
            ("highlight-syntax", self.syntax_highlighting_switch_row, "enable-expansion"),  # noqa: E501
            ('enable-space-drawer', self.checkbutton_show_whitespace, 'active'),  # noqa: E501
            ('custom-editor-command', self.custom_edit_command_entry, 'text'),
            ("folder-shallow-comparison", self.checkbutton_shallow_compare, "enable-expansion"),  # noqa: E501
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
            ("use-system-editor", self.system_editor_checkbutton, "enable-expansion"),
            ("use-system-font", self.custom_font_switch_row, "enable-expansion"),
            ('folder-shallow-comparison', self.checkbutton_folder_filter_text, 'sensitive'),  # noqa: E501
        ]
        for key, obj, attribute in invert_bindings:
            settings.bind(
                key, obj, attribute, Gio.SettingsBindFlags.DEFAULT |
                Gio.SettingsBindFlags.INVERT_BOOLEAN)

        filefilter = FilterList(
            filter_type=FilterEntry.SHELL,
            settings_key="filename-filters",
        )
        filefilter.set_vexpand(True)
        self.file_filters_vbox.append(filefilter)

        textfilter = FilterList(
            filter_type=FilterEntry.REGEX,
            settings_key="text-filters",
        )
        textfilter.set_vexpand(True)
        self.text_filters_vbox.append(textfilter)

        columnlist = ColumnList(settings_key="folder-columns")
        columnlist.set_vexpand(True)
        self.column_list_vbox.append(columnlist)

        def setting_from_scheme(*args):
            scheme_id = self.style_scheme_chooser_button.props.style_scheme.get_id()
            settings.set_string("style-scheme", scheme_id)

        def scheme_from_setting(*args):
            manager = GtkSource.StyleSchemeManager.get_default()
            scheme_id = settings.get_string("style-scheme")
            scheme = manager.get_scheme(scheme_id)
            self.style_scheme_chooser_button.set_style_scheme(scheme)

        self.style_scheme_chooser_button.connect(
            "notify::style-scheme", setting_from_scheme
        )
        settings.connect("changed::style-scheme", scheme_from_setting)
        scheme_from_setting()
