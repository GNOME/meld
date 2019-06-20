# Copyright (C) 2016 Kai Willadsen <kai.willadsen@gmail.com>
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

import datetime

from gi.repository import GObject
from gi.repository import Gtk


class CellRendererDate(Gtk.CellRendererText):

    __gtype_name__ = "CellRendererDate"

    DATETIME_FORMAT = "%a %d %b %Y %H:%M:%S"

    def get_timestamp(self):
        return getattr(self, '_datetime', -1.0)

    def set_timestamp(self, value):
        if value == self.get_timestamp():
            return
        if value == -1.0:
            time_str = ''
        else:
            mod_datetime = datetime.datetime.fromtimestamp(value)
            time_str = mod_datetime.strftime(self.DATETIME_FORMAT)
        self.props.markup = time_str
        self._datetime = value

    timestamp = GObject.Property(
        type=float,
        nick="Unix timestamp to display",
        getter=get_timestamp,
        setter=set_timestamp,
    )


class CellRendererByteSize(Gtk.CellRendererText):

    __gtype_name__ = "CellRendererByteSize"

    def get_bytesize(self):
        return getattr(self, '_bytesize', -1)

    def set_bytesize(self, value):
        if value == self.get_bytesize():
            return
        if value == -1:
            byte_str = ''
        else:
            suffixes = (
                'B', 'kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'
            )
            size = float(value)
            unit = 0
            while size > 1000 and unit < len(suffixes) - 1:
                size /= 1000
                unit += 1
            format_str = "%.1f %s" if unit > 0 else "%d %s"
            byte_str = format_str % (size, suffixes[unit])
        self.props.markup = byte_str
        self._bytesize = value

    bytesize = GObject.Property(
        type=GObject.TYPE_INT64,
        nick="Byte size to display",
        getter=get_bytesize,
        setter=set_bytesize,
    )


class CellRendererFileMode(Gtk.CellRendererText):

    __gtype_name__ = "CellRendererFileMode"

    def get_file_mode(self):
        return getattr(self, '_file_mode', -1)

    def set_file_mode(self, value):
        if value == self.get_file_mode():
            return
        if value == -1.0:
            mode_str = ''
        else:
            perms = []
            rwx = ((4, 'r'), (2, 'w'), (1, 'x'))
            for group_index in (6, 3, 0):
                group = value >> group_index & 7
                perms.extend([p if group & i else '-' for i, p in rwx])
            mode_str = "".join(perms)
        self.props.markup = mode_str
        self._file_mode = value

    file_mode = GObject.Property(
        type=int,
        nick="Byte size to display",
        getter=get_file_mode,
        setter=set_file_mode,
    )
