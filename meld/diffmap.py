### Copyright (C) 2002-2009 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2009-2010 Kai Willadsen <kai.willadsen@gmail.com>

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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import gobject
import gtk


class DiffMap(gtk.DrawingArea):

    __gtype_name__ = "DiffMap"

    __gsignals__ = {
        'expose-event': 'override',
        'button-press-event': 'override',
        'size-request': 'override',
    }

    def __init__(self):
        gtk.DrawingArea.__init__(self)
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self._scrolladj = None
        self._difffunc = lambda: None
        self._handlers = []
        self._y_offset = 0
        self._h_offset = 0
        self._scroll_y = 0
        self._scroll_height = 0
        self.ctab = {}

    def setup(self, scrollbar, change_chunk_fn, colour_map):
        for (o, h) in self._handlers:
            o.disconnect(h)

        self._scrolladj = scrollbar.get_adjustment()
        self.on_scrollbar_style_set(scrollbar, None)
        self.on_scrollbar_size_allocate(scrollbar, scrollbar.allocation)
        scroll_style_hid = scrollbar.connect("style-set",
                                             self.on_scrollbar_style_set)
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
        self.ctab = colour_map
        self.queue_draw()

    def on_scrollbar_style_set(self, scrollbar, previous_style):
        stepper_size = scrollbar.style_get_property("stepper-size")
        steppers = [scrollbar.style_get_property(x) for x in
                    ("has-backward-stepper", "has-secondary-forward-stepper",
                     "has-secondary-backward-stepper", "has-forward-stepper")]
        stepper_spacing = scrollbar.style_get_property("stepper-spacing")

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
        self._scroll_y = allocation.y
        self._scroll_height = allocation.height
        self.queue_draw()

    def do_expose_event(self, event):
        height = self._scroll_height - self._h_offset - 1
        y_start = self._scroll_y - self.allocation.y + self._y_offset + 1
        xpad = self.style_get_property('x-padding')
        x0 = xpad
        x1 = self.allocation.width - 2 * xpad

        context = self.window.cairo_create()
        context.translate(0, y_start)
        context.set_line_width(1)
        context.rectangle(x0 - 3, -1, x1 + 6, height + 1)
        context.clip()

        darken = lambda color: [x * 0.8 for x in color]

        for c, y0, y1 in self._difffunc():
            color = self.ctab[c]
            y0, y1 = round(y0 * height) - 0.5, round(y1 * height) - 0.5
            context.set_source_rgb(*color)
            context.rectangle(x0, y0, x1, int(y1 - y0))
            context.fill_preserve()
            context.set_source_rgb(*darken(color))
            context.stroke()

        page_color = (0., 0., 0., 0.1)
        page_outline_color = (0.0, 0.0, 0.0, 0.3)
        adj = self._scrolladj
        s = round(height * (adj.value / adj.upper)) - 0.5
        e = round(height * (adj.page_size / adj.upper))
        context.set_source_rgba(*page_color)
        context.rectangle(x0 - 2, s, x1 + 4, e)
        context.fill_preserve()
        context.set_source_rgba(*page_outline_color)
        context.stroke()

    def do_button_press_event(self, event):
        if event.button == 1:
            y_start = self.allocation.y - self._scroll_y - self._y_offset
            total_height = self._scroll_height - self._h_offset
            fraction = (event.y + y_start) / total_height

            adj = self._scrolladj
            val = fraction * adj.upper - adj.page_size / 2
            upper = adj.upper - adj.page_size
            adj.set_value(max(min(upper, val), adj.lower))
            return True
        return False

    def do_size_request(self, request):
        request.width = self.style_get_property('width')

gtk.widget_class_install_style_property(DiffMap,
                                        ('width', float,
                                         'Width',
                                         'Width of the bar',
                                         0.0, gobject.G_MAXFLOAT, 20,
                                         gobject.PARAM_READABLE))
gtk.widget_class_install_style_property(DiffMap,
                                        ('x-padding', float,
                                         'Width-wise padding',
                                         'Padding to be left between left and '
                                         'right edges and change blocks',
                                         0.0, gobject.G_MAXFLOAT, 3.5,
                                         gobject.PARAM_READABLE))


def create_diffmap(str1, str2, int1, int2):
    return DiffMap()
