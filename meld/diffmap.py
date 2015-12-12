# Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009-2013, 2015 Kai Willadsen <kai.willadsen@gmail.com>
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

import cairo

from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import Gtk

from meld.misc import get_common_theme
from meld.settings import meldsettings


class DiffMap(Gtk.DrawingArea):

    __gtype_name__ = "DiffMap"

    def __init__(self):
        GObject.GObject.__init__(self)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self._scrolladj = None
        self._difffunc = lambda: None
        self._handlers = []
        self._y_offset = 0
        self._h_offset = 0
        self._scroll_y = 0
        self._scroll_height = 0
        self._setup = False
        self._width = 10
        meldsettings.connect('changed', self.on_setting_changed)
        self.on_setting_changed(meldsettings, 'style-scheme')

    def setup(self, scrollbar, change_chunk_fn):
        for (o, h) in self._handlers:
            o.disconnect(h)

        self._scrolladj = scrollbar.get_adjustment()
        self.on_scrollbar_style_updated(scrollbar)
        self.on_scrollbar_size_allocate(scrollbar, scrollbar.get_allocation())
        scrollbar.ensure_style()
        scroll_style_hid = scrollbar.connect("style-updated",
                                             self.on_scrollbar_style_updated)
        scroll_size_hid = scrollbar.connect("size-allocate",
                                            self.on_scrollbar_size_allocate)
        adj_change_hid = self._scrolladj.connect("changed",
                                                 lambda w: self.queue_draw())
        adj_val_hid = self._scrolladj.connect("value-changed",
                                              lambda w: self.queue_draw())
        self._handlers = [(scrollbar, scroll_style_hid),
                          (scrollbar, scroll_size_hid),
                          (self._scrolladj, adj_change_hid),
                          (self._scrolladj, adj_val_hid)]
        self._difffunc = change_chunk_fn
        self._setup = True
        self._cached_map = None
        self.queue_draw()

    def on_diffs_changed(self, *args):
        self._cached_map = None

    def on_setting_changed(self, meldsettings, key):
        if key == 'style-scheme':
            self.fill_colors, self.line_colors = get_common_theme()

    def on_scrollbar_style_updated(self, scrollbar):
        stepper_size = scrollbar.style_get_property("stepper-size")
        stepper_spacing = scrollbar.style_get_property("stepper-spacing")

        has_backward = scrollbar.style_get_property("has-backward-stepper")
        has_secondary_backward = scrollbar.style_get_property(
            "has-secondary-backward-stepper")
        has_secondary_forward = scrollbar.style_get_property(
            "has-secondary-forward-stepper")
        has_forward = scrollbar.style_get_property("has-forward-stepper")
        steppers = [
            has_backward, has_secondary_backward,
            has_secondary_forward, has_forward,
        ]

        offset = stepper_size * steppers[0:2].count(True)
        shorter = stepper_size * steppers.count(True)
        if steppers[0] or steppers[1]:
            offset += stepper_spacing
            shorter += stepper_spacing
        if steppers[2] or steppers[3]:
            shorter += stepper_spacing
        self._y_offset = offset
        self._h_offset = shorter
        self.queue_draw()

    def on_scrollbar_size_allocate(self, scrollbar, allocation):
        translation = scrollbar.translate_coordinates(self, 0, 0)
        self._scroll_y = translation[1] if translation else 0
        self._scroll_height = allocation.height
        self._width = max(allocation.width, 10)
        self._cached_map = None
        self.queue_resize()

    def do_draw(self, context):
        if not self._setup:
            return
        height = self._scroll_height - self._h_offset - 1
        y_start = self._scroll_y + self._y_offset + 1
        width = self.get_allocated_width()
        xpad = 2.5
        x0 = xpad
        x1 = width - 2 * xpad

        # Hack to work around a cairo bug when calling create_similar
        # https://bugs.freedesktop.org/show_bug.cgi?id=60519
        if not (width and height):
            return

        context.translate(0, y_start)
        context.set_line_width(1)
        context.rectangle(x0 - 3, -1, x1 + 6, height + 1)
        context.clip()

        if self._cached_map is None:
            surface = cairo.Surface.create_similar(
                context.get_target(), cairo.CONTENT_COLOR_ALPHA,
                width, height)
            cache_ctx = cairo.Context(surface)
            cache_ctx.set_line_width(1)

            tagged_diffs = collections.defaultdict(list)
            for c, y0, y1 in self._difffunc():
                tagged_diffs[c].append((y0, y1))

            for tag, diffs in tagged_diffs.items():
                cache_ctx.set_source_rgba(*self.fill_colors[tag])
                for y0, y1 in diffs:
                    y0, y1 = round(y0 * height) - 0.5, round(y1 * height) - 0.5
                    cache_ctx.rectangle(x0, y0, x1, y1 - y0)
                cache_ctx.fill_preserve()
                cache_ctx.set_source_rgba(*self.line_colors[tag])
                cache_ctx.stroke()
            self._cached_map = surface

        context.set_source_surface(self._cached_map, 0., 0.)
        context.paint()

        page_color = (0., 0., 0., 0.1)
        page_outline_color = (0.0, 0.0, 0.0, 0.3)
        adj = self._scrolladj
        s = round(height * (adj.get_value() / adj.get_upper())) - 0.5
        e = round(height * (adj.get_page_size() / adj.get_upper()))
        context.set_source_rgba(*page_color)
        context.rectangle(x0 - 2, s, x1 + 4, e)
        context.fill_preserve()
        context.set_source_rgba(*page_outline_color)
        context.stroke()

    def do_button_press_event(self, event):
        if event.button == 1:
            y_start = self._scroll_y + self._y_offset
            total_height = self._scroll_height - self._h_offset
            fraction = (event.y - y_start) / total_height

            adj = self._scrolladj
            val = fraction * adj.get_upper() - adj.get_page_size() / 2
            upper = adj.get_upper() - adj.get_page_size()
            adj.set_value(max(min(upper, val), adj.get_lower()))
            return True
        return False

    def do_get_preferred_width(self):
        return self._width, self._width
