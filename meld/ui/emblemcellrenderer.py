### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2010 Kai Willadsen <kai.willadsen@gmail.com>

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

import cairo
import gobject
import gtk


class EmblemCellRenderer(gtk.GenericCellRenderer):

    __gproperties__ = {
        "icon-name":   (str, "Named icon",
                        "Name for base icon",
                        "text-x-generic", gobject.PARAM_READWRITE),
        "emblem-name": (str, "Named emblem icon",
                        "Name for emblem icon to overlay",
                        None, gobject.PARAM_READWRITE),
        "icon-tint":   (str, "Icon tint",
                        "GDK-parseable color to be used to tint icon",
                        None, gobject.PARAM_READWRITE),
    }

    def __init__(self):
        self.__gobject_init__()
        self._icon_name = "text-x-generic"
        self._emblem_name = None
        self._icon_tint = None
        self._tint_color = None
        self._state = None
        # FIXME: hardcoded sizes
        self._icon_size = 16
        self._emblem_size = 8

    def do_set_property(self, pspec, value):
        if pspec.name == "icon-name":
            self._icon_name = value
        elif pspec.name == "emblem-name":
            self._emblem_name = value
        elif pspec.name == "icon-tint":
            self._icon_tint = value
            if self._icon_tint:
                self._tint_color = gtk.gdk.color_parse(value)
            else:
                self._tint_color = None
        else:
            raise AttributeError("unknown property %s" % pspec.name)

    def do_get_property(self, pspec):
        if pspec.name == "icon-name":
            return self._icon_name
        elif pspec.name == "emblem-name":
            return self._emblem_name
        elif pspec.name == "icon-tint":
            return self._icon_tint
        else:
            raise AttributeError("unknown property %s" % pspec.name)

    def on_render(self, window, widget, background_area, cell_area,
                  expose_area, flags):
        context = window.cairo_create()
        context.translate(cell_area.x, cell_area.y)
        context.rectangle(0, 0, cell_area.width, cell_area.height)
        context.clip()

        # TODO: Incorporate padding
        context.push_group()
        if self._icon_name:
            icon_theme = gtk.icon_theme_get_default()
            # Assumes square icons; may break if we don't get the requested size
            pixbuf = icon_theme.load_icon(self._icon_name,
                                          self._icon_size, 0).copy() # FIXME: copy?

            context.set_operator(cairo.OPERATOR_SOURCE)
            context.set_source_pixbuf(pixbuf, 0, 0)
            context.rectangle(0, 0, cell_area.width, cell_area.height)
            context.fill()

            if self._tint_color:
                c = self._tint_color
                r, g, b = [x / 65535. for x in (c.red, c.green, c.blue)]
                # Figure out the difference between our tint colour and an
                # empirically determined (i.e., guessed) satisfying luma and
                # adjust the base colours accordingly
                luma = (r + r + b + g + g + g) / 6.
                extra_luma = (1.2 - luma) / 3.
                r, g, b = [min(x + extra_luma, 1.) for x in (r, g, b)]
                context.set_source_rgba(r, g, b, 0.4)
                context.set_operator(cairo.OPERATOR_ATOP)
                context.paint()

            if self._emblem_name:
                emblem_pixbuf = icon_theme.load_icon(self._emblem_name,
                                                     self._emblem_size, 0)

                x_offset = self._icon_size - self._emblem_size
                context.set_operator(cairo.OPERATOR_OVER)
                context.set_source_pixbuf(emblem_pixbuf, x_offset, 0)
                context.rectangle(x_offset, 0,
                                  cell_area.width, self._emblem_size)
                context.fill()

        context.set_source(context.pop_group())
        context.set_operator(cairo.OPERATOR_OVER)
        context.paint()

    def on_get_size(self, widget, cell_area):
        # TODO: Account for cell_area if we have alignment set
        x_offset, y_offset = 0, 0
        width, height = self._icon_size, self._icon_size
        # TODO: Account for padding
        return (x_offset, y_offset, width, height)
