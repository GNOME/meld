# Copyright (C) 2011 Kai Willadsen <kai.willadsen@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""This module encapsulates optional D-Bus support for Meld."""

import dbus
import dbus.bus
import dbus.service
import dbus.mainloop.glib


DBUS_NAME = "org.gnome.Meld"
DBUS_PATH = "/org/gnome/Meld"

if getattr(dbus, 'version', (0, 0, 0)) < (0, 83, 0):
    raise ImportError("Unsupported dbus version")


class DBusProvider(dbus.service.Object):
    """Implements a simple interface for controlling a MeldApp."""

    def __init__(self, bus, name, path, app):
        dbus.service.Object.__init__(self, bus, path, name)
        self.app = app

    @dbus.service.method(DBUS_NAME, in_signature='asu')
    def OpenPaths(self, args, timestamp):
        """Attempt to open a new tab comparing the passed paths.

        If a valid timestamp is not available, pass 0.
        """
        tab = self.app.window.open_paths(args)
        if timestamp > 0:
            self.app.window.widget.present_with_time(timestamp)
        else:
            self.app.window.widget.present()
        self.app.window.notebook.set_current_page(
            self.app.window.notebook.page_num(tab.widget))


def setup(app):
    """Request and return a dbus interface for controlling the MeldApp."""
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    request = bus.request_name(DBUS_NAME, dbus.bus.NAME_FLAG_DO_NOT_QUEUE)
    already_running = request == dbus.bus.REQUEST_NAME_REPLY_EXISTS
    if already_running:
        obj = dbus.Interface(bus.get_object(DBUS_NAME, DBUS_PATH), DBUS_NAME)
    else:
        obj = DBusProvider(bus, DBUS_NAME, DBUS_PATH, app)
    return already_running, obj
