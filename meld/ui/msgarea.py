# This file is part of the Hotwire Shell user interface.
#
# Copyright (C) 2007,2008 Colin Walters <walters@verbum.org>
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
#
# Additional modifications made for use in Meld and adaptations for
# newer GTK+.
# Copyright (C) 2013 Kai Willadsen <kai.willadsen@gmail.com>

from gi.repository import Gtk

from meld.conf import _
from meld.ui.wraplabel import WrapLabel


def layout_text_and_icon(stockid, primary_text, secondary_text=None):
    hbox_content = Gtk.HBox(homogeneous=False, spacing=8)
    hbox_content.show()

    image = Gtk.Image.new_from_icon_name(stockid, Gtk.IconSize.DIALOG)
    image.show()
    hbox_content.pack_start(image, False, False, 0)
    image.set_alignment(0.5, 0.5)

    vbox = Gtk.VBox(homogeneous=False, spacing=6)
    vbox.show()
    hbox_content.pack_start(vbox, True, True, 0)

    primary_markup = "<b>%s</b>" % (primary_text,)
    primary_label = WrapLabel(primary_markup)
    primary_label.show()
    vbox.pack_start(primary_label, True, True, 0)
    primary_label.set_use_markup(True)
    primary_label.set_line_wrap(True)
    primary_label.set_alignment(0, 0.5)
    primary_label.set_can_focus(True)
    primary_label.set_selectable(True)

    if secondary_text:
        secondary_markup = "<small>%s</small>" % (secondary_text,)
        secondary_label = WrapLabel(secondary_markup)
        secondary_label.show()
        vbox.pack_start(secondary_label, True, True, 0)
        secondary_label.set_can_focus(True)
        secondary_label.set_use_markup(True)
        secondary_label.set_line_wrap(True)
        secondary_label.set_selectable(True)
        secondary_label.set_alignment(0, 0.5)

    return hbox_content


class MsgAreaController(Gtk.HBox):
    __gtype_name__ = "MsgAreaController"

    def __init__(self):
        super(MsgAreaController, self).__init__()

        self.__msgarea = None
        self.__msgid = None

    def has_message(self):
        return self.__msgarea is not None

    def get_msg_id(self):
        return self.__msgid

    def set_msg_id(self, msgid):
        self.__msgid = msgid

    def clear(self):
        if self.__msgarea is not None:
            self.remove(self.__msgarea)
            self.__msgarea.destroy()
            self.__msgarea = None
        self.__msgid = None

    def new_from_text_and_icon(self, stockid, primary, secondary=None,
                               buttons=[]):
        self.clear()
        msgarea = self.__msgarea = Gtk.InfoBar()

        for (text, respid) in buttons:
            self.add_button(text, respid)

        content = layout_text_and_icon(stockid, primary, secondary)

        content_area = msgarea.get_content_area()
        content_area.foreach(content_area.remove, None)
        content_area.add(content)

        self.pack_start(msgarea, True, True, 0)
        return msgarea

    def add_dismissable_msg(self, icon, primary, secondary):
        msgarea = self.new_from_text_and_icon(icon, primary, secondary)
        msgarea.add_button(_("Hi_de"), Gtk.ResponseType.CLOSE)
        msgarea.connect("response", lambda *args: self.clear())
        msgarea.show_all()
        return msgarea

    def add_action_msg(self, icon, primary, secondary, action_label, callback):
        def on_response(msgarea, response_id, *args):
            self.clear()
            if response_id == Gtk.ResponseType.ACCEPT:
                callback()

        msgarea = self.new_from_text_and_icon(icon, primary, secondary)
        msgarea.add_button(action_label, Gtk.ResponseType.ACCEPT)
        msgarea.add_button(_("Hi_de"), Gtk.ResponseType.CLOSE)
        msgarea.connect("response", on_response)
        msgarea.show_all()
        return msgarea
