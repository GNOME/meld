# Copyright (C) 2013 Kai Willadsen <kai.willadsen@gmail.com>
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
from gi.repository import GObject
from gi.repository import GtkSource
from gi.repository import Pango

import meld.conf
import meld.filters


class MeldSettings(GObject.GObject):
    """Handler for settings that can't easily be bound to object properties"""

    __gsignals__ = {
        'file-filters-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'text-filters-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'changed': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self.on_setting_changed(settings, 'filename-filters')
        self.on_setting_changed(settings, 'text-filters')
        self.on_setting_changed(settings, 'use-system-font')
        self.style_scheme = self._style_scheme_from_gsettings()
        settings.connect('changed', self.on_setting_changed)

    def on_setting_changed(self, settings, key):
        if key == 'filename-filters':
            self.file_filters = self._filters_from_gsetting(
                'filename-filters', meld.filters.FilterEntry.SHELL)
            self.emit('file-filters-changed')
        elif key == 'text-filters':
            self.text_filters = self._filters_from_gsetting(
                'text-filters', meld.filters.FilterEntry.REGEX)
            self.emit('text-filters-changed')
        elif key in ('use-system-font', 'custom-font'):
            self.font = self._current_font_from_gsetting()
            self.emit('changed', 'font')
        elif key in ('style-scheme'):
            self.style_scheme = self._style_scheme_from_gsettings()
            self.emit('changed', 'style-scheme')

    def _style_scheme_from_gsettings(self):
        manager = GtkSource.StyleSchemeManager.get_default()
        return manager.get_scheme(settings.get_string('style-scheme'))

    def _filters_from_gsetting(self, key, filt_type):
        filter_params = settings.get_value(key)
        filters = [
            meld.filters.FilterEntry.new_from_gsetting(params, filt_type)
            for params in filter_params
        ]
        return filters

    def _current_font_from_gsetting(self, *args):
        if settings.get_boolean('use-system-font'):
            font_string = interface_settings.get_string('monospace-font-name')
        else:
            font_string = settings.get_string('custom-font')
        return Pango.FontDescription(font_string)


def load_settings_schema(schema_id):
    if meld.conf.DATADIR_IS_UNINSTALLED:
        schema_source = Gio.SettingsSchemaSource.new_from_directory(
            meld.conf.DATADIR,
            Gio.SettingsSchemaSource.get_default(),
            False,
        )
        schema = schema_source.lookup(schema_id, False)
        settings = Gio.Settings.new_full(
            schema=schema, backend=None, path=None)
    else:
        settings = Gio.Settings.new(schema_id)
    return settings


def create_settings():
    global settings, interface_settings, meldsettings

    settings = load_settings_schema(meld.conf.APPLICATION_ID)
    interface_settings = Gio.Settings.new('org.gnome.desktop.interface')
    meldsettings = MeldSettings()


def bind_settings(obj):
    global settings
    bind_flags = (
        Gio.SettingsBindFlags.DEFAULT | Gio.SettingsBindFlags.NO_SENSITIVITY)
    for binding in getattr(obj, '__gsettings_bindings__', ()):
        settings_id, property_id = binding
        settings.bind(settings_id, obj, property_id, bind_flags)


settings = None
interface_settings = None
meldsettings = None
