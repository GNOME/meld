### Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2008-2009 Kai Willadsen <kai.willadsen@gmail.com>

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


from gettext import gettext as _

import gtk
import pango

gtk.rc_parse_string(
    """
    style "meld-tab-close-button-style" {
        GtkWidget::focus-padding = 0
        GtkWidget::focus-line-width = 0
        xthickness = 0
        ythickness = 0
    }
    widget "*.meld-tab-close-button" style "meld-tab-close-button-style"
    """)

class NotebookLabel(gtk.HBox):
    __gtype_name__ = "NotebookLabel"

    tab_width_in_chars = 30

    def __init__(self, iconname, text, onclose):
        gtk.HBox.__init__(self, False, 4)

        label = gtk.Label(text)
        # FIXME: ideally, we would use custom ellipsization that ellipsized the
        # two paths separately, but that requires significant changes to label
        # generation in many different parts of the code
        label.set_ellipsize(pango.ELLIPSIZE_MIDDLE)
        label.set_single_line_mode(True)
        label.set_alignment(0.0, 0.5)
        label.set_padding(0, 0)

        context = self.get_pango_context()
        metrics = context.get_metrics(self.style.font_desc, context.get_language())
        char_width = metrics.get_approximate_digit_width()
        (w, h) = gtk.icon_size_lookup_for_settings (self.get_settings(), gtk.ICON_SIZE_MENU)
        self.set_size_request(self.tab_width_in_chars * pango.PIXELS(char_width) + 2 * w, -1)

        button = gtk.Button()
        button.set_relief(gtk.RELIEF_NONE)
        button.set_focus_on_click(False)
        image = gtk.image_new_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)
        image.set_tooltip_text(_("Close tab"))
        button.add(image)
        button.set_name("meld-tab-close-button")
        button.set_size_request(w + 2, h + 2)
        button.connect("clicked", onclose)

        icon = gtk.image_new_from_icon_name(iconname, gtk.ICON_SIZE_MENU)

        label_box = gtk.EventBox()
        label_box.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        label_box.props.visible_window = False
        label_box.connect("button-press-event", self.on_label_clicked)
        label_box.add(label)

        self.pack_start(icon, expand=False)
        self.pack_start(label_box)
        self.pack_start(button, expand=False)
        self.set_tooltip_text(text)
        self.show_all()

        self.__label = label
        self.__onclose = onclose

    def on_label_clicked(self, box, event):
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 2:
            self.__onclose(None)

    def get_label_text(self):
        return self.__label.get_text()

    def set_label_text(self, text):
        self.__label.set_text(text)
        self.set_tooltip_text(text)

