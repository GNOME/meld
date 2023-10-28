# Copyright (C) 2019 Kai Willadsen <kai.willadsen@gmail.com>
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

import bisect
from typing import Dict, Optional

from gi.repository import Gdk, GdkPixbuf, GObject, Gtk

from meld.conf import _
from meld.const import ActionMode, ChunkAction
from meld.settings import get_meld_settings
from meld.style import get_common_theme
from meld.ui.gtkcompat import get_style
from meld.ui.gtkutil import make_gdk_rgba


class ActionIcons:

    #: Fixed size of the renderer. Ideally this would be font-dependent and
    #: would adjust to other textview attributes, but that's both quite
    #: difficult and not necessarily desirable.
    pixbuf_height = 16
    icon_cache: Dict[str, GdkPixbuf.Pixbuf] = {}
    icon_name_prefix = 'meld-change'

    @classmethod
    def load(cls, icon_name: str):
        icon = cls.icon_cache.get(icon_name)

        if not icon:
            icon_theme = Gtk.IconTheme.get_default()
            icon = icon_theme.load_icon(
                f'{cls.icon_name_prefix}-{icon_name}', cls.pixbuf_height, 0)
            cls.icon_cache[icon_name] = icon

        return icon


class ActionGutter(Gtk.DrawingArea):

    __gtype_name__ = 'ActionGutter'

    action_mode = GObject.Property(
        type=int,
        nick='Action mode for chunk change actions',
        default=ActionMode.Replace,
    )

    @GObject.Property(
        type=object,
        nick='List of diff chunks for display',
    )
    def chunks(self):
        return self._chunks

    @chunks.setter
    def chunks_set(self, chunks):
        self._chunks = chunks
        self.chunk_starts = [c.start_a for c in chunks]

    @GObject.Property(
        type=Gtk.TextDirection,
        nick='Which direction should directional changes appear to go',
        flags=(
            GObject.ParamFlags.READABLE |
            GObject.ParamFlags.WRITABLE |
            GObject.ParamFlags.CONSTRUCT_ONLY
        ),
        default=Gtk.TextDirection.LTR,
    )
    def icon_direction(self):
        return self._icon_direction

    @icon_direction.setter
    def icon_direction_set(self, direction: Gtk.TextDirection):
        if direction not in (Gtk.TextDirection.LTR, Gtk.TextDirection.RTL):
            raise ValueError('Invalid icon direction {}'.format(direction))

        replace_icons = {
            Gtk.TextDirection.LTR: 'apply-right',
            Gtk.TextDirection.RTL: 'apply-left',
        }
        self.action_map = {
            ActionMode.Replace: ActionIcons.load(replace_icons[direction]),
            ActionMode.Delete: ActionIcons.load('delete'),
            ActionMode.Insert: ActionIcons.load('copy'),
        }
        self._icon_direction = direction

    _source_view: Gtk.TextView
    _source_editable_connect_id: int = 0

    @GObject.Property(
        type=Gtk.TextView,
        nick='Text view for which action are displayed',
        default=None,
    )
    def source_view(self):
        return self._source_view

    @source_view.setter
    def source_view_setter(self, view: Gtk.TextView):
        if self._source_editable_connect_id:
            self._source_view.disconnect(self._source_editable_connect_id)

        self._source_editable_connect_id = view.connect(
            'notify::editable', lambda *args: self.queue_draw())
        self._source_view = view
        self.queue_draw()

    _target_view: Gtk.TextView
    _target_editable_connect_id: int = 0

    @GObject.Property(
        type=Gtk.TextView,
        nick='Text view to which actions are directed',
        default=None,
    )
    def target_view(self):
        return self._target_view

    @target_view.setter
    def target_view_setter(self, view: Gtk.TextView):
        if self._target_editable_connect_id:
            self._target_view.disconnect(self._target_editable_connect_id)

        self._target_editable_connect_id = view.connect(
            'notify::editable', lambda *args: self.queue_draw())
        self._target_view = view
        self.queue_draw()

    @GObject.Signal
    def chunk_action_activated(
        self,
        action: str,  # String-ified ChunkAction
        from_view: Gtk.TextView,
        to_view: Gtk.TextView,
        chunk: object,
    ) -> None:
        ...

    def __init__(self):
        super().__init__()

        # Object-type defaults
        self.chunks = []
        self.action_map = {}

        # State for "button" implementation
        self.buttons = []
        self.pointer_chunk = None
        self.pressed_chunk = None

        self.motion_controller = Gtk.EventControllerMotion(widget=self)
        self.motion_controller.set_propagation_phase(Gtk.PropagationPhase.TARGET)
        self.motion_controller.connect("enter", self.motion_event)
        self.motion_controller.connect("leave", self.motion_event)
        self.motion_controller.connect("motion", self.motion_event)

    def on_setting_changed(self, settings, key):
        if key == 'style-scheme':
            self.fill_colors, self.line_colors = get_common_theme()
            alpha = self.fill_colors['current-chunk-highlight'].alpha
            self.chunk_highlights = {
                state: make_gdk_rgba(*[alpha + c * (1.0 - alpha) for c in colour])
                for state, colour in self.fill_colors.items()
            }

    def do_realize(self):
        self.set_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK |
            Gdk.EventMask.LEAVE_NOTIFY_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.SCROLL_MASK
        )
        self.connect('notify::action-mode', lambda *args: self.queue_draw())

        meld_settings = get_meld_settings()
        meld_settings.connect('changed', self.on_setting_changed)
        self.on_setting_changed(meld_settings, 'style-scheme')

        return Gtk.DrawingArea.do_realize(self)

    def update_pointer_chunk(self, x, y):
        # This is the simplest button/intersection implementation in
        # the world, but it basically works for our purposes.
        for button in self.buttons:
            x1, y1, x2, y2, chunk = button

            # Check y first; it's more likely to be out of range
            if y1 <= y <= y2 and x1 <= x <= x2:
                new_pointer_chunk = chunk
                break
        else:
            new_pointer_chunk = None

        if new_pointer_chunk != self.pointer_chunk:
            self.pointer_chunk = new_pointer_chunk
            self.queue_draw()

    def motion_event(
        self,
        controller: Gtk.EventControllerMotion,
        x: float | None = None,
        y: float | None = None,
    ):
        if x is None or y is None:
            # Missing coordinates are leave events
            if self.pointer_chunk:
                self.pointer_chunk = None
                self.queue_draw()
        else:
            # This is either an enter or motion event; we treat them the same
            self.update_pointer_chunk(x, y)

    def do_button_press_event(self, event):
        if self.pointer_chunk:
            self.pressed_chunk = self.pointer_chunk

        return Gtk.DrawingArea.do_button_press_event(self, event)

    def do_button_release_event(self, event):
        if self.pointer_chunk and self.pointer_chunk == self.pressed_chunk:
            self.activate(self.pressed_chunk)
        self.pressed_chunk = None

        return Gtk.DrawingArea.do_button_press_event(self, event)

    def _action_on_chunk(self, action: ChunkAction, chunk):
        self.chunk_action_activated.emit(
            action.value, self.source_view, self.target_view, chunk)

    def activate(self, chunk):

        action = self._classify_change_actions(chunk)

        # FIXME: When fully transitioned to GAction, we should see
        # whether we can do this by getting the container's action
        # group and activating the actions directly instead.

        if action == ActionMode.Replace:
            self._action_on_chunk(ChunkAction.replace, chunk)
        elif action == ActionMode.Delete:
            self._action_on_chunk(ChunkAction.delete, chunk)
        elif action == ActionMode.Insert:
            copy_menu = self._make_copy_menu(chunk)
            copy_menu.popup_at_pointer(None)

    def _make_copy_menu(self, chunk):
        copy_menu = Gtk.Menu()
        copy_up = Gtk.MenuItem.new_with_mnemonic(_('Copy _up'))
        copy_down = Gtk.MenuItem.new_with_mnemonic(_('Copy _down'))
        copy_menu.append(copy_up)
        copy_menu.append(copy_down)
        copy_menu.show_all()

        def copy_chunk(widget, action):
            self._action_on_chunk(action, chunk)

        copy_up.connect('activate', copy_chunk, ChunkAction.copy_up)
        copy_down.connect('activate', copy_chunk, ChunkAction.copy_down)
        return copy_menu

    def get_chunk_range(self, start_y, end_y):
        start_line = self.source_view.get_line_num_for_y(start_y)
        end_line = self.source_view.get_line_num_for_y(end_y)

        start_idx = bisect.bisect(self.chunk_starts, start_line)
        end_idx = bisect.bisect(self.chunk_starts, end_line)

        if start_idx > 0 and start_line <= self.chunks[start_idx - 1].end_a:
            start_idx -= 1

        return self.chunks[start_idx:end_idx]

    def do_draw(self, context):
        view = self.source_view
        if not view or not view.get_realized():
            return

        self.buttons = []

        width = self.get_allocated_width()
        height = self.get_allocated_height()

        style_context = self.get_style_context()
        Gtk.render_background(style_context, context, 0, 0, width, height)

        buf = view.get_buffer()

        context.save()
        context.set_line_width(1.0)

        # Get our linked view's visible offset, get our vertical offset
        # against our view (e.g., for info bars at the top of the view)
        # and translate our context to match.
        view_y_start = view.get_visible_rect().y
        view_y_offset = view.translate_coordinates(self, 0, 0)[1]
        gutter_y_translate = view_y_offset - view_y_start
        context.translate(0, gutter_y_translate)

        button_x = 1
        button_width = width - 2

        for chunk in self.get_chunk_range(view_y_start, view_y_start + height):

            change_type, start_line, end_line, *_unused = chunk

            rect_y = view.get_y_for_line_num(start_line)
            rect_height = max(
                0, view.get_y_for_line_num(end_line) - rect_y - 1)

            # Draw our rectangle outside x bounds, so we don't get
            # vertical lines. Fill first, over-fill with a highlight
            # if in the focused chunk, and then stroke the border.
            context.rectangle(-0.5, rect_y + 0.5, width + 1, rect_height)
            if start_line != end_line:
                context.set_source_rgba(*self.fill_colors[change_type])
                context.fill_preserve()
                if view.current_chunk_check(chunk):
                    highlight = self.fill_colors['current-chunk-highlight']
                    context.set_source_rgba(*highlight)
                    context.fill_preserve()
            context.set_source_rgba(*self.line_colors[change_type])
            context.stroke()

            # Button rendering and tracking
            action = self._classify_change_actions(chunk)
            if action is None:
                continue

            it = buf.get_iter_at_line(start_line)
            button_y, button_height = view.get_line_yrange(it)
            button_y += 1
            button_height -= 2

            button_style_context = get_style(None, 'button.flat.image-button')
            if chunk == self.pointer_chunk:
                button_style_context.set_state(Gtk.StateFlags.PRELIGHT)

            Gtk.render_background(
                button_style_context, context, button_x, button_y,
                button_width, button_height)
            Gtk.render_frame(
                button_style_context, context, button_x, button_y,
                button_width, button_height)

            # TODO: Ideally we'd do this in a pre-render step of some
            # kind, but I'm having trouble figuring out what that would
            # look like.
            self.buttons.append(
                (
                    button_x,
                    button_y + gutter_y_translate,
                    button_x + button_width,
                    button_y + gutter_y_translate + button_height,
                    chunk,
                )
            )

            pixbuf = self.action_map.get(action)
            icon_x = button_x + (button_width - pixbuf.props.width) // 2
            icon_y = button_y + (button_height - pixbuf.props.height) // 2
            Gtk.render_icon(
                button_style_context, context, pixbuf, icon_x, icon_y)

        context.restore()

    def _classify_change_actions(self, change) -> Optional[ActionMode]:
        """Classify possible actions for the given change

        Returns the action that can be performed given the content and
        context of the change.
        """
        source_editable = self.source_view.get_editable()
        target_editable = self.target_view.get_editable()

        if not source_editable and not target_editable:
            return None

        # Reclassify conflict changes, since we treat them the same as a
        # normal two-way change as far as actions are concerned
        change_type = change[0]
        if change_type == 'conflict':
            if change[1] == change[2]:
                change_type = 'insert'
            elif change[3] == change[4]:
                change_type = 'delete'
            else:
                change_type = 'replace'

        if change_type == 'insert':
            return None

        action = self.action_mode
        if action == ActionMode.Delete and not source_editable:
            action = None
        elif action == ActionMode.Insert and change_type == 'delete':
            action = ActionMode.Replace
        if not target_editable:
            action = ActionMode.Delete
        return action


ActionGutter.set_css_name('action-gutter')
