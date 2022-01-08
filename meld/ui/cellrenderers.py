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

from gi.repository import GObject, Gtk


class CellRendererDate(Gtk.CellRendererText):

    __gtype_name__ = "CellRendererDate"

    #: We use negative 32-bit Unix timestamp to threshold our valid values
    MIN_TIMESTAMP = -2147483648
    DATETIME_FORMAT = "%a %d %b %Y %H:%M:%S"

    def _format_datetime(self, dt: datetime.datetime) -> str:
        return dt.strftime(self.DATETIME_FORMAT)

    def get_timestamp(self):
        return getattr(self, '_datetime', self.MIN_TIMESTAMP)

    def set_timestamp(self, value):
        if value == self.get_timestamp():
            return
        if value <= self.MIN_TIMESTAMP:
            time_str = ''
        else:
            try:
                mod_datetime = datetime.datetime.fromtimestamp(value)
                time_str = self._format_datetime(mod_datetime)
            except Exception:
                time_str = ''
        self.props.markup = time_str
        self._datetime = value

    timestamp = GObject.Property(
        type=float,
        nick="Unix timestamp to display",
        getter=get_timestamp,
        setter=set_timestamp,
    )


class CellRendererISODate(CellRendererDate):

    __gtype_name__ = "CellRendererISODate"

    def _format_datetime(self, dt: datetime.datetime) -> str:
        # Limit our ISO display to seconds (i.e., no milli or
        # microseconds) for usability
        return dt.isoformat(timespec="seconds")


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
