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

from gi.repository import Gtk


class LinkMap(Gtk.DrawingArea):

    __gtype_name__ = "LinkMap"

    def __init__(self):
        self._setup = False

    def associate(self, filediff, left_view, right_view):
        self.filediff = filediff
        self.views = [left_view, right_view]
        if self.get_direction() == Gtk.TextDirection.RTL:
            self.views.reverse()
        self.view_indices = [filediff.textview.index(t) for t in self.views]

        self.set_color_scheme((filediff.fill_colors, filediff.line_colors))

        self.line_height = filediff.pixels_per_line

        self._setup = True

    def set_color_scheme(self, color_map):
        self.fill_colors, self.line_colors = color_map
        self.queue_draw()

    def do_draw(self, context):
        if not self._setup:
            return

        context.set_line_width(1.0)
        allocation = self.get_allocation()

        pix_start = [t.get_visible_rect().y for t in self.views]
        y_offset = [t.translate_coordinates(self, 0, 0)[1] for t in self.views]

        height = allocation.height
        visible = [self.views[0].get_line_num_for_y(pix_start[0]),
                   self.views[0].get_line_num_for_y(pix_start[0] + height),
                   self.views[1].get_line_num_for_y(pix_start[1]),
                   self.views[1].get_line_num_for_y(pix_start[1] + height)]

        wtotal = allocation.width
        # For bezier control points
        x_steps = [-0.5, (1. / 3) * wtotal, (2. / 3) * wtotal, wtotal + 0.5]
        # Rounded rectangle corner radius for culled changes display
        radius = self.line_height // 2
        q_rad = math.pi / 2

        left, right = self.view_indices
        view_offset_line = lambda v, l: (self.views[v].get_y_for_line_num(l) -
                                         pix_start[v] + y_offset[v])
        for c in self.filediff.linediffer.pair_changes(left, right, visible):
            # f and t are short for "from" and "to"
            f0, f1 = [view_offset_line(0, l) for l in c[1:3]]
            t0, t1 = [view_offset_line(1, l) for l in c[3:5]]

            # If either endpoint is completely off-screen, we cull for clarity
            if (t0 < 0 and t1 < 0) or (t0 > height and t1 > height):
                if f0 == f1:
                    continue
                context.move_to(x_steps[0], f0 - 0.5)
                context.arc(x_steps[0], f0 - 0.5 + radius, radius, -q_rad, 0)
                context.rel_line_to(0, f1 - f0 - radius * 2)
                context.arc(x_steps[0], f1 - 0.5 - radius, radius, 0, q_rad)
                context.close_path()
            elif (f0 < 0 and f1 < 0) or (f0 > height and f1 > height):
                if t0 == t1:
                    continue
                context.move_to(x_steps[3], t0 - 0.5)
                context.arc_negative(x_steps[3], t0 - 0.5 + radius, radius,
                                     -q_rad, q_rad * 2)
                context.rel_line_to(0, t1 - t0 - radius * 2)
                context.arc_negative(x_steps[3], t1 - 0.5 - radius, radius,
                                     q_rad * 2, q_rad)
                context.close_path()
            else:
                context.move_to(x_steps[0], f0 - 0.5)
                context.curve_to(x_steps[1], f0 - 0.5,
                                 x_steps[2], t0 - 0.5,
                                 x_steps[3], t0 - 0.5)
                context.line_to(x_steps[3], t1 - 0.5)
                context.curve_to(x_steps[2], t1 - 0.5,
                                 x_steps[1], f1 - 0.5,
                                 x_steps[0], f1 - 0.5)
                context.close_path()

            context.set_source_rgba(*self.fill_colors[c[0]])
            context.fill_preserve()

            chunk_idx = self.filediff.linediffer.locate_chunk(left, c[1])[0]
            if chunk_idx == self.filediff.cursor.chunk:
                h = self.fill_colors['current-chunk-highlight']
                context.set_source_rgba(
                    h.red, h.green, h.blue, 0.5)
                context.fill_preserve()

            context.set_source_rgba(*self.line_colors[c[0]])
            context.stroke()


    def do_scroll_event(self, event):
        self.filediff.next_diff(event.direction)
