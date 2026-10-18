# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010, 2012-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

import logging
from typing import ClassVar

import cairo
from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Graphene, Gtk

log = logging.getLogger(__name__)


class EmblemCellRenderer(Gtk.CellRenderer):
    __gtype_name__ = "EmblemCellRenderer"

    icon_cache: ClassVar[dict[tuple[str, int], GdkPixbuf.Pixbuf]] = {}

    icon_name = GObject.Property(
        type=str,
        nick="Named icon",
        blurb="Name for base icon",
        default="text-x-generic",
    )

    emblem_name = GObject.Property(
        type=str,
        nick="Named emblem icon",
        blurb="Name for emblem icon to overlay",
    )

    icon_tint = GObject.Property(
        type=Gdk.RGBA,
        nick="Icon tint",
        blurb="GDK-parseable color to be used to tint icon",
    )

    def __init__(self):
        super().__init__()
        self._state = None
        # FIXME: hardcoded sizes
        self._icon_size = 16
        self._emblem_size = 8

    def _get_pixbuf(self, widget, name, size):
        if not name:
            return None

        if (name, size) not in self.icon_cache:
            icon_theme = Gtk.IconTheme.get_for_display(widget.get_display())
            pixbuf = None
            if icon_theme.has_icon(name):
                paintable = icon_theme.lookup_icon(
                    name, None, size, 1, Gtk.TextDirection.NONE, 0
                )
                icon_file = paintable.get_file()
                try:
                    stream = icon_file.read(None)
                    pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                        stream, size, size, True, None
                    )
                except GLib.Error as err:
                    log.error(f"Icon {name!r} could not be loaded: {err.message}")
            else:
                log.error(f"Icon {name!r} not found; an icon theme is missing")

            self.icon_cache[(name, size)] = pixbuf

        return self.icon_cache[(name, size)]

    def do_snapshot(self, snapshot, widget, background_area, cell_area, flags):
        bounds = Graphene.Rect().init(
            cell_area.x, cell_area.y, cell_area.width, cell_area.height
        )
        context = snapshot.append_cairo(bounds)
        context.translate(cell_area.x, cell_area.y)
        context.rectangle(0, 0, cell_area.width, cell_area.height)
        context.clip()

        # TODO: Incorporate padding
        context.push_group()
        pixbuf = self._get_pixbuf(widget, self.icon_name, self._icon_size)
        if pixbuf:
            context.set_operator(cairo.OPERATOR_SOURCE)
            # Assumes square icons; may break if we don't get the requested
            # size
            height_offset = int((cell_area.height - pixbuf.get_height()) / 2)
            Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, height_offset)
            context.rectangle(0, height_offset, pixbuf.get_width(), pixbuf.get_height())
            context.fill()

            if self.icon_tint:
                c = self.icon_tint
                r, g, b = c.red, c.green, c.blue
                # Figure out the difference between our tint colour and an
                # empirically determined (i.e., guessed) satisfying luma and
                # adjust the base colours accordingly
                luma = (r + r + b + g + g + g) / 6.0
                extra_luma = (1.2 - luma) / 3.0
                r, g, b = [min(x + extra_luma, 1.0) for x in (r, g, b)]
                context.set_source_rgba(r, g, b, 0.4)
                context.set_operator(cairo.OPERATOR_ATOP)
                context.paint()

            if self.emblem_name:
                pixbuf = self._get_pixbuf(widget, self.emblem_name, self._emblem_size)
                if pixbuf:
                    x_offset = self._icon_size - self._emblem_size
                    context.set_operator(cairo.OPERATOR_OVER)
                    Gdk.cairo_set_source_pixbuf(context, pixbuf, x_offset, 0)
                    context.rectangle(x_offset, 0, cell_area.width, self._emblem_size)
                    context.fill()

        context.pop_group_to_source()
        context.set_operator(cairo.OPERATOR_OVER)
        context.paint()

    def do_get_preferred_width(self, widget):
        # TODO: Account for padding
        return (self._icon_size, self._icon_size)

    def do_get_preferred_height(self, widget):
        # TODO: Account for padding
        return (self._icon_size, self._icon_size)
