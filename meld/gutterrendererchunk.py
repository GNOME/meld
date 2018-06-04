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

from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import GtkSource
from gi.repository import Pango

from meld.conf import _
from meld.const import MODE_DELETE, MODE_INSERT, MODE_REPLACE
from meld.misc import get_common_theme
from meld.settings import meldsettings
from meld.ui.gtkcompat import get_style

# Fixed size of the renderer. Ideally this would be font-dependent and
# would adjust to other textview attributes, but that's both quite difficult
# and not necessarily desirable.
LINE_HEIGHT = 16

GTK_RENDERER_STATE_MAPPING = {
    GtkSource.GutterRendererState.NORMAL: Gtk.StateFlags.NORMAL,
    GtkSource.GutterRendererState.CURSOR: Gtk.StateFlags.FOCUSED,
    GtkSource.GutterRendererState.PRELIT: Gtk.StateFlags.PRELIGHT,
    GtkSource.GutterRendererState.SELECTED: Gtk.StateFlags.SELECTED,
}

ALIGN_MODE_FIRST = GtkSource.GutterRendererAlignmentMode.FIRST


def load(icon_name):
    icon_theme = Gtk.IconTheme.get_default()
    return icon_theme.load_icon(icon_name, LINE_HEIGHT, 0)


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


def renderer_to_gtk_state(state):
    gtk_state = Gtk.StateFlags(0)
    for renderer_flag, gtk_flag in GTK_RENDERER_STATE_MAPPING.items():
        if renderer_flag & state:
            gtk_state |= gtk_flag
    return gtk_state


class MeldGutterRenderer:

    def set_renderer_defaults(self):
        self.set_alignment_mode(GtkSource.GutterRendererAlignmentMode.FIRST)
        self.set_padding(3, 0)
        self.set_alignment(0.5, 0.5)

    def on_setting_changed(self, meldsettings, key):
        if key == 'style-scheme':
            self.fill_colors, self.line_colors = get_common_theme()
            alpha = self.fill_colors['current-chunk-highlight'].alpha
            self.chunk_highlights = {
                state: Gdk.RGBA(*[alpha + c * (1.0 - alpha) for c in colour])
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
        super().__init__()
        self.set_renderer_defaults()
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

        self.is_action = False
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
        elif action == MODE_REPLACE:
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

    def do_begin(self, *args):
        self.views_editable = [v.get_editable() for v in self.views]

    def do_draw(self, context, background_area, cell_area, start, end, state):
        GtkSource.GutterRendererPixbuf.do_draw(
            self, context, background_area, cell_area, start, end, state)
        if self.is_action:
            # TODO: Fix padding and min-height in CSS and use
            # draw_style_common
            style_context = get_style(None, "button.flat.image-button")
            style_context.set_state(renderer_to_gtk_state(state))

            x = background_area.x + 1
            y = background_area.y + 1
            width = background_area.width - 2
            height = background_area.height - 2

            Gtk.render_background(style_context, context, x, y, width, height)
            Gtk.render_frame(style_context, context, x, y, width, height)

            pixbuf = self.props.pixbuf
            pix_width, pix_height = pixbuf.props.width, pixbuf.props.height

            xalign, yalign = self.get_alignment()
            align_mode = self.get_alignment_mode()
            if align_mode == GtkSource.GutterRendererAlignmentMode.CELL:
                icon_x = x + (width - pix_width) // 2
                icon_y = y + (height - pix_height) // 2
            else:
                line_iter = start if align_mode == ALIGN_MODE_FIRST else end
                textview = self.get_view()
                loc = textview.get_iter_location(line_iter)
                line_x, line_y = textview.buffer_to_window_coords(
                    self.get_window_type(), loc.x, loc.y)
                icon_x = cell_area.x + (cell_area.width - pix_width) * xalign
                icon_y = line_y + (loc.height - pix_height) * yalign

            Gtk.render_icon(style_context, context, pixbuf, icon_x, icon_y)

        self.draw_chunks(
            context, background_area, cell_area, start, end, state)

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
        self.query_chunks(start, end, state)
        line = start.get_line()

        if self._chunk and self._chunk[1] == line:
            action = self._classify_change_actions(self._chunk)
            pixbuf = self.action_map.get(action)
        else:
            pixbuf = None
        self.is_action = bool(pixbuf)
        self.props.pixbuf = pixbuf

    def on_container_mode_changed(self, container, mode):
        self.mode = mode
        self.queue_draw()

    def _classify_change_actions(self, change):
        """Classify possible actions for the given change

        Returns the action that can be performed given the content and
        context of the change.
        """
        editable, other_editable = self.views_editable

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

        if change_type == 'insert':
            return None

        action = self.mode
        if action == MODE_DELETE and not editable:
            action = None
        elif action == MODE_INSERT and change_type == 'delete':
            action = MODE_REPLACE
        if not other_editable:
            action = MODE_DELETE
        return action


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
