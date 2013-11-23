# Copyright (C) 2013 Kai Willadsen <kai.willadsen@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.

# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from gi.repository import Gio
from gi.repository import GObject

import meld.conf
import meld.filters

schema_source = Gio.SettingsSchemaSource.new_from_directory(
    meld.conf.DATADIR,
    Gio.SettingsSchemaSource.get_default(),
    False,
)
schema = schema_source.lookup('org.gnome.meld', False)
settings = Gio.Settings.new_full(schema, None, None)

interface_settings = Gio.Settings.new('org.gnome.desktop.interface')


class MeldSettings(GObject.GObject):
    """Handler for settings that can't easily be bound to object properties"""

    __gsignals__ = {
        'file-filters-changed': (GObject.SignalFlags.RUN_FIRST,
                                 None, ()),
        'text-filters-changed': (GObject.SignalFlags.RUN_FIRST,
                                 None, ()),
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.on_setting_changed(settings, 'filename-filters')
        self.on_setting_changed(settings, 'text-filters')
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

    def _filters_from_gsetting(self, key, filt_type):
        filter_params = settings.get_value(key)
        filters = [
            meld.filters.FilterEntry.new_from_gsetting(params, filt_type)
            for params in filter_params
        ]
        return filters

meldsettings = MeldSettings()
