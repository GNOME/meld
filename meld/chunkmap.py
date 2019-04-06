# Copyright (C) 2019 Kai Willadsen <kai.willadsen@gmail.com>
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

import collections
import logging
from typing import List, Mapping, Tuple

import cairo
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gtk

from meld.misc import get_common_theme
from meld.settings import meldsettings

log = logging.getLogger(__name__)


class ChunkMap(Gtk.DrawingArea):

    __gtype_name__ = "ChunkMap"

    adjustment = GObject.Property(
        type=Gtk.Adjustment,
        nick='Adjustment used for scrolling the mapped view',
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    handle_overdraw = GObject.Property(
        type=Gdk.RGBA,
        nick='Color of the document handle overdraw',
        default=Gdk.RGBA(0.0, 0.0, 0.0, 0.2)
    )

    handle_outline = GObject.Property(
        type=Gdk.RGBA,
        nick='Color of the document handle outline',
        default=Gdk.RGBA(0.0, 0.0, 0.0, 0.4)
    )

    @GObject.Property(
        type=GObject.TYPE_PYOBJECT,
        nick='Chunks defining regions in the mapped view',
    )
    def chunks(self):
        return self._chunks

    @chunks.setter
    def chunks_set(self, chunks):
        self._chunks = chunks
        self._cached_map = None

    overdraw_padding: int = 2

    def __init__(self):
        super().__init__()
        self.chunks = []
        self._have_grab = False
        self._cached_map = None

    def do_realize(self):
        if not self.adjustment:
            log.critical(
                f'{self.__gtype_name__} initialized without an adjustment')
            return Gtk.DrawingArea.do_realize(self)

        self.set_events(
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK
        )

        self.adjustment.connect('changed', lambda w: self.queue_draw())
        self.adjustment.connect('value-changed', lambda w: self.queue_draw())

        meldsettings.connect('changed', self.on_setting_changed)
        self.on_setting_changed(meldsettings, 'style-scheme')

        return Gtk.DrawingArea.do_realize(self)

    def do_size_allocate(self, *args):
        self._cached_map = None
        return Gtk.DrawingArea.do_size_allocate(self, *args)

    def on_setting_changed(self, meldsettings, key):
        if key == 'style-scheme':
            self.fill_colors, self.line_colors = get_common_theme()
            self._cached_map = None

    def chunk_coords_by_tag(self) -> Mapping[str, List[Tuple[float, float]]]:
        """Map chunks to buffer offsets for drawing, ordered by tag"""
        raise NotImplementedError()

    def do_draw(self, context: cairo.Context) -> bool:
        if not self.adjustment:
            return False

        height = self.get_allocated_height()
        width = self.get_allocated_width()

        if width <= 0 or height <= 0:
            return False

        x0 = self.overdraw_padding + 0.5
        x1 = width - 2 * x0

        if self._cached_map is None:
            surface = cairo.Surface.create_similar(
                context.get_target(), cairo.CONTENT_COLOR_ALPHA, width, height)
            cache_ctx = cairo.Context(surface)
            cache_ctx.set_line_width(1)

            # We get drawing coordinates by tag to minimise our source
            # colour setting, and make this loop slightly cleaner.
            tagged_diffs = self.chunk_coords_by_tag()

            for tag, diffs in tagged_diffs.items():
                cache_ctx.set_source_rgba(*self.fill_colors[tag])
                for y0, y1 in diffs:
                    y0, y1 = round(y0 * height) + 0.5, round(y1 * height) - 0.5
                    cache_ctx.rectangle(x0, y0, x1, y1 - y0)
                cache_ctx.fill_preserve()
                cache_ctx.set_source_rgba(*self.line_colors[tag])
                cache_ctx.stroke()

            self._cached_map = surface

        context.set_source_surface(self._cached_map, 0, 0)
        context.paint()

        # Draw our scroll position indicator
        context.set_line_width(1)
        Gdk.cairo_set_source_rgba(context, self.handle_overdraw)
        adj_y = self.adjustment.get_value() / self.adjustment.get_upper()
        adj_h = self.adjustment.get_page_size() / self.adjustment.get_upper()
        context.rectangle(
            x0 - self.overdraw_padding, round(height * adj_y) + 0.5,
            x1 + 2 * self.overdraw_padding, round(height * adj_h) - 1,
        )
        context.fill_preserve()
        Gdk.cairo_set_source_rgba(context, self.handle_outline)
        context.stroke()

        return True

    def _scroll_to_location(self, location: float):
        raise NotImplementedError()

    def _scroll_fraction(self, position: float):
        """Scroll the mapped textview to the given position

        This uses GtkTextView's scrolling so that the movement is
        animated.

        :param position: Position to scroll to, in event coordinates
        """
        if not self.adjustment:
            return

        fraction = position / self.get_allocated_height()
        adj = self.adjustment
        location = fraction * (adj.get_upper() - adj.get_lower())

        self._scroll_to_location(location)

    def do_button_press_event(self, event: Gdk.EventButton) -> bool:
        if event.button == 1:
            self._scroll_fraction(event.y)
            self.grab_add()
            self._have_grab = True
            return True

        return False

    def do_button_release_event(self, event: Gdk.EventButton) -> bool:
        if event.button == 1:
            self.grab_remove()
            self._have_grab = False
            return True

        return False

    def do_motion_notify_event(self, event: Gdk.EventMotion) -> bool:
        if self._have_grab:
            self._scroll_fraction(event.y)

        return True


class TextViewChunkMap(ChunkMap):

    __gtype_name__ = 'TextViewChunkMap'

    textview = GObject.Property(
        type=Gtk.TextView,
        nick='Textview being mapped',
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    def chunk_coords_by_tag(self):

        buf = self.textview.get_buffer()

        tagged_diffs: Mapping[str, List[Tuple[float, float]]]
        tagged_diffs = collections.defaultdict(list)

        y, h = self.textview.get_line_yrange(buf.get_end_iter())
        max_y = float(y + h)
        for chunk in self.chunks:
            start_iter = buf.get_iter_at_line(chunk.start_a)
            y0, _ = self.textview.get_line_yrange(start_iter)
            if chunk.start_a == chunk.end_a:
                y, h = y0, 0
            else:
                end_iter = buf.get_iter_at_line(chunk.end_a - 1)
                y, h = self.textview.get_line_yrange(end_iter)

            tagged_diffs[chunk.tag].append((y0 / max_y, (y + h) / max_y))

        return tagged_diffs

    def do_draw(self, context: cairo.Context) -> bool:
        if not self.textview:
            return False

        return ChunkMap.do_draw(self, context)

    def _scroll_to_location(self, location: float):
        if not self.textview:
            return

        _, it = self.textview.get_iter_at_location(0, location)
        self.textview.scroll_to_iter(it, 0.0, True, 1.0, 0.5)
