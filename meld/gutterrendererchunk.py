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

from gi.repository import Graphene, Gsk, GtkSource, Pango

from meld.settings import get_meld_settings
from meld.style import get_common_theme
from meld.ui.gtkutil import alpha_tint


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
                state: alpha_tint(colour, alpha)
                for state, colour in self.fill_colors.items()
            }

    def draw_chunks(self, snapshot, lines, line):
        chunk = self._chunk
        x, width = 0, self.get_width()
        y, height = lines.get_line_yrange(line, GtkSource.GutterRendererAlignmentMode.CELL)
        # Adjustment because we want to stroke the bottom border. This needs
        # to match do_snapshot_layer in meld.sourceview or things will not
        # align correctly.
        height += 1

        if not chunk or chunk[1] == chunk[2]:
            # For some reason, the background drawing doesn't work as we
            # expect in the gutter context; this gives us our desired result
            background_rgba = get_background_rgba(self)
        elif self.props.view.current_chunk_check(chunk):
            background_rgba = self.chunk_highlights[chunk[0]]
        else:
            background_rgba = self.fill_colors[chunk[0]]

        rect = Graphene.Rect()
        rect.init(x, y + 1, width, height)
        snapshot.append_color(background_rgba, rect)

        # If we don't have a chunk, we don't draw any borders
        if not chunk:
            return

        path_builder = Gsk.PathBuilder()
        is_first_line = line == chunk[1]
        is_last_line = line == chunk[2] - 1

        if is_first_line:
            path_builder.move_to(x, y + 0.5)
            path_builder.rel_line_to(width, 0)
        if is_last_line:
            path_builder.move_to(x, y - 0.5 + height)
            path_builder.rel_line_to(width, 0)

        path = path_builder.to_path()
        snapshot.append_stroke(path, Gsk.Stroke(1.0), self.line_colors[chunk[0]])

    def query_chunks(self, lines, line):
        idx = self.linediffer.locate_chunk(self.from_pane, line)[0]
        if idx is not None:
            self._chunk = self.linediffer.get_chunk(idx, self.from_pane, self.to_pane)
        else:
            self._chunk = None


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
        if not self.get_buffer():
            return
        buf = self.get_buffer()
        self.recalculate_size(buf, force=True)

    def do_css_changed(self, change):
        self.on_view_changed()
        GtkSource.GutterRendererText.do_css_changed(self, change)

    def do_change_buffer(self, old_buffer):
        if old_buffer:
            old_buffer.disconnect(self.changed_handler_id)

        if buf := self.get_buffer():
            self.changed_handler_id = buf.connect("changed", self.recalculate_size)
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
        width, height = self._measure_markup(f"<b>{num_lines}</b>")
        self.set_size_request(width, height)

    def do_snapshot_line(self, snapshot, lines, line):
        self.draw_chunks(snapshot, lines, line)
        return GtkSource.GutterRendererText.do_snapshot_line(
            self, snapshot, lines, line
        )

    def do_query_data(self, lines, line):
        self.query_chunks(lines, line)
        self.set_markup(f"<b>{line + 1}</b>", -1)
