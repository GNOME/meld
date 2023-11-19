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
from typing import Any, List, Mapping, Tuple

import cairo
from gi.repository import Gdk, GObject, Gtk

from meld.settings import get_meld_settings
from meld.style import get_common_theme
from meld.tree import STATE_ERROR, STATE_MODIFIED, STATE_NEW
from meld.ui.gtkutil import make_gdk_rgba

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

    handle_overdraw_alpha = GObject.Property(
        type=float,
        nick='Alpha of the document handle overdraw',
        default=0.2,
    )

    handle_outline_alpha = GObject.Property(
        type=float,
        nick='Alpha of the document handle outline',
        default=0.4,
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
        self.queue_draw()

    overdraw_padding: int = 2

    def __init__(self):
        super().__init__()
        self.chunks = []
        self._have_grab = False
        self._cached_map = None

        self.click_controller = Gtk.GestureMultiPress(widget=self)
        self.click_controller.connect("pressed", self.button_press_event)
        self.click_controller.connect("released", self.button_release_event)

        self.motion_controller = Gtk.EventControllerMotion(widget=self)
        self.motion_controller.set_propagation_phase(Gtk.PropagationPhase.TARGET)
        self.motion_controller.connect("motion", self.motion_event)

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

        meld_settings = get_meld_settings()
        meld_settings.connect('changed', self.on_setting_changed)
        self.on_setting_changed(meld_settings, 'style-scheme')

        return Gtk.DrawingArea.do_realize(self)

    def do_size_allocate(self, *args):
        self._cached_map = None
        return Gtk.DrawingArea.do_size_allocate(self, *args)

    def on_setting_changed(self, settings, key):
        if key == 'style-scheme':
            self.fill_colors, self.line_colors = get_common_theme()
            self._cached_map = None

    def get_height_scale(self) -> float:
        return 1.0

    def get_map_base_colors(
            self) -> Tuple[Gdk.RGBA, Gdk.RGBA, Gdk.RGBA, Gdk.RGBA]:
        raise NotImplementedError()

    def _make_map_base_colors(
            self, widget) -> Tuple[Gdk.RGBA, Gdk.RGBA, Gdk.RGBA, Gdk.RGBA]:
        stylecontext = widget.get_style_context()
        base_set, base = (
            stylecontext.lookup_color('theme_base_color'))
        if not base_set:
            base = make_gdk_rgba(1.0, 1.0, 1.0, 1.0)
        text_set, text = (
            stylecontext.lookup_color('theme_text_color'))
        if not text_set:
            base = make_gdk_rgba(0.0, 0.0, 0.0, 1.0)
        border_set, border = (
            stylecontext.lookup_color('borders'))
        if not border_set:
            base = make_gdk_rgba(0.95, 0.95, 0.95, 1.0)

        handle_overdraw = text.copy()
        handle_overdraw.alpha = self.handle_overdraw_alpha
        handle_outline = text.copy()
        handle_outline.alpha = self.handle_outline_alpha

        return base, border, handle_overdraw, handle_outline

    def chunk_coords_by_tag(self) -> Mapping[str, List[Tuple[float, float]]]:
        """Map chunks to buffer offsets for drawing, ordered by tag"""
        raise NotImplementedError()

    def do_draw(self, context: cairo.Context) -> bool:
        if not self.adjustment or self.adjustment.get_upper() <= 0:
            return False

        height = self.get_allocated_height()
        width = self.get_allocated_width()

        if width <= 0 or height <= 0:
            return False

        base_bg, base_outline, handle_overdraw, handle_outline = (
            self.get_map_base_colors())

        x0 = self.overdraw_padding + 0.5
        x1 = width - 2 * x0
        height_scale = height * self.get_height_scale()

        if self._cached_map is None:
            surface = cairo.Surface.create_similar(
                context.get_target(), cairo.CONTENT_COLOR_ALPHA, width, height)
            cache_ctx = cairo.Context(surface)
            cache_ctx.set_line_width(1)

            cache_ctx.rectangle(x0, -0.5, x1, height_scale + 0.5)
            Gdk.cairo_set_source_rgba(cache_ctx, base_bg)
            cache_ctx.fill()

            # We get drawing coordinates by tag to minimise our source
            # colour setting, and make this loop slightly cleaner.
            tagged_diffs = self.chunk_coords_by_tag()

            for tag, diffs in tagged_diffs.items():
                Gdk.cairo_set_source_rgba(cache_ctx, self.fill_colors[tag])
                for y0, y1 in diffs:
                    y0 = round(y0 * height_scale) + 0.5
                    y1 = round(y1 * height_scale) - 0.5
                    cache_ctx.rectangle(x0, y0, x1, y1 - y0)
                cache_ctx.fill_preserve()
                Gdk.cairo_set_source_rgba(cache_ctx, self.line_colors[tag])
                cache_ctx.stroke()

            cache_ctx.rectangle(x0, -0.5, x1, height_scale + 0.5)
            Gdk.cairo_set_source_rgba(cache_ctx, base_outline)
            cache_ctx.stroke()

            self._cached_map = surface

        context.set_source_surface(self._cached_map, 0, 0)
        context.paint()

        # Draw our scroll position indicator
        context.set_line_width(1)
        Gdk.cairo_set_source_rgba(context, handle_overdraw)

        adj_y = self.adjustment.get_value() / self.adjustment.get_upper()
        adj_h = self.adjustment.get_page_size() / self.adjustment.get_upper()

        context.rectangle(
            x0 - self.overdraw_padding, round(height_scale * adj_y) + 0.5,
            x1 + 2 * self.overdraw_padding, round(height_scale * adj_h) - 1,
        )
        context.fill_preserve()
        Gdk.cairo_set_source_rgba(context, handle_outline)
        context.stroke()

        return True

    def _scroll_to_location(self, location: float, animate: bool):
        raise NotImplementedError()

    def _scroll_fraction(self, position: float, *, animate: bool = True):
        """Scroll the mapped textview to the given position

        This uses GtkTextView's scrolling so that the movement is
        animated.

        :param position: Position to scroll to, in event coordinates
        """
        if not self.adjustment:
            return

        height = self.get_height_scale() * self.get_allocated_height()
        fraction = position / height
        adj = self.adjustment
        location = fraction * (adj.get_upper() - adj.get_lower())

        self._scroll_to_location(location, animate)

    def button_press_event(
        self,
        controller: Gtk.GestureMultiPress,
        npress: int,
        x: float,
        y: float,
    ) -> None:
        self._scroll_fraction(y)
        self.grab_add()
        self._have_grab = True

    def button_release_event(
        self,
        controller: Gtk.GestureMultiPress,
        npress: int,
        x: float,
        y: float,
    ) -> bool:
        self.grab_remove()
        self._have_grab = False

    def motion_event(
        self,
        controller: Gtk.EventControllerMotion,
        x: float | None = None,
        y: float | None = None,
    ):
        if self._have_grab:
            self._scroll_fraction(y, animate=False)

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

    paired_adjustment_1 = GObject.Property(
        type=Gtk.Adjustment,
        nick='Paired adjustment used for scaling the map',
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    paired_adjustment_2 = GObject.Property(
        type=Gtk.Adjustment,
        nick='Paired adjustment used for scaling the map',
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    def do_realize(self):

        def force_redraw(*args: Any) -> None:
            self._cached_map = None
            self.queue_draw()

        self.textview.connect("notify::wrap-mode", force_redraw)
        return ChunkMap.do_realize(self)

    def get_height_scale(self):
        adjustments = [
            self.props.adjustment,
            self.props.paired_adjustment_1,
            self.props.paired_adjustment_2,
        ]
        heights = [
            adj.get_upper() for adj in adjustments
            if adj.get_upper() > 0
        ]
        return self.props.adjustment.get_upper() / max(heights)

    def get_map_base_colors(self):
        return self._make_map_base_colors(self.textview)

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

    def _scroll_to_location(self, location: float, animate: bool):
        if not self.textview:
            return

        _, it = self.textview.get_iter_at_location(0, location)
        if animate:
            self.textview.scroll_to_iter(it, 0.0, True, 1.0, 0.5)
        else:
            # TODO: Add handling for centreing adjustment like we do
            # for animated scroll above.
            self.adjustment.set_value(location)


class TreeViewChunkMap(ChunkMap):

    __gtype_name__ = 'TreeViewChunkMap'

    treeview = GObject.Property(
        type=Gtk.TreeView,
        nick='Treeview being mapped',
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    treeview_idx = GObject.Property(
        type=int,
        nick='Index of the Treeview within the store',
        flags=(
            GObject.ParamFlags.READWRITE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
    )

    chunk_type_map = {
        STATE_NEW: "insert",
        STATE_ERROR: "error",
        STATE_MODIFIED: "replace",
    }

    def __init__(self):
        super().__init__()
        self.model_signal_ids = []

    def do_realize(self):
        self.treeview.connect('row-collapsed', self.clear_cached_map)
        self.treeview.connect('row-expanded', self.clear_cached_map)
        self.treeview.connect('notify::model', self.connect_model)
        self.connect_model()

        return ChunkMap.do_realize(self)

    def connect_model(self, *args):
        for model, signal_id in self.model_signal_ids:
            model.disconnect(signal_id)

        model = self.treeview.get_model()
        self.model_signal_ids = [
            (model, model.connect('row-changed', self.clear_cached_map)),
            (model, model.connect('row-deleted', self.clear_cached_map)),
            (model, model.connect('row-inserted', self.clear_cached_map)),
            (model, model.connect('rows-reordered', self.clear_cached_map)),
        ]

    def clear_cached_map(self, *args):
        self._cached_map = None

    def get_map_base_colors(self):
        return self._make_map_base_colors(self.treeview)

    def chunk_coords_by_tag(self):
        def recurse_tree_states(rowiter):
            row_states.append(
                model.get_state(rowiter.iter, self.treeview_idx))
            if self.treeview.row_expanded(rowiter.path):
                for row in rowiter.iterchildren():
                    recurse_tree_states(row)

        row_states = []
        model = self.treeview.get_model()
        recurse_tree_states(next(iter(model)))
        # Terminating mark to force the last chunk to be added
        row_states.append(None)

        tagged_diffs: Mapping[str, List[Tuple[float, float]]]
        tagged_diffs = collections.defaultdict(list)

        numlines = len(row_states) - 1
        chunkstart, laststate = 0, row_states[0]
        for index, state in enumerate(row_states):
            if state != laststate:
                action = self.chunk_type_map.get(laststate)
                if action is not None:
                    chunk = (chunkstart / numlines, index / numlines)
                    tagged_diffs[action].append(chunk)
                chunkstart, laststate = index, state

        return tagged_diffs

    def do_draw(self, context: cairo.Context) -> bool:
        if not self.treeview:
            return False

        return ChunkMap.do_draw(self, context)

    def _scroll_to_location(self, location: float, animate: bool):
        if not self.treeview or self.adjustment.get_upper() <= 0:
            return

        location -= self.adjustment.get_page_size() / 2
        if animate:
            self.treeview.scroll_to_point(-1, location)
        else:
            self.adjustment.set_value(location)
