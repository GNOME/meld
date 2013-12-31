### Copyright (C) 2012 Kai Willadsen <kai.willadsen@gmail.com>

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

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango


Gtk.rc_parse_string(
    """
    style "meld-statusbar-style" {
        GtkStatusbar::shadow-type = GTK_SHADOW_NONE
    }
    class "MeldStatusBar" style "meld-statusbar-style"

    style "meld-progressbar-style" {
        GtkProgressBar::yspacing = 0
        GtkProgressBar::min-horizontal-bar-height = 14
    }
    widget "*.MeldStatusBar.*.GtkProgressBar" style "meld-progressbar-style"
    """)


class MeldStatusBar(Gtk.Statusbar):
    __gtype_name__ = "MeldStatusBar"

    def __init__(self):
        GObject.GObject.__init__(self)
        self.props.spacing = 6

        if hasattr(self, "get_message_area"):
            # FIXME: added in 2.20, but not in the corresponding pyGtk. Use this if available
            hbox = self.get_message_area()
            label = hbox.get_children()[0]
        else:
            frame = self.get_children()[0]
            self.set_child_packing(frame, False, False, 0, Gtk.PACK_START)
            child = frame.get_child()
            # Internal GTK widgetry changed when get_message_area was added.
            if not isinstance(child, Gtk.HBox):
                hbox = Gtk.HBox(False, 4)
                child.reparent(hbox)
                frame.add(hbox)
                hbox.show()
                label = child
            else:
                hbox = child
                label = hbox.get_children()[0]
        hbox.props.spacing = 6
        label.props.ellipsize = Pango.EllipsizeMode.NONE

        self.progress = Gtk.ProgressBar()
        self.progress.props.pulse_step = 0.02
        self.progress.props.ellipsize = Pango.EllipsizeMode.END
        self.progress.set_size_request(200, -1)
        progress_font = self.get_style_context().get_font(
            Gtk.StateFlags.NORMAL)
        progress_font.set_size(progress_font.get_size() - 2 * Pango.SCALE)
        self.progress.modify_font(progress_font)
        hbox.pack_start(self.progress, False, True, 0)
        self.progress.show()

        hbox.remove(label)
        hbox.pack_start(label, True, True, 0)

        alignment = Gtk.Alignment.new(xalign=1.0, yalign=0.5, xscale=1.0, yscale=1.0)
        self.info_box = Gtk.HBox(False, 6)
        self.info_box.show()
        alignment.add(self.info_box)
        self.pack_start(alignment, True, True, 0)
        alignment.show()

        self.timeout_source = None

    def start_pulse(self):
        self.progress.show()
        if self.timeout_source is None:
            def pulse():
                self.progress.pulse()
                return True
            self.timeout_source = GObject.timeout_add(50, pulse)

    def stop_pulse(self):
        if self.timeout_source is not None:
            GObject.source_remove(self.timeout_source)
            self.timeout_source = None
        self.progress.set_fraction(0)
        self.progress.hide()

    def set_task_status(self, status):
        self.progress.set_text(status)

    def set_info_box(self, widgets):
        for child in self.info_box.get_children():
            self.info_box.remove(child)
        for widget in widgets:
            self.info_box.pack_end(widget, True, True, 0)
