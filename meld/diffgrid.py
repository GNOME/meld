# Copyright (C) 2014 Marco Brito <bcaza@null.net>
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

from gi.repository import Gdk, GObject, Gtk


class DiffGrid(Gtk.Grid):
    __gtype_name__ = "DiffGrid"

    column_count = 10
    handle_columns = (2, 6)

    def __init__(self):
        super().__init__()
        self._in_drag = False
        self._drag_pos = -1
        self._drag_handle = None
        self._handle1 = HandleWindow()
        self._handle2 = HandleWindow()

    def do_realize(self):
        Gtk.Grid.do_realize(self)
        self._handle1.realize(self)
        self._handle2.realize(self)

    def do_unrealize(self):
        self._handle1.unrealize()
        self._handle2.unrealize()
        Gtk.Grid.do_unrealize(self)

    def do_map(self):
        Gtk.Grid.do_map(self)

        drag = self.get_child_at(2, 0)
        self._handle1.set_visible(drag and drag.get_visible())
        drag = self.get_child_at(6, 0)
        self._handle2.set_visible(drag and drag.get_visible())

    def do_unmap(self):
        self._handle1.set_visible(False)
        self._handle2.set_visible(False)
        Gtk.Grid.do_unmap(self)

    def _handle_set_prelight(self, window, flag):
        if hasattr(window, "handle"):
            window.handle.set_prelight(flag)

    def do_enter_notify_event(self, event):
        if hasattr(event.window, "handle"):
            event.window.handle.set_prelight(True)

    def do_leave_notify_event(self, event):
        if self._in_drag:
            return

        if hasattr(event.window, "handle"):
            event.window.handle.set_prelight(False)

    def do_button_press_event(self, event):
        if event.button & Gdk.BUTTON_PRIMARY:
            self._drag_pos = event.x
            self._in_drag = True
            return True
        return False

    def do_button_release_event(self, event):
        if event.button & Gdk.BUTTON_PRIMARY:
            self._in_drag = False
            return True
        return False

    def do_motion_notify_event(self, event):
        if event.state & Gdk.ModifierType.BUTTON1_MASK:
            if hasattr(event.window, "handle"):
                x, y = event.window.get_position()
                pos = round(x + event.x - self._drag_pos)
                event.window.handle.set_position(pos)
                self._drag_handle = event.window.handle
                self.queue_resize_no_redraw()
                return True
        return False

    def _calculate_positions(
            self, xmin, xmax, pane_sep_width_1, pane_sep_width_2,
            wpane1, wpane2, wpane3):
        wremain = max(0, xmax - xmin - pane_sep_width_1 - pane_sep_width_2)
        pos1 = self._handle1.get_position(wremain, xmin)
        pos2 = self._handle2.get_position(wremain, xmin + pane_sep_width_1)

        if not self._drag_handle:
            npanes = 0
            if wpane1 > 0:
                npanes += 1
            if wpane2 > 0:
                npanes += 1
            if wpane3 > 0:
                npanes += 1
            wpane = float(wremain) / max(1, npanes)
            if wpane1 > 0:
                wpane1 = wpane
            if wpane2 > 0:
                wpane2 = wpane
            if wpane3 > 0:
                wpane3 = wpane

        xminlink1 = xmin + wpane1
        xmaxlink2 = xmax - wpane3 - pane_sep_width_2
        wlinkpane = pane_sep_width_1 + wpane2

        if wpane1 == 0:
            pos1 = xminlink1
        if wpane3 == 0:
            pos2 = xmaxlink2
        if wpane2 == 0:
            if wpane3 == 0:
                pos1 = pos2 - pane_sep_width_2
            else:
                pos2 = pos1 + pane_sep_width_1

        if self._drag_handle == self._handle2:
            xminlink2 = xminlink1 + wlinkpane
            pos2 = min(max(xminlink2, pos2), xmaxlink2)
            xmaxlink1 = pos2 - wlinkpane
            pos1 = min(max(xminlink1, pos1), xmaxlink1)
        else:
            xmaxlink1 = xmaxlink2 - wlinkpane
            pos1 = min(max(xminlink1, pos1), xmaxlink1)
            xminlink2 = pos1 + wlinkpane
            pos2 = min(max(xminlink2, pos2), xmaxlink2)

        self._handle1.set_position(pos1)
        self._handle2.set_position(pos2)
        return int(round(pos1)), int(round(pos2))

    def do_size_allocate(self, allocation):
        # We should be chaining up here to:
        #     Gtk.Grid.do_size_allocate(self, allocation)
        # However, when we do this, we hit issues with doing multiple
        # allocations in a single allocation cycle (see bgo#779883).

        self.set_allocation(allocation)
        wcols, hrows = self._get_min_sizes()
        yrows = [allocation.y,
                 allocation.y + hrows[0],
                 # Roughly equivalent to hard-coding row 1 to expand=True
                 allocation.y + (allocation.height - hrows[2] - hrows[3]),
                 allocation.y + (allocation.height - hrows[3]),
                 allocation.y + allocation.height]

        (wpane1, wgutter1, wlink1, wgutter2, wpane2, wgutter3, wlink2,
            wgutter4, wpane3, wmap) = wcols
        xmin = allocation.x
        xmax = allocation.x + allocation.width - wmap
        pane_sep_width_1 = wgutter1 + wlink1 + wgutter2
        pane_sep_width_2 = wgutter3 + wlink2 + wgutter4
        pos1, pos2 = self._calculate_positions(
            xmin, xmax, pane_sep_width_1, pane_sep_width_2,
            wpane1, wpane2, wpane3
        )
        wpane1 = pos1 - allocation.x
        wpane2 = pos2 - (pos1 + pane_sep_width_1)
        wpane3 = xmax - (pos2 + pane_sep_width_2)
        wcols = (
            allocation.x, wpane1, wgutter1, wlink1, wgutter2, wpane2,
            wgutter3, wlink2, wgutter4, wpane3, wmap)
        columns = [sum(wcols[:i + 1]) for i in range(len(wcols))]

        def child_allocate(child):
            if not child.get_visible():
                return
            left, top, width, height = self.child_get(
                child, 'left-attach', 'top-attach', 'width', 'height')
            # This is a copy, and we have to do this because there's no Python
            # access to Gtk.Allocation.
            child_alloc = self.get_allocation()
            child_alloc.x = columns[left]
            child_alloc.y = yrows[top]
            child_alloc.width = columns[left + width] - columns[left]
            child_alloc.height = yrows[top + height] - yrows[top]

            if self.get_direction() == Gtk.TextDirection.RTL:
                child_alloc.x = (
                    allocation.x + allocation.width -
                    (child_alloc.x - allocation.x) - child_alloc.width)

            child.size_allocate(child_alloc)

        for child in self.get_children():
            child_allocate(child)

        if self.get_realized():
            mapped = self.get_mapped()
            ydrag = yrows[0]
            hdrag = yrows[1] - yrows[0]
            self._handle1.set_visible(mapped and pane_sep_width_1 > 0)
            self._handle1.move_resize(pos1, ydrag, pane_sep_width_1, hdrag)
            self._handle2.set_visible(mapped and pane_sep_width_2 > 0)
            self._handle2.move_resize(pos2, ydrag, pane_sep_width_2, hdrag)

    def _get_min_sizes(self):
        hrows = [0] * 4
        wcols = [0] * self.column_count
        for row in range(4):
            for col in range(self.column_count):
                child = self.get_child_at(col, row)
                if child and child.get_visible():
                    msize, nsize = child.get_preferred_size()
                    # Ignore spanning columns in width calculations; we should
                    # do this properly, but it's difficult.
                    spanning = GObject.Value(int)
                    self.child_get_property(child, 'width', spanning)
                    spanning = spanning.get_int()
                    # We ignore natural size when calculating required
                    # width, but use it when doing required height. The
                    # logic here is that height-for-width means that
                    # minimum width requisitions mean more-than-minimum
                    # heights. This is all extremely dodgy, but works
                    # for now.
                    if spanning == 1:
                        wcols[col] = max(wcols[col], msize.width)
                    hrows[row] = max(hrows[row], msize.height, nsize.height)
        return wcols, hrows

    def do_draw(self, context):
        Gtk.Grid.do_draw(self, context)
        self._handle1.draw(context)
        self._handle2.draw(context)


