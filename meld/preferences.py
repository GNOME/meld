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

import logging
import shlex
import string

from gettext import gettext as _

from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk

from . import filters
from . import misc
from . import vc
from .ui import gnomeglade
from .ui import listwidget
from .util import prefs

from meld.settings import settings, interface_settings


TIMESTAMP_RESOLUTION_PRESETS = [('1ns (ext4)', 1),
                                ('100ns (NTFS)', 100),
                                ('1s (ext2/ext3)', 1000000000),
                                ('2s (VFAT)', 2000000000)]

log = logging.getLogger(__name__)


class FilterList(listwidget.ListWidget):

    def __init__(self, prefs, key, filter_type):
        default_entry = [_("label"), False, _("pattern"), True]
        listwidget.ListWidget.__init__(self, "EditableList.ui",
                                       "list_alignment", ["EditableListStore"],
                                       "EditableList", default_entry)
        self.prefs = prefs
        self.key = key
        self.filter_type = filter_type

        self.pattern_column.set_cell_data_func(self.validity_renderer,
                                               self.valid_icon_celldata)

        for filtstring in getattr(self.prefs, self.key).split("\n"):
            filt = filters.FilterEntry.parse(filtstring, filter_type)
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
        pref = []
        for row in self.model:
            pattern = row[2]
            if pattern:
                pattern = pattern.replace('\r', '')
                pattern = pattern.replace('\n', '')
            pref.append("%s\t%s\t%s" % (row[0], 1 if row[1] else 0, pattern))
        setattr(self.prefs, self.key, "\n".join(pref))


