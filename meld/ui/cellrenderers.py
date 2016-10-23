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
        return getattr(self, '_datetime', None)

    def set_timestamp(self, value):
        if value == self.get_timestamp():
            return
        if value is None:
            time_str = ''
        else:
            mod_datetime = datetime.datetime.fromtimestamp(value)
            time_str = mod_datetime.strftime(self.DATETIME_FORMAT)
        self.props.markup = time_str
        self._datetime = value

    timestamp = GObject.property(
        type=object,
        nick="Unix timestamp to display",
        getter=get_timestamp,
        setter=set_timestamp,
    )
    )
