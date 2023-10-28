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

from typing import Optional

from gi.repository import Gtk, Pango

from meld.conf import _


def layout_text_and_icon(
    primary_text: str,
    secondary_text: Optional[str] = None,
    icon_name: Optional[str] = None,
):
    hbox_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

    if icon_name:
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        image.set_alignment(0.5, 0.5)
        hbox_content.pack_start(image, False, False, 0)

    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

    primary_label = Gtk.Label(
        label="<b>{}</b>".format(primary_text),
        wrap=True,
        wrap_mode=Pango.WrapMode.WORD_CHAR,
        use_markup=True,
        xalign=0,
        can_focus=True,
        selectable=True,
    )
    vbox.pack_start(primary_label, True, True, 0)

    if secondary_text:
        secondary_label = Gtk.Label(
            "<small>{}</small>".format(secondary_text),
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD,
            use_markup=True,
            xalign=0,
            can_focus=True,
            selectable=True,
        )
        vbox.pack_start(secondary_label, True, True, 0)

    hbox_content.pack_start(vbox, True, True, 0)
    hbox_content.show_all()
    return hbox_content


class MsgAreaController(Gtk.Box):
    __gtype_name__ = "MsgAreaController"

    def __init__(self):
        super().__init__()

        self.__msgarea = None
        self.__msgid = None

        self.props.orientation = Gtk.Orientation.HORIZONTAL

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

    def new_from_text_and_icon(
        self,
        primary: str,
        secondary: Optional[str] = None,
        icon_name: Optional[str] = None,
    ):
        self.clear()
        msgarea = self.__msgarea = Gtk.InfoBar()

        content = layout_text_and_icon(primary, secondary, icon_name)

        content_area = msgarea.get_content_area()
        content_area.foreach(content_area.remove, None)
        content_area.add(content)

        action_area = msgarea.get_action_area()
        action_area.set_orientation(Gtk.Orientation.VERTICAL)

        self.pack_start(msgarea, True, True, 0)
        return msgarea

    def add_dismissable_msg(self, icon, primary, secondary, close_panes=None):
        def clear_all(*args):
            if close_panes:
                for pane in close_panes:
                    pane.clear()
            else:
                self.clear()
        msgarea = self.new_from_text_and_icon(primary, secondary, icon)
        msgarea.add_button(_("Hi_de"), Gtk.ResponseType.CLOSE)
        msgarea.connect("response", clear_all)
        msgarea.show_all()
        return msgarea

    def add_action_msg(self, icon, primary, secondary, action_label, callback):
        def on_response(msgarea, response_id, *args):
            self.clear()
            if response_id == Gtk.ResponseType.ACCEPT:
                callback()

        msgarea = self.new_from_text_and_icon(primary, secondary, icon)
        msgarea.add_button(action_label, Gtk.ResponseType.ACCEPT)
        msgarea.add_button(_("Hi_de"), Gtk.ResponseType.CLOSE)
        msgarea.connect("response", on_response)
        msgarea.show_all()
        return msgarea