class HandleWindow():

    # We restrict the handle width because render_handle doesn't pay
    # attention to orientation.
    handle_width = 10

    def __init__(self):
        self._widget = None
        self._window = None
        self._area_x = -1
        self._area_y = -1
        self._area_width = 1
        self._area_height = 1
        self._prelit = False
        self._pos = 0.0
        self._transform = (0, 0)

    def get_position(self, width, xtrans):
        self._transform = (width, xtrans)
        return float(self._pos * width) + xtrans

    def set_position(self, pos):
        width, xtrans = self._transform
        self._pos = float(pos - xtrans) / width

    def realize(self, widget):
        attr = Gdk.WindowAttr()
        attr.window_type = Gdk.WindowType.CHILD
        attr.x = self._area_x
        attr.y = self._area_y
        attr.width = self._area_width
        attr.height = self._area_height
        attr.wclass = Gdk.WindowWindowClass.INPUT_OUTPUT
        attr.event_mask = (widget.get_events() |
                           Gdk.EventMask.BUTTON_PRESS_MASK |
                           Gdk.EventMask.BUTTON_RELEASE_MASK |
                           Gdk.EventMask.ENTER_NOTIFY_MASK |
                           Gdk.EventMask.LEAVE_NOTIFY_MASK |
                           Gdk.EventMask.POINTER_MOTION_MASK)
        attr.cursor = Gdk.Cursor.new_from_name(
            widget.get_display(),
            "col-resize",
        )
        attr_mask = (Gdk.WindowAttributesType.X |
                     Gdk.WindowAttributesType.Y |
                     Gdk.WindowAttributesType.CURSOR)

        parent = widget.get_parent_window()
        self._window = Gdk.Window(parent, attr, attr_mask)
        self._window.handle = self
        self._widget = widget
        self._widget.register_window(self._window)

    def unrealize(self):
        self._widget.unregister_window(self._window)

    def set_visible(self, visible):
        if visible:
            self._window.show()
        else:
            self._window.hide()

    def move_resize(self, x, y, width, height):
        self._window.move_resize(x, y, width, height)
        self._area_x = x
        self._area_y = y
        self._area_width = width
        self._area_height = height

    def set_prelight(self, flag):
        self._prelit = flag
        self._widget.queue_draw_area(self._area_x, self._area_y,
                                     self._area_width, self._area_height)

    def draw(self, cairocontext):
        alloc = self._widget.get_allocation()
        padding = 5
        x = self._area_x - alloc.x + padding
        y = self._area_y - alloc.y + padding
        width = max(0, self._area_width - 2 * padding)
        height = max(0, self._area_height - 2 * padding)

        if width == 0 or height == 0:
            return

        stylecontext = self._widget.get_style_context()
        state = stylecontext.get_state()
        if self._widget.is_focus():
            state |= Gtk.StateFlags.SELECTED
        if self._prelit:
            state |= Gtk.StateFlags.PRELIGHT

        if Gtk.cairo_should_draw_window(cairocontext, self._window):
            stylecontext.save()
            stylecontext.set_state(state)
            stylecontext.add_class(Gtk.STYLE_CLASS_PANE_SEPARATOR)
            stylecontext.add_class(Gtk.STYLE_CLASS_VERTICAL)
            color = stylecontext.get_background_color(state)
            if color.alpha > 0.0:
                xcenter = x + width / 2.0 - self.handle_width / 2.0
                Gtk.render_handle(
                    stylecontext, cairocontext,
                    xcenter, y, self.handle_width, height)
            else:
                xcenter = x + width / 2.0
                Gtk.render_line(stylecontext, cairocontext,
                                xcenter, y, xcenter, y + height)
            stylecontext.restore()
