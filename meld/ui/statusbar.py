# Copyright (C) 2012-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango


Gtk.rc_parse_string(
    """
    style "meld-statusbar-style" {
        GtkStatusbar::shadow-type = GTK_SHADOW_NONE
    }
    class "MeldStatusBar" style "meld-statusbar-style"
    """)


class MeldStatusBar(Gtk.Statusbar):
    __gtype_name__ = "MeldStatusBar"

    def __init__(self):
        GObject.GObject.__init__(self)
        self.props.spacing = 6

        hbox = self.get_message_area()
        label = hbox.get_children()[0]
        hbox.props.spacing = 6
        label.props.ellipsize = Pango.EllipsizeMode.NONE
        hbox.remove(label)
        hbox.pack_start(label, True, True, 0)

        alignment = Gtk.Alignment.new(
            xalign=1.0, yalign=0.5, xscale=1.0, yscale=1.0)
        self.info_box = Gtk.HBox(homogeneous=False, spacing=12)
        self.info_box.show()
        alignment.add(self.info_box)
        self.pack_start(alignment, True, True, 0)
        alignment.show()

    def set_info_box(self, widgets):
        for child in self.info_box.get_children():
            self.info_box.remove(child)
        for widget in widgets:
            self.info_box.pack_end(widget, False, True, 0)
