# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import Gdk, Gtk

from meld.settings import get_meld_settings
from meld.style import get_common_theme

# Rounded rectangle corner radius for culled changes display
RADIUS = 3


class LinkMap(Gtk.DrawingArea):

    __gtype_name__ = "LinkMap"

    def __init__(self):
        self.filediff = None
        self.views = []

    def associate(self, filediff, left_view, right_view):
        self.filediff = filediff
        self.views = [left_view, right_view]
        if self.get_direction() == Gtk.TextDirection.RTL:
            self.views.reverse()
        self.view_indices = [filediff.textview.index(t) for t in self.views]

        meld_settings = get_meld_settings()
        self.on_setting_changed(meld_settings, 'style-scheme')
        meld_settings.connect('changed', self.on_setting_changed)

    def on_setting_changed(self, settings, key):
        if key == 'style-scheme':
            self.fill_colors, self.line_colors = get_common_theme()

    def do_draw(self, context):
        if not self.views:
            return

        pix_start = [t.get_visible_rect().y for t in self.views]
        y_offset = [
            t.translate_coordinates(self, 0, 0)[1] + 1 for t in self.views]

        clip_y = min(y_offset) - 1
        clip_height = max(t.get_visible_rect().height for t in self.views) + 2
        allocation = self.get_allocation()

        stylecontext = self.get_style_context()
        Gtk.render_background(
            stylecontext, context, 0, clip_y, allocation.width, clip_height)
        context.set_line_width(1.0)

        height = allocation.height
        visible = [
            self.views[0].get_line_num_for_y(pix_start[0]),
            self.views[0].get_line_num_for_y(pix_start[0] + height),
            self.views[1].get_line_num_for_y(pix_start[1]),
            self.views[1].get_line_num_for_y(pix_start[1] + height),
        ]

        # For bezier control points
        x_steps = [-0.5, allocation.width / 2, allocation.width + 0.5]
        q_rad = math.pi / 2

        left, right = self.view_indices

        def view_offset_line(view_idx, line_num):
            line_start = self.views[view_idx].get_y_for_line_num(line_num)
            return line_start - pix_start[view_idx] + y_offset[view_idx]

        for c in self.filediff.linediffer.pair_changes(left, right, visible):
            # f and t are short for "from" and "to"
            f0, f1 = [view_offset_line(0, line) for line in c[1:3]]
            t0, t1 = [view_offset_line(1, line) for line in c[3:5]]
            # We want the last pixel of the previous line
            f1 = f1 if f1 == f0 else f1 - 1
            t1 = t1 if t1 == t0 else t1 - 1

            # If either endpoint is completely off-screen, we cull for clarity
            if (t0 < 0 and t1 < 0) or (t0 > height and t1 > height):
                if f0 == f1:
                    continue
                context.arc(
                    x_steps[0], f0 - 0.5 + RADIUS, RADIUS, q_rad * 3, 0)
                context.arc(x_steps[0], f1 - 0.5 - RADIUS, RADIUS, 0, q_rad)
                context.close_path()
            elif (f0 < 0 and f1 < 0) or (f0 > height and f1 > height):
                if t0 == t1:
                    continue
                context.arc_negative(x_steps[2], t0 - 0.5 + RADIUS, RADIUS,
                                     q_rad * 3, q_rad * 2)
                context.arc_negative(x_steps[2], t1 - 0.5 - RADIUS, RADIUS,
                                     q_rad * 2, q_rad)
                context.close_path()
            else:
                context.move_to(x_steps[0], f0 - 0.5)
                context.curve_to(x_steps[1], f0 - 0.5,
                                 x_steps[1], t0 - 0.5,
                                 x_steps[2], t0 - 0.5)
                context.line_to(x_steps[2], t1 - 0.5)
                context.curve_to(x_steps[1], t1 - 0.5,
                                 x_steps[1], f1 - 0.5,
                                 x_steps[0], f1 - 0.5)
                context.close_path()

            Gdk.cairo_set_source_rgba(context, self.fill_colors[c[0]])
            context.fill_preserve()

            chunk_idx = self.filediff.linediffer.locate_chunk(left, c[1])[0]
            if chunk_idx == self.filediff.cursor.chunk:
                highlight = self.fill_colors['current-chunk-highlight']
                Gdk.cairo_set_source_rgba(context, highlight)
                context.fill_preserve()

            Gdk.cairo_set_source_rgba(context, self.line_colors[c[0]])
            context.stroke()


LinkMap.set_css_name("link-map")


class ScrollLinkMap(Gtk.DrawingArea):

    __gtype_name__ = "ScrollLinkMap"
