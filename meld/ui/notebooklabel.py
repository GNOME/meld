# Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2008-2009, 2013, 2019 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import Gdk, GObject, Gtk


@Gtk.Template(resource_path='/org/gnome/meld/ui/notebook-label.ui')
class NotebookLabel(Gtk.EventBox):

    __gtype_name__ = 'NotebookLabel'

    label = Gtk.Template.Child()

    label_text = GObject.Property(
        type=str,
        nick='Text of this notebook label',
        default='',
    )

    page = GObject.Property(
        type=object,
        nick='Notebook page for which this is the label',
        default=None,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.bind_property(
            'label-text', self.label, 'label',
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
        )
        self.bind_property(
            'label-text', self, 'tooltip-text',
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
        )

    @Gtk.Template.Callback()
    def on_label_button_press_event(self, widget, event):
        # Middle-click on the tab closes the tab.
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 2:
            self.page.on_delete_event()

    @Gtk.Template.Callback()
    def on_close_button_clicked(self, widget):
        self.page.on_delete_event()