class ColumnList(listwidget.ListWidget):

    available_columns = set((
        "size",
        "modification time",
        "permissions",
    ))

    def __init__(self, prefs, key):
        listwidget.ListWidget.__init__(self, "EditableList.ui",
                               "columns_ta", ["ColumnsListStore"],
                               "columns_treeview")
        self.prefs = prefs
        self.key = key

        prefs_columns = []
        for column in getattr(self.prefs, self.key):
            column_name, visibility = column.rsplit(" ", 1)
            visibility = bool(int(visibility))
            prefs_columns.append((column_name, visibility))

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
        columns = ["%s %d" % (c[1].lower(), int(c[0])) for c in self.model]
        setattr(self.prefs, self.key, columns)


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
            ('indent-width', self.spinbutton_tabsize, 'value'),
            ('insert-spaces-instead-of-tabs', self.checkbutton_spaces_instead_of_tabs, 'active'),
            ('highlight-current-line', self.checkbutton_highlight_current_line, 'active'),
            ('show-line-numbers', self.checkbutton_show_line_numbers, 'active'),
            ('highlight-syntax', self.checkbutton_use_syntax_highlighting, 'active'),
            ('use-system-editor', self.system_editor_checkbutton, 'active'),
            ('custom-editor-command', self.custom_edit_command_entry, 'text'),
            ('folder-shallow-comparison', self.checkbutton_shallow_compare, 'active'),
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

        if not self.prefs.use_custom_font:
            self.checkbutton_default_font.set_active(True)
            self.fontpicker.set_sensitive(False)
        else:
            self.checkbutton_default_font.set_active(False)
            self.fontpicker.set_sensitive(True)
            self.fontpicker.set_font_name(self.prefs.custom_font)
        self.fontpicker.set_font_name( self.prefs.custom_font )
        self.checkbutton_show_whitespace.set_active(
            self.prefs.show_whitespace)
        # TODO: This doesn't restore the state of character wrapping when word
        # wrapping is disabled, but this is hard with our existing gconf keys
        if self.prefs.edit_wrap_lines != Gtk.WrapMode.NONE:
            if self.prefs.edit_wrap_lines == Gtk.WrapMode.CHAR:
                self.checkbutton_split_words.set_active(False)
            self.checkbutton_wrap_text.set_active(True)

        # file filters
        self.filefilter = FilterList(self.prefs, "filters",
                                     filters.FilterEntry.SHELL)
        self.file_filters_tab.pack_start(self.filefilter.widget, True, True, 0)
        self.checkbutton_ignore_symlinks.set_active( self.prefs.ignore_symlinks)

        # text filters
        self.textfilter = FilterList(self.prefs, "regexes",
                                     filters.FilterEntry.REGEX)
        self.text_filters_tab.pack_start(self.textfilter.widget, True, True, 0)
        self.checkbutton_ignore_blank_lines.set_active( self.prefs.ignore_blank_lines )
        # encoding
        self.entry_text_codecs.set_text( self.prefs.text_codecs )

        columnlist = ColumnList(self.prefs, "dirdiff_columns")
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

    def on_fontpicker_font_set(self, picker):
        self.prefs.custom_font = picker.get_font_name()

    def on_checkbutton_default_font_toggled(self, button):
        use_custom = not button.get_active()
        self.fontpicker.set_sensitive(use_custom)
        self.prefs.use_custom_font = use_custom

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

    def on_checkbutton_show_whitespace_toggled(self, check):
        self.prefs.show_whitespace = check.get_active()

    #
    # filters
    #
    def on_checkbutton_ignore_symlinks_toggled(self, check):
        self.prefs.ignore_symlinks = check.get_active()
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
        "use_custom_font": prefs.Value(prefs.BOOL,0),
        "custom_font": prefs.Value(prefs.STRING,"monospace, 14"),
        "show_whitespace": prefs.Value(prefs.BOOL, False),
        "edit_wrap_lines" : prefs.Value(prefs.INT, 0),
        "text_codecs": prefs.Value(prefs.STRING, "utf8 latin1"),
        "ignore_symlinks": prefs.Value(prefs.BOOL,0),
        "vc_console_visible": prefs.Value(prefs.BOOL, 0),
        "filters" : prefs.Value(prefs.STRING,
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Backups\t1\t#*# .#* ~* *~ *.{orig,bak,swp}\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("OS-specific metadata\t0\t.DS_Store ._* .Spotlight-V100 .Trashes Thumbs.db Desktop.ini\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Version Control\t1\t%s\n") % misc.shell_escape(' '.join(vc.get_plugins_metadata())) + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Binaries\t1\t*.{pyc,a,obj,o,so,la,lib,dll,exe}\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Media\t0\t*.{jpg,gif,png,bmp,wav,mp3,ogg,flac,avi,mpg,xcf,xpm}")),
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
        "regexes" : prefs.Value(prefs.STRING, _("CVS keywords\t0\t\$\\w+(:[^\\n$]+)?\$\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("C++ comment\t0\t//.*\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("C comment\t0\t/\*.*?\*/\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("All whitespace\t0\t[ \\t\\r\\f\\v]*\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Leading whitespace\t0\t^[ \\t\\r\\f\\v]*\n") + \
            #TRANSLATORS: translate this string ONLY to the first "\t", leave it and the following parts intact
            _("Script comment\t0\t#.*")),
        "ignore_blank_lines" : prefs.Value(prefs.BOOL, False),
        "toolbar_visible" : prefs.Value(prefs.BOOL, True),
        "statusbar_visible" : prefs.Value(prefs.BOOL, True),
        "dir_status_filters": prefs.Value(prefs.LIST,
                                          ['normal', 'modified', 'new']),
        "vc_status_filters": prefs.Value(prefs.LIST,
                                         ['flatten', 'modified']),
        # Currently, we're using a quite simple format to store the columns:
        # each line contains a column name followed by a 1 or a 0
        # depending on whether the column is visible or not.
        "dirdiff_columns": prefs.Value(prefs.LIST,
                                         ["size 1", "modification time 1",
                                          "permissions 0"]),

        "vc_left_is_local": prefs.Value(prefs.BOOL, False),
    }

    def __init__(self):
        super(MeldPreferences, self).__init__("/apps/meld", self.defaults)

    def get_current_font(self):
        if self.use_custom_font:
            return self.custom_font
        return interface_settings.get_string('monospace-font-name')

    def get_editor_command(self, path, line=0):
        system_editor = settings.get_boolean('use-system-editor')
        if not system_editor:
            custom_command = settings.get_string('custom-editor-command')
            fmt = string.Formatter()
            replacements = [tok[1] for tok in fmt.parse(custom_command)]

            if not any(replacements):
                cmd = " ".join([custom_command, path])
            elif not all(r in (None, 'file', 'line') for r in replacements):
                cmd = " ".join([custom_command, path])
                log.error("Unsupported fields found", )
            else:
                cmd = custom_command.format(file=path, line=line)
            return shlex.split(cmd)
        else:
            if not hasattr(self, "_gconf"):
                return []

            editor_path = "/desktop/gnome/applications/editor/"
            terminal_path = "/desktop/gnome/applications/terminal/"
            editor = self._gconf.get_string(editor_path + "exec") or "gedit"
            if self._gconf.get_bool(editor_path + "needs_term"):
                argv = []
                texec = self._gconf.get_string(terminal_path + "exec")
                if texec:
                    argv.append(texec)
                    targ = self._gconf.get_string(terminal_path + "exec_arg")
                    if targ:
                        argv.append(targ)
                escaped_path = path.replace(" ", "\\ ")
                argv.append("%s %s" % (editor, escaped_path))
                return argv
            else:
                return [editor, path]
