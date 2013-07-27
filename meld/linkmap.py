### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2009-2011 Kai Willadsen <kai.willadsen@gmail.com>

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


import math

import gtk

from . import diffutil


# FIXME: import order issues
MODE_REPLACE, MODE_DELETE, MODE_INSERT = 0, 1, 2


class LinkMap(gtk.DrawingArea):

    __gtype_name__ = "LinkMap"

    __gsignals__ = {
        'expose-event': 'override',
        'scroll-event': 'override',
        'button-press-event': 'override',
        'button-release-event': 'override',
    }

    def __init__(self):
        self.mode = MODE_REPLACE
        self._setup = False

    def associate(self, filediff, left_view, right_view):
        self.filediff = filediff
        self.views = [left_view, right_view]
        if self.get_direction() == gtk.TEXT_DIR_RTL:
            self.views.reverse()
        self.view_indices = [filediff.textview.index(t) for t in self.views]

        self.set_color_scheme((filediff.fill_colors, filediff.line_colors))

        self.line_height = filediff.pixels_per_line
        icon_theme = gtk.icon_theme_get_default()
        load = lambda x: icon_theme.load_icon(x, self.line_height, 0)
        pixbuf_apply0 = load("button_apply0")
        pixbuf_apply1 = load("button_apply1")
        pixbuf_delete = load("button_delete")
        # FIXME: this is a somewhat bizarre action to take, but our non-square
        # icons really make this kind of handling difficult
        load = lambda x: icon_theme.load_icon(x, self.line_height * 2, 0)
        pixbuf_copy0 = load("button_copy0")
        pixbuf_copy1 = load("button_copy1")

        self.action_map_left = {
            MODE_REPLACE: pixbuf_apply0,
            MODE_DELETE: pixbuf_delete,
            MODE_INSERT: pixbuf_copy0,
        }

        self.action_map_right = {
            MODE_REPLACE: pixbuf_apply1,
            MODE_DELETE: pixbuf_delete,
            MODE_INSERT: pixbuf_copy1,
        }

        self.button_width = pixbuf_apply0.get_width()
        self.button_height = pixbuf_apply0.get_height()

        filediff.connect("action-mode-changed", self.on_container_mode_changed)
        self._setup = True

    def set_color_scheme(self, color_map):
        self.fill_colors, self.line_colors = color_map
        self.queue_draw()

    def on_container_mode_changed(self, container, mode):
        # On mode change, set our local copy of the mode, and cancel any mouse
        # actions in progress. Otherwise, if someone clicks, then releases
        # Shift, then releases the button... what do we do?
        self.mode = mode
        self.mouse_chunk = None
        x, y, width, height = self.allocation
        pixbuf_width = self.button_width
        self.queue_draw_area(0, 0, pixbuf_width, height)
        self.queue_draw_area(width - pixbuf_width, 0, pixbuf_width, height)

    def paint_pixbuf_at(self, context, pixbuf, x, y):
        context.translate(x, y)
        context.set_source_pixbuf(pixbuf, 0, 0)
        context.paint()
        context.identity_matrix()

    def _classify_change_actions(self, change):
        """Classify possible actions for the given change

        Returns a tuple containing actions that can be performed given the
        content and context of the change. The tuple gives the actions for
        the left and right sides of the LinkMap.
        """
        left_editable, right_editable = [v.get_editable() for v in self.views]

        if not left_editable and not right_editable:
            return None, None

        # Reclassify conflict changes, since we treat them the same as a
        # normal two-way change as far as actions are concerned
        change_type = change[0]
        if change_type == "conflict":
            if change[1] == change[2]:
                change_type = "insert"
            elif change[3] == change[4]:
                change_type = "delete"
            else:
                change_type = "replace"

        left_act, right_act = None, None
        if change_type == "delete":
            left_act = MODE_REPLACE
            if (self.mode == MODE_DELETE or not right_editable) and \
               left_editable:
                left_act = MODE_DELETE
        elif change_type == "insert":
            right_act = MODE_REPLACE
            if (self.mode == MODE_DELETE or not left_editable) and \
               right_editable:
                right_act = MODE_DELETE
        elif change_type == "replace":
            if not left_editable:
                left_act, right_act = MODE_REPLACE, MODE_DELETE
                if self.mode == MODE_INSERT:
                    left_act = MODE_INSERT
            elif not right_editable:
                left_act, right_act = MODE_DELETE, MODE_REPLACE
                if self.mode == MODE_INSERT:
                    right_act = MODE_INSERT
            else:
                left_act, right_act = MODE_REPLACE, MODE_REPLACE
                if self.mode == MODE_DELETE:
                    left_act, right_act = MODE_DELETE, MODE_DELETE
                elif self.mode == MODE_INSERT:
                    left_act, right_act = MODE_INSERT, MODE_INSERT

        return left_act, right_act

    def do_expose_event(self, event):
        if not self._setup:
            return

        context = self.window.cairo_create()
        context.rectangle(event.area.x, event.area.y, event.area.width,
                          event.area.height)
        context.clip()
        context.set_line_width(1.0)

        pix_start = [t.get_visible_rect().y for t in self.views]
        rel_offset = [t.allocation.y - self.allocation.y for t in self.views]

        height = self.allocation.height
        visible = [self.views[0].get_line_num_for_y(pix_start[0]),
                   self.views[0].get_line_num_for_y(pix_start[0] + height),
                   self.views[1].get_line_num_for_y(pix_start[1]),
                   self.views[1].get_line_num_for_y(pix_start[1] + height)]

        wtotal = self.allocation.width
        # For bezier control points
        x_steps = [-0.5, (1. / 3) * wtotal, (2. / 3) * wtotal, wtotal + 0.5]
        # Rounded rectangle corner radius for culled changes display
        radius = self.line_height // 2
        q_rad = math.pi / 2

        left, right = self.view_indices
        view_offset_line = lambda v, l: (self.views[v].get_y_for_line_num(l) -
                                         pix_start[v] + rel_offset[v])
        for c in self.filediff.linediffer.pair_changes(left, right, visible):
            # f and t are short for "from" and "to"
            f0, f1 = [view_offset_line(0, l) for l in c[1:3]]
            t0, t1 = [view_offset_line(1, l) for l in c[3:5]]

            culled = False
            # If either endpoint is completely off-screen, we cull for clarity
            if (t0 < 0 and t1 < 0) or (t0 > height and t1 > height):
                if f0 == f1:
                    continue
                context.move_to(x_steps[0], f0 - 0.5)
                context.arc(x_steps[0], f0 - 0.5 + radius, radius, -q_rad, 0)
                context.rel_line_to(0, f1 - f0 - radius * 2)
                context.arc(x_steps[0], f1 - 0.5 - radius, radius, 0, q_rad)
                context.close_path()
                culled = True
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
                culled = True
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

            context.set_source_color(self.fill_colors[c[0]])
            context.fill_preserve()

            chunk_idx = self.filediff.linediffer.locate_chunk(left, c[1])[0]
            if chunk_idx == self.filediff.cursor.chunk:
                h = self.fill_colors['current-chunk-highlight']
                context.set_source_rgba(
                    h.red_float, h.green_float, h.blue_float, 0.5)
                context.fill_preserve()

            context.set_source_color(self.line_colors[c[0]])
            context.stroke()

            if culled:
                continue

            x = wtotal - self.button_width
            left_act, right_act = self._classify_change_actions(c)
            if left_act is not None:
                pix0 = self.action_map_left[left_act]
                self.paint_pixbuf_at(context, pix0, 0, f0)
            if right_act is not None:
                pix1 = self.action_map_right[right_act]
                self.paint_pixbuf_at(context, pix1, x, t0)

        # allow for scrollbar at end of textview
        mid = int(0.5 * self.views[0].allocation.height) + 0.5
        context.set_source_rgba(0., 0., 0., 0.5)
        context.move_to(.35 * wtotal, mid)
        context.line_to(.65 * wtotal, mid)
        context.stroke()

    def do_scroll_event(self, event):
        self.filediff.next_diff(event.direction)

    def _linkmap_process_event(self, event, side, x, pix_width, pix_height):
        src_idx, dst_idx = side, 1 if side == 0 else 0
        src, dst = self.view_indices[src_idx], self.view_indices[dst_idx]

        vis_offset = [t.get_visible_rect().y for t in self.views]
        rel_offset = [t.allocation.y - self.allocation.y for t in self.views]
        height = self.allocation.height

        bounds = []
        for v in (self.views[src_idx], self.views[dst_idx]):
            visible = v.get_visible_rect()
            bounds.append(v.get_line_num_for_y(visible.y))
            bounds.append(v.get_line_num_for_y(visible.y + visible.height))

        view_offset_line = lambda v, l: (self.views[v].get_y_for_line_num(l) -
                                         vis_offset[v] + rel_offset[v])
        for c in self.filediff.linediffer.pair_changes(src, dst, bounds):
            f0, f1 = [view_offset_line(src_idx, l) for l in c[1:3]]
            t0, t1 = [view_offset_line(dst_idx, l) for l in c[3:5]]

            f0 = view_offset_line(src_idx, c[1])

            if f0 < event.y < f0 + pix_height:
                if (t0 < 0 and t1 < 0) or (t0 > height and t1 > height) or \
                   (f0 < 0 and f1 < 0) or (f0 > height and f1 > height):
                    break

                # _classify_change_actions assumes changes are left->right
                action_change = diffutil.reverse_chunk(c) if dst < src else c
                actions = self._classify_change_actions(action_change)
                if actions[side] is not None:
                    rect = gtk.gdk.Rectangle(x, f0, pix_width, pix_height)
                    self.mouse_chunk = ((src, dst), rect, c, actions[side])
                break

    def do_button_press_event(self, event):
        if event.button == 1:
            self.mouse_chunk = None
            pix_width = self.button_width
            pix_height = self.button_height
            # Hack to deal with our non-square insert-mode icons
            if self.mode == MODE_INSERT:
                pix_height *= 2

            # Quick reject if not in the area used to draw our buttons
            right_gutter_x = self.allocation.width - pix_width
            if event.x >= pix_width and event.x <= right_gutter_x:
                return True

            # side = 0 means left side of linkmap, so action from left -> right
            side = 0 if event.x < pix_width else 1
            x = 0 if event.x < pix_width else right_gutter_x
            self._linkmap_process_event(event, side, x, pix_width, pix_height)
            return True
        return False

    def do_button_release_event(self, event):
        if event.button == 1:
            if self.mouse_chunk:
                (src, dst), rect, chunk, action = self.mouse_chunk
                self.mouse_chunk = None
                # Check that we're still in the same button we started in
                if rect.x <= event.x < rect.x + rect.width and \
                   rect.y <= event.y < rect.y + rect.height:
                    # Unless we move the cursor, the view scrolls back to
                    # its old position
                    self.views[0].place_cursor_onscreen()
                    self.views[1].place_cursor_onscreen()

                    if action == MODE_DELETE:
                        self.filediff.delete_chunk(src, chunk)
                    elif action == MODE_INSERT:
                        copy_up = event.y - rect[1] < 0.5 * rect[3]
                        self.filediff.copy_chunk(src, dst, chunk, copy_up)
                    else:
                        self.filediff.replace_chunk(src, dst, chunk)
            return True
        return False
