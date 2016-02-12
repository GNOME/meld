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

from gi.repository import Pango
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.conf import _
from meld.const import MODE_REPLACE, MODE_DELETE, MODE_INSERT
from meld.misc import get_common_theme
from meld.settings import meldsettings

# Fixed size of the renderer. Ideally this would be font-dependent and
# would adjust to other textview attributes, but that's both quite difficult
# and not necessarily desirable.
LINE_HEIGHT = 16


def load(icon_name):
    icon_theme = Gtk.IconTheme.get_default()
    return icon_theme.load_icon(icon_name, LINE_HEIGHT, 0)


class MeldGutterRenderer(object):

    def on_setting_changed(self, meldsettings, key):
        if key == 'style-scheme':
            # meldsettings.style_scheme
            self.fill_colors, self.line_colors = get_common_theme()

    def draw_chunks(
            self, context, background_area, cell_area, start, end, state):

        stylecontext = self.props.view.get_style_context()
        background_set, background_rgba = (
            stylecontext.lookup_color('theme_bg_color'))

        line = start.get_line()
        chunk_index = self.linediffer.locate_chunk(self.from_pane, line)[0]

        context.save()
        context.set_line_width(1.0)

        context.rectangle(
            background_area.x, background_area.y,
            background_area.width, background_area.height)
        context.set_source_rgba(*background_rgba)
        context.fill()

        if chunk_index is not None:
            chunk = self.linediffer.get_chunk(
                chunk_index, self.from_pane, self.to_pane)

            if chunk:
                x = background_area.x - 1
                width = background_area.width + 2

                height = 1 if chunk[1] == chunk[2] else background_area.height
                y = background_area.y
                context.rectangle(x, y, width, height)
                context.set_source_rgba(*self.fill_colors[chunk[0]])

                if self.props.view.current_chunk_check(chunk):
                    context.fill_preserve()
                    highlight = self.fill_colors['current-chunk-highlight']
                    context.set_source_rgba(*highlight)
                context.fill()

                if line == chunk[1] or line == chunk[2] - 1:
                    context.set_source_rgba(*self.line_colors[chunk[0]])
                    if line == chunk[1]:
                        context.move_to(x, y + 0.5)
                        context.rel_line_to(width, 0)
                    if line == chunk[2] - 1:
                        context.move_to(x, y - 0.5 + height)
                        context.rel_line_to(width, 0)
                    context.stroke()
        context.restore()


