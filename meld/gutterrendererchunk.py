# Copyright (C) 2013-2014 Kai Willadsen <kai.willadsen@gmail.com>
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

import math
from typing import Any

from gi.repository import Gdk, GtkSource, Pango

from meld.settings import get_meld_settings
from meld.style import get_common_theme
from meld.ui.gtkutil import make_gdk_rgba


def get_background_rgba(renderer):
    '''Get and cache the expected background for the renderer widget

    Current versions of GTK+ don't paint the background of text view
    gutters with the actual expected widget background, which causes
    them to look wrong when put next to any other widgets. This hack
    just gets the background from the renderer's view, and then caches
    it for performance, and on the basis that all renderers will be
    assigned to similarly-styled views. This is fragile, but the
    alternative is really significantly slower.
    '''
    global _background_rgba
    if _background_rgba is None:
        if renderer.props.view:
            stylecontext = renderer.props.view.get_style_context()
            background_set, _background_rgba = (
                stylecontext.lookup_color('theme_bg_color'))
    return _background_rgba


_background_rgba = None


class MeldGutterRenderer:

    def set_renderer_defaults(self):
        self.set_alignment_mode(GtkSource.GutterRendererAlignmentMode.FIRST)
        self.props.xpad = 3
        self.props.ypad = 0
        self.props.xalign = 0.5
        self.props.yalign = 0.5

    def on_setting_changed(self, settings, key):
        if key == 'style-scheme':
            self.fill_colors, self.line_colors = get_common_theme()
            alpha = self.fill_colors['current-chunk-highlight'].alpha
            self.chunk_highlights = {
                state: make_gdk_rgba(*[alpha + c * (1.0 - alpha) for c in colour])
                for state, colour in self.fill_colors.items()
            }

    def draw_chunks(
            self, context, background_area, cell_area, start, end, state):

        chunk = self._chunk
        if not chunk:
            return

        line = start.get_line()
        is_first_line = line == chunk[1]
        is_last_line = line == chunk[2] - 1
        if not (is_first_line or is_last_line):
            # Only paint for the first and last lines of a chunk
            return

        x = background_area.x - 1
        y = background_area.y
        width = background_area.width + 2
        height = 1 if chunk[1] == chunk[2] else background_area.height

        context.set_line_width(1.0)
        Gdk.cairo_set_source_rgba(context, self.line_colors[chunk[0]])
        if is_first_line:
            context.move_to(x, y + 0.5)
            context.rel_line_to(width, 0)
        if is_last_line:
            context.move_to(x, y - 0.5 + height)
            context.rel_line_to(width, 0)
        context.stroke()

    def query_chunks(self, start, end, state):
        line = start.get_line()
        chunk_index = self.linediffer.locate_chunk(self.from_pane, line)[0]
        in_chunk = chunk_index is not None

        chunk = None
        if in_chunk:
            chunk = self.linediffer.get_chunk(
                chunk_index, self.from_pane, self.to_pane)

        if chunk is not None:
            if chunk[1] == chunk[2]:
                background_rgba = get_background_rgba(self)
            elif self.props.view.current_chunk_check(chunk):
                background_rgba = self.chunk_highlights[chunk[0]]
            else:
                background_rgba = self.fill_colors[chunk[0]]
        else:
            # TODO: Remove when fixed in upstream GTK+
            background_rgba = get_background_rgba(self)
        self._chunk = chunk
        self.set_background(background_rgba)
        return in_chunk


# GutterRendererChunkLines is an adaptation of GtkSourceGutterRendererLines
# Copyright (C) 2010 - Jesse van den Kieboom
#
# Python reimplementation is Copyright (C) 2015 Kai Willadsen


class GutterRendererChunkLines(
        GtkSource.GutterRendererText, MeldGutterRenderer):
    __gtype_name__ = "GutterRendererChunkLines"

    def __init__(self, from_pane, to_pane, linediffer):
        super().__init__()
        self.set_renderer_defaults()
        self.from_pane = from_pane
        self.to_pane = to_pane
        # FIXME: Don't pass in the linediffer; pass a generator like elsewhere
        self.linediffer = linediffer

        self.num_line_digits = 0
        self.changed_handler_id = None

        meld_settings = get_meld_settings()
        meld_settings.connect('changed', self.on_setting_changed)
        self.font_string = meld_settings.font.to_string()
        self.on_setting_changed(meld_settings, 'style-scheme')

        self.connect("notify::view", self.on_view_changed)

    def on_view_changed(self, *args: Any) -> None:
        if not self.get_view():
            return

        self.get_view().connect("style-updated", self.on_view_style_updated)

    def on_view_style_updated(self, view: GtkSource.View) -> None:
        stylecontext = view.get_style_context()
        # We should be using stylecontext.get_property, but it doesn't work
        # for reasons that according to the GTK code are "Yuck".
        font = stylecontext.get_font(stylecontext.get_state())
        font_string = font.to_string()
        need_recalculate = font_string != self.font_string

        buf = self.get_view().get_buffer()
        self.font_string = font_string
        self.recalculate_size(buf, force=need_recalculate)

    def do_change_buffer(self, old_buffer):
        if old_buffer:
            old_buffer.disconnect(self.changed_handler_id)

        view = self.get_view()
        if view:
            buf = view.get_buffer()
            if buf:
                self.changed_handler_id = buf.connect(
                    "changed", self.recalculate_size)
                self.recalculate_size(buf)

    def _measure_markup(self, markup):
        layout = self.get_view().create_pango_layout()
        layout.set_markup(markup)
        w, h = layout.get_size()
        return w / Pango.SCALE, h / Pango.SCALE

    def recalculate_size(
        self,
        buf: GtkSource.Buffer,
        force: bool = False,
    ) -> None:

        # Always calculate display size for at least two-digit line counts
        num_lines = max(buf.get_line_count(), 99)
        num_digits = int(math.ceil(math.log(num_lines, 10)))

        if num_digits == self.num_line_digits and not force:
            return

        self.num_line_digits = num_digits
        markup = "<b>%d</b>" % num_lines
        width, height = self._measure_markup(markup)
        self.set_size(width)

    def do_draw(self, context, background_area, cell_area, start, end, state):
        GtkSource.GutterRendererText.do_draw(
            self, context, background_area, cell_area, start, end, state)
        self.draw_chunks(
            context, background_area, cell_area, start, end, state)

    def do_query_data(self, start, end, state):
        self.query_chunks(start, end, state)
        line = start.get_line() + 1
        current_line = state & GtkSource.GutterRendererState.CURSOR
        markup = "<b>%d</b>" % line if current_line else str(line)
        self.set_markup(markup, -1)
