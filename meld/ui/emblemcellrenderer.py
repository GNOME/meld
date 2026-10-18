# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010, 2012-2026 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import Gdk, GObject, Graphene, Gtk

log = logging.getLogger(__name__)


class EmblemCellRenderer(Gtk.CellRenderer):
    """Custom cell renderer for drawing recoloured icons

    Contrary to the naming, this no longer supports emblems, and is only
    used to draw symbolic icons with a colour matching the comparison
    state.
    """

    __gtype_name__ = "EmblemCellRenderer"

    icon_cache: ClassVar[dict[tuple[str, int, int], Gtk.IconPaintable | None]] = {}

    icon_name = GObject.Property(
        type=str,
        nick="Named icon",
        blurb="Name for base icon",
        default="text-x-generic",
    )

    icon_size = GObject.Property(
        type=int,
        nick="Size of icon in pixels",
        default=16,
    )

    icon_tint = GObject.Property(
        type=Gdk.RGBA,
        nick="Icon tint",
        blurb="GDK-parseable color to be used to tint icon",
    )

    def _get_paintable(self, widget, name, size):
        if not name:
            return None

        scale = widget.get_scale_factor()
        key = (name, size, scale)
        if key not in self.icon_cache:
            icon_theme = Gtk.IconTheme.get_for_display(widget.get_display())
            if icon_theme.has_icon(name):
                paintable = icon_theme.lookup_icon(
                    name, None, size, scale, widget.get_direction(), 0
                )
            else:
                log.error(f"Icon {name!r} not found; an icon theme is missing")
                paintable = None

            self.icon_cache[key] = paintable

        return self.icon_cache[key]

    def do_snapshot(self, snapshot, widget, background_area, cell_area, flags):
        icon_size = min(cell_area.width, cell_area.height)
        paintable = self._get_paintable(widget, self.icon_name, icon_size)
        if not paintable:
            return

        icon_color = self.icon_tint or widget.get_color()
        height_offset = int((cell_area.height - icon_size) / 2)
        x, y = cell_area.x, cell_area.y + height_offset

        snapshot.save()
        snapshot.translate(Graphene.Point().init(x, y))
        paintable.snapshot_symbolic(snapshot, icon_size, icon_size, [icon_color])
        snapshot.restore()

    def do_get_preferred_width(self, widget):
        return (self.icon_size, self.icon_size)

    def do_get_preferred_height(self, widget):
        return (self.icon_size, self.icon_size)