class GutterRendererChunkAction(
        GtkSource.GutterRendererPixbuf, MeldGutterRenderer):
    __gtype_name__ = "GutterRendererChunkAction"

    ACTION_MAP = {
        'LTR': {
            MODE_REPLACE: load("meld-change-apply-right"),
            MODE_DELETE: load("meld-change-delete"),
            MODE_INSERT: load("meld-change-copy"),
        },
        'RTL': {
            MODE_REPLACE: load("meld-change-apply-left"),
            MODE_DELETE: load("meld-change-delete"),
            MODE_INSERT: load("meld-change-copy"),
        }
    }

    def __init__(self, from_pane, to_pane, views, filediff, linediffer):
        super(GutterRendererChunkAction, self).__init__()
        self.from_pane = from_pane
        self.to_pane = to_pane
        # FIXME: Views are needed only for editable checking; connect to this
        # in Filediff instead?
        self.views = views
        # FIXME: Don't pass in the linediffer; pass a generator like elsewhere
        self.linediffer = linediffer
        self.mode = MODE_REPLACE
        self.set_size(LINE_HEIGHT)
        direction = 'LTR' if from_pane < to_pane else 'RTL'
        if self.views[0].get_direction() == Gtk.TextDirection.RTL:
            direction = 'LTR' if direction == 'RTL' else 'RTL'

        self.action_map = self.ACTION_MAP[direction]
        self.filediff = filediff
        self.filediff.connect("action-mode-changed",
                              self.on_container_mode_changed)

        meldsettings.connect('changed', self.on_setting_changed)
        self.on_setting_changed(meldsettings, 'style-scheme')

    def do_activate(self, start, area, event):
        line = start.get_line()
        chunk_index = self.linediffer.locate_chunk(self.from_pane, line)[0]
        if chunk_index is None:
            return

        chunk = self.linediffer.get_chunk(
            chunk_index, self.from_pane, self.to_pane)
        if chunk[1] != line:
            return

        action = self._classify_change_actions(chunk)
        if action == MODE_DELETE:
            self.filediff.delete_chunk(self.from_pane, chunk)
        elif action == MODE_INSERT:
            copy_menu = self._make_copy_menu(chunk)
            # TODO: Need a custom GtkMenuPositionFunc to position this next to
            # the clicked gutter, not where the cursor is
            copy_menu.popup(None, None, None, None, 0, event.time)
        else:
            self.filediff.replace_chunk(self.from_pane, self.to_pane, chunk)

    def _make_copy_menu(self, chunk):
        copy_menu = Gtk.Menu()
        copy_up = Gtk.MenuItem.new_with_mnemonic(_("Copy _up"))
        copy_down = Gtk.MenuItem.new_with_mnemonic(_("Copy _down"))
        copy_menu.append(copy_up)
        copy_menu.append(copy_down)
        copy_menu.show_all()

        # FIXME: This is horrible
        widget = self.filediff.widget
        copy_menu.attach_to_widget(widget, None)

        def copy_chunk(widget, chunk, copy_up):
            self.filediff.copy_chunk(self.from_pane, self.to_pane, chunk,
                                     copy_up)

        copy_up.connect('activate', copy_chunk, chunk, True)
        copy_down.connect('activate', copy_chunk, chunk, False)
        return copy_menu

    def do_draw(self, context, background_area, cell_area, start, end, state):
        self.draw_chunks(
            context, background_area, cell_area, start, end, state)
        return GtkSource.GutterRendererPixbuf.do_draw(
            self, context, background_area, cell_area, start, end, state)

    def do_query_activatable(self, start, area, event):
        line = start.get_line()
        chunk_index = self.linediffer.locate_chunk(self.from_pane, line)[0]
        if chunk_index is not None:
            # FIXME: This is all chunks, not just those shared with to_pane
            chunk = self.linediffer.get_chunk(chunk_index, self.from_pane)
            if chunk[1] == line:
                return True
        return False

    def do_query_data(self, start, end, state):
        line = start.get_line()
        chunk_index = self.linediffer.locate_chunk(self.from_pane, line)[0]

        pixbuf = None
        if chunk_index is not None:
            chunk = self.linediffer.get_chunk(
                chunk_index, self.from_pane, self.to_pane)
            if chunk and chunk[1] == line:
                action = self._classify_change_actions(chunk)
                pixbuf = self.action_map.get(action)
        if pixbuf:
            self.set_pixbuf(pixbuf)
        else:
            self.props.pixbuf = None

    def on_container_mode_changed(self, container, mode):
        self.mode = mode
        self.queue_draw()

    def _classify_change_actions(self, change):
        """Classify possible actions for the given change

        Returns the action that can be performed given the content and
        context of the change.
        """
        editable, other_editable = [v.get_editable() for v in self.views]

        if not editable and not other_editable:
            return None

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

        action = None
        if change_type == "delete":
            if (editable and (self.mode == MODE_DELETE or not other_editable)):
                action = MODE_DELETE
            elif other_editable:
                action = MODE_REPLACE
        elif change_type == "replace":
            if not editable:
                if self.mode in (MODE_INSERT, MODE_REPLACE):
                    action = self.mode
            elif not other_editable:
                action = MODE_DELETE
            else:
                action = self.mode

        return action


# GutterRendererChunkLines is an adaptation of GtkSourceGutterRendererLines
# Copyright (C) 2010 - Jesse van den Kieboom
#
# Python reimplementation is Copyright (C) 2015 Kai Willadsen


class GutterRendererChunkLines(
        GtkSource.GutterRendererText, MeldGutterRenderer):
    __gtype_name__ = "GutterRendererChunkLines"

    def __init__(self, from_pane, to_pane, linediffer):
        super(GutterRendererChunkLines, self).__init__()
        self.from_pane = from_pane
        self.to_pane = to_pane
        # FIXME: Don't pass in the linediffer; pass a generator like elsewhere
        self.linediffer = linediffer

        self.num_line_digits = 0
        self.changed_handler_id = None

        meldsettings.connect('changed', self.on_setting_changed)
        self.on_setting_changed(meldsettings, 'style-scheme')

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

    def recalculate_size(self, buf):

        # Always calculate display size for at least two-digit line counts
        num_lines = max(buf.get_line_count(), 99)
        num_digits = int(math.ceil(math.log(num_lines, 10)))

        if num_digits == self.num_line_digits:
            return

        self.num_line_digits = num_digits
        markup = "<b>%d</b>" % num_lines
        width, height = self._measure_markup(markup)
        self.set_size(width)

    def do_draw(self, context, background_area, cell_area, start, end, state):
        self.draw_chunks(
            context, background_area, cell_area, start, end, state)
        return GtkSource.GutterRendererText.do_draw(
            self, context, background_area, cell_area, start, end, state)

    def do_query_data(self, start, end, state):
        line = start.get_line() + 1
        current_line = state & GtkSource.GutterRendererState.CURSOR
        markup = "<b>%d</b>" % line if current_line else str(line)
        self.set_markup(markup, -1)
