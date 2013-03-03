# This file is part of the Hotwire Shell user interface.
#
# Copyright (C) 2007,2008 Colin Walters <walters@verbum.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

import logging

import gobject
import gtk

from .wraplabel import WrapLabel

_logger = logging.getLogger("hotwire.ui.MsgArea")

# This file is a Python translation of gedit/gedit/gedit-message-area.c

class MsgArea(gtk.HBox):
    __gtype_name__ = "MsgArea"

    __gsignals__ = {
        "response" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_INT,)),
        "close" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, [])
    }

    def __init__(self, buttons, **kwargs):
        super(MsgArea, self).__init__(**kwargs)

        self.__contents = None
        self.__labels = []
        self.__changing_style = False

        self.__main_hbox = gtk.HBox(False, 16) # FIXME: use style properties
        self.__main_hbox.show()
        self.__main_hbox.set_border_width(8) # FIXME: use style properties

        self.__action_area = gtk.VBox(True, 4); # FIXME: use style properties
        self.__action_area.show()
        self.__main_hbox.pack_end (self.__action_area, False, True, 0)

        self.pack_start(self.__main_hbox, True, True, 0)

        self.set_app_paintable(True)

        self.connect("expose-event", self.__paint)

        # Note that we connect to style-set on one of the internal
        # widgets, not on the message area itself, since gtk does
        # not deliver any further style-set signals for a widget on
        # which the style has been forced with gtk_widget_set_style()
        self.__main_hbox.ensure_style()
        self.__main_hbox.connect("style-set", self.__on_style_set)

        self.add_buttons(buttons)

    def __get_response_data(self, w, create):
        d = w.get_data('hotwire-msg-area-data')
        if (d is None) and create:
            d = {'respid': None}
            w.set_data('hotwire-msg-area-data', d)
        return d

    def __find_button(self, respid):
        children = self.__actionarea.get_children()
        for child in children:
            rd = self.__get_response_data(child, False)
            if rd is not None and rd['respid'] == respid:
                return child

    def __close(self):
        cancel = self.__find_button(gtk.RESPONSE_CANCEL)
        if cancel is None:
            return
        self.response(gtk.RESPONSE_CANCEL)

    def __paint(self, w, event):
        gtk.Style.paint_flat_box(w.style,
                                 w.window,
                                 gtk.STATE_NORMAL,
                                 gtk.SHADOW_OUT,
                                 None,
                                 w,
                                 "tooltip",
                                 w.allocation.x + 1,
                                 w.allocation.y + 1,
                                 w.allocation.width - 2,
                                 w.allocation.height - 2)

        return False

    def __on_style_set(self, w, style):
        if self.__changing_style:
            return
        # This is a hack needed to use the tooltip background color
        window = gtk.Window(gtk.WINDOW_POPUP);
        window.set_name("gtk-tooltip")
        window.ensure_style()
        style = window.get_style()

        self.__changing_style = True
        self.set_style(style)
        for label in self.__labels:
            label.set_style(style)
        self.__changing_style = False

        window.destroy()

        self.queue_draw()

    def __get_response_for_widget(self, w):
        rd = self.__get_response_data(w, False)
        if rd is None:
            return gtk.RESPONSE_NONE
        return rd['respid']

    def __on_action_widget_activated(self, w):
        response_id = self.__get_response_for_widget(w)
        self.response(response_id)

    def add_action_widget(self, child, respid):
        rd = self.__get_response_data(child, True)
        rd['respid'] = respid
        if not isinstance(child, gtk.Button):
            raise ValueError("Can only pack buttons as action widgets")
        child.connect('clicked', self.__on_action_widget_activated)
        if respid != gtk.RESPONSE_HELP:
            self.__action_area.pack_start(child, False, False, 0)
        else:
            self.__action_area.pack_end(child, False, False, 0)

    def set_contents(self, contents):
        self.__contents = contents
        self.__main_hbox.pack_start(contents, True, True, 0)


    def add_button(self, btext, respid):
        button = gtk.Button(stock=btext)
        button.set_focus_on_click(False)
        button.set_flags(gtk.CAN_DEFAULT)
        button.show()
        self.add_action_widget(button, respid)
        return button

    def add_buttons(self, args):
        _logger.debug("init buttons: %r", args)
        for (btext, respid) in args:
            self.add_button(btext, respid)

    def set_response_sensitive(self, respid, setting):
        for child in self.__action_area.get_children():
            rd = self.__get_response_data(child, False)
            if rd is not None and rd['respid'] == respid:
                child.set_sensitive(setting)
                break

    def set_default_response(self, respid):
        for child in self.__action_area.get_children():
            rd = self.__get_response_data(child, False)
            if rd is not None and rd['respid'] == respid:
                child.grab_default()
                break

    def response(self, respid):
        self.emit('response', respid)

    def add_stock_button_with_text(self, text, stockid, respid):
        b = gtk.Button(label=text)
        b.set_focus_on_click(False)
        img = gtk.Image()
        img.set_from_stock(stockid, gtk.ICON_SIZE_BUTTON)
        b.set_image(img)
        b.show_all()
        self.add_action_widget(b, respid)
        return b

    def set_text_and_icon(self, stockid, primary_text, secondary_text=None):
        hbox_content = gtk.HBox(False, 8)
        hbox_content.show()

        image = gtk.Image()
        image.set_from_stock(stockid, gtk.ICON_SIZE_DIALOG)
        image.show()
        hbox_content.pack_start(image, False, False, 0)
        image.set_alignment(0.5, 0.5)

        vbox = gtk.VBox(False, 6)
        vbox.show()
        hbox_content.pack_start (vbox, True, True, 0)

        self.__labels = []

        primary_markup = "<b>%s</b>" % (primary_text,)
        primary_label = WrapLabel(primary_markup)
        primary_label.show()
        vbox.pack_start(primary_label, True, True, 0)
        primary_label.set_use_markup(True)
        primary_label.set_line_wrap(True)
        primary_label.set_alignment(0, 0.5)
        primary_label.set_flags(gtk.CAN_FOCUS)
        primary_label.set_selectable(True)
        self.__labels.append(primary_label)

        if secondary_text:
            secondary_markup = "<small>%s</small>" % (secondary_text,)
            secondary_label = WrapLabel(secondary_markup)
            secondary_label.show()
            vbox.pack_start(secondary_label, True, True, 0)
            secondary_label.set_flags(gtk.CAN_FOCUS)
            secondary_label.set_use_markup(True)
            secondary_label.set_line_wrap(True)
            secondary_label.set_selectable(True)
            secondary_label.set_alignment(0, 0.5)
            self.__labels.append(secondary_label)

        self.set_contents(hbox_content)

class MsgAreaController(gtk.HBox):
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

    def new_from_text_and_icon(self, stockid, primary, secondary=None, buttons=[]):
        self.clear()
        msgarea = self.__msgarea = MsgArea(buttons)
        msgarea.set_text_and_icon(stockid, primary, secondary)
        self.pack_start(msgarea, expand=True)
        return msgarea
