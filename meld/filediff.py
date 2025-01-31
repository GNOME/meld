# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009-2019 Kai Willadsen <kai.willadsen@gmail.com>
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

import copy
import functools
import logging
import math
from enum import Enum
from typing import Optional, Tuple, Type

from gi.repository import Gdk, Gio, GLib, GObject, Gtk, GtkSource

# TODO: Don't from-import whole modules
from meld import misc
from meld.conf import _
from meld.const import (
    NEWLINES,
    TEXT_FILTER_ACTION_FORMAT,
    ActionMode,
    ChunkAction,
    FileComparisonMode,
    FileLoadError,
)
from meld.externalhelpers import open_files_external
from meld.gutterrendererchunk import GutterRendererChunkLines
from meld.iohelpers import find_shared_parent_path, prompt_save_filename
from meld.matchers.diffutil import Differ, merged_chunk_order
from meld.matchers.helpers import CachedSequenceMatcher
from meld.matchers.merge import AutoMergeDiffer, Merger
from meld.meldbuffer import (
    BufferDeletionAction,
    BufferInsertionAction,
    BufferLines,
    MeldBufferState,
)
from meld.melddoc import ComparisonState, MeldDoc
from meld.menuhelpers import replace_menu_section
from meld.misc import user_critical, with_focused_pane
from meld.patchdialog import PatchDialog
from meld.recent import RecentType
from meld.settings import bind_settings, get_meld_settings
from meld.sourceview import (
    LanguageManager,
    TextviewLineAnimationType,
    get_custom_encoding_candidates,
)
from meld.ui.findbar import FindBar
from meld.ui.util import (
    make_multiobject_property_action,
    map_widgets_into_lists,
)
from meld.undo import UndoSequence

log = logging.getLogger(__name__)


def with_scroll_lock(lock_attr):
    """Decorator for locking a callback based on an instance attribute

    This is used when scrolling panes. Since a scroll event in one pane
    causes us to set the scroll position in other panes, we need to
    stop these other panes re-scrolling the initial one.

    Unlike a threading-style lock, this decorator discards any calls
    that occur while the lock is held, rather than queuing them.

    :param lock_attr: The instance attribute used to lock access
    """
    def wrap(function):
        @functools.wraps(function)
        def wrap_function(locked, *args, **kwargs):
            force_locked = locked.props.lock_scrolling
            if getattr(locked, lock_attr, False) or force_locked:
                return

            try:
                setattr(locked, lock_attr, True)
                return function(locked, *args, **kwargs)
            finally:
                setattr(locked, lock_attr, False)
        return wrap_function
    return wrap


MASK_SHIFT, MASK_CTRL = 1, 2
PANE_LEFT, PANE_RIGHT = -1, +1

LOAD_PROGRESS_MARK = "meld-load-progress"
#: Line length at which we'll cancel loads because of potential hangs
LINE_LENGTH_LIMIT = 8 * 1024

class CursorDetails:
    __slots__ = (
        "pane", "pos", "line", "chunk", "prev", "next",
        "prev_conflict", "next_conflict",
    )

    def __init__(self):
        for var in self.__slots__:
            setattr(self, var, None)


@Gtk.Template(resource_path='/org/gnome/meld/ui/filediff.ui')
class FileDiff(Gtk.Box, MeldDoc):
    """Two or three way comparison of text files"""

    __gtype_name__ = "FileDiff"

    close_signal = MeldDoc.close_signal
    create_diff_signal = MeldDoc.create_diff_signal
    file_changed_signal = MeldDoc.file_changed_signal
    label_changed = MeldDoc.label_changed
    move_diff = MeldDoc.move_diff
    tab_state_changed = MeldDoc.tab_state_changed

    __gsettings_bindings_view__ = (
        ('ignore-blank-lines', 'ignore-blank-lines'),
        ('show-overview-map', 'show-overview-map'),
        ('overview-map-style', 'overview-map-style'),
    )

    ignore_blank_lines = GObject.Property(
        type=bool,
        nick="Ignore blank lines",
        blurb="Whether to ignore blank lines when comparing file contents",
        default=False,
    )
    show_overview_map = GObject.Property(type=bool, default=True)
    overview_map_style = GObject.Property(type=str, default='chunkmap')

    actiongutter0 = Gtk.Template.Child()
    actiongutter1 = Gtk.Template.Child()
    actiongutter2 = Gtk.Template.Child()
    actiongutter3 = Gtk.Template.Child()
    chunkmap0 = Gtk.Template.Child()
    chunkmap1 = Gtk.Template.Child()
    chunkmap2 = Gtk.Template.Child()
    chunkmap_hbox = Gtk.Template.Child()
    dummy_toolbar_actiongutter0 = Gtk.Template.Child()
    dummy_toolbar_actiongutter1 = Gtk.Template.Child()
    dummy_toolbar_actiongutter2 = Gtk.Template.Child()
    dummy_toolbar_actiongutter3 = Gtk.Template.Child()
    dummy_toolbar_linkmap0 = Gtk.Template.Child()
    dummy_toolbar_linkmap1 = Gtk.Template.Child()
    file_open_button0 = Gtk.Template.Child()
    file_open_button1 = Gtk.Template.Child()
    file_open_button2 = Gtk.Template.Child()
    file_save_button0 = Gtk.Template.Child()
    file_save_button1 = Gtk.Template.Child()
    file_save_button2 = Gtk.Template.Child()
    file_toolbar0 = Gtk.Template.Child()
    file_toolbar1 = Gtk.Template.Child()
    file_toolbar2 = Gtk.Template.Child()
    filelabel0 = Gtk.Template.Child()
    filelabel1 = Gtk.Template.Child()
    filelabel2 = Gtk.Template.Child()
    grid = Gtk.Template.Child()
    msgarea_mgr0 = Gtk.Template.Child()
    msgarea_mgr1 = Gtk.Template.Child()
    msgarea_mgr2 = Gtk.Template.Child()
    readonlytoggle0 = Gtk.Template.Child()
    readonlytoggle1 = Gtk.Template.Child()
    readonlytoggle2 = Gtk.Template.Child()
    scrolledwindow0 = Gtk.Template.Child()
    scrolledwindow1 = Gtk.Template.Child()
    scrolledwindow2 = Gtk.Template.Child()
    sourcemap_revealer = Gtk.Template.Child()
    sourcemap0 = Gtk.Template.Child()
    sourcemap1 = Gtk.Template.Child()
    sourcemap2 = Gtk.Template.Child()
    sourcemap_hbox = Gtk.Template.Child()
    statusbar0 = Gtk.Template.Child()
    statusbar1 = Gtk.Template.Child()
    statusbar2 = Gtk.Template.Child()
    statusbar_sourcemap_revealer = Gtk.Template.Child()
    linkmap0 = Gtk.Template.Child()
    linkmap1 = Gtk.Template.Child()
    textview0 = Gtk.Template.Child()
    textview1 = Gtk.Template.Child()
    textview2 = Gtk.Template.Child()
    toolbar_sourcemap_revealer = Gtk.Template.Child()
    vbox0 = Gtk.Template.Child()
    vbox1 = Gtk.Template.Child()
    vbox2 = Gtk.Template.Child()

    differ: Type[Differ]
    comparison_mode: FileComparisonMode

    keylookup = {
        Gdk.KEY_Shift_L: MASK_SHIFT,
        Gdk.KEY_Shift_R: MASK_SHIFT,
        Gdk.KEY_Control_L: MASK_CTRL,
        Gdk.KEY_Control_R: MASK_CTRL,
    }

    # Identifiers for MsgArea messages
    (MSG_SAME, MSG_SLOW_HIGHLIGHT, MSG_SYNCPOINTS) = list(range(3))
    # Transient messages that should be removed if any file in the
    # comparison gets reloaded.
    TRANSIENT_MESSAGES = {MSG_SAME, MSG_SLOW_HIGHLIGHT}

    __gsignals__ = {
        'next-conflict-changed': (
            GObject.SignalFlags.RUN_FIRST, None, (bool, bool)),
    }

    action_mode = GObject.Property(
        type=int,
        nick='Action mode for chunk change actions',
        default=ActionMode.Replace,
    )

    lock_scrolling = GObject.Property(
        type=bool,
        nick='Lock scrolling of all panes',
        default=False,
    )

    def __init__(
        self,
        num_panes,
        *,
        comparison_mode: FileComparisonMode = FileComparisonMode.Compare,
    ):
        super().__init__()
        # FIXME:
        # This unimaginable hack exists because GObject (or GTK+?)
        # doesn't actually correctly chain init calls, even if they're
        # not to GObjects. As a workaround, we *should* just be able to
        # put our class first, but because of Gtk.Template we can't do
        # that if it's a GObject, because GObject doesn't support
        # multiple inheritance and we need to inherit from our Widget
        # parent to make Template work.
        MeldDoc.__init__(self)
        bind_settings(self)

        widget_lists = [
            "sourcemap", "file_save_button", "file_toolbar",
            "linkmap", "msgarea_mgr", "readonlytoggle",
            "scrolledwindow", "textview", "vbox",
            "dummy_toolbar_linkmap", "filelabel",
            "file_open_button", "statusbar",
            "actiongutter", "dummy_toolbar_actiongutter",
            "chunkmap",
        ]
        map_widgets_into_lists(self, widget_lists)

        self.comparison_mode = comparison_mode
        if comparison_mode == FileComparisonMode.AutoMerge:
            self.differ = AutoMergeDiffer
        else:
            self.differ = Differ

        self.warned_bad_comparison = False
        self._keymask = 0
        self.meta = {}
        self.lines_removed = 0
        self.focus_pane = None
        self.textbuffer = [v.get_buffer() for v in self.textview]
        self.buffer_texts = [BufferLines(b) for b in self.textbuffer]
        self.undosequence = UndoSequence(self.textbuffer)
        self.text_filters = []
        meld_settings = get_meld_settings()
        self.settings_handlers = [
            meld_settings.connect(
                "text-filters-changed", self.on_text_filters_changed)
        ]
        self.buffer_filtered = [
            BufferLines(b, self._filter_text) for b in self.textbuffer
        ]
        for (i, w) in enumerate(self.scrolledwindow):
            w.get_vadjustment().connect("value-changed", self._sync_vscroll, i)
            w.get_hadjustment().connect("value-changed", self._sync_hscroll)
        self._connect_buffer_handlers()
        self._sync_vscroll_lock = False
        self._sync_hscroll_lock = False
        self.linediffer = self.differ()
        self.force_highlight = False

        def get_mark_line(pane, mark):
            return self.textbuffer[pane].get_iter_at_mark(mark).get_line()

        self.syncpoints = Syncpoints(num_panes, get_mark_line)
        self.in_nested_textview_gutter_expose = False
        self._cached_match = CachedSequenceMatcher(self.scheduler)

        # Set up property actions for statusbar toggles
        sourceview_prop_actions = [
            'draw-spaces-bool',
            'highlight-current-line-local',
            'show-line-numbers',
            'wrap-mode-bool',
        ]

        prop_action_group = Gio.SimpleActionGroup()
        for prop in sourceview_prop_actions:
            action = make_multiobject_property_action(self.textview, prop)
            prop_action_group.add_action(action)
        self.insert_action_group('view-local', prop_action_group)

        # Set up per-view action group for top-level menu insertion
        self.view_action_group = Gio.SimpleActionGroup()

        property_actions = (
            ('show-overview-map', self, 'show-overview-map'),
            ('lock-scrolling', self, 'lock_scrolling'),
        )
        for action_name, obj, prop_name in property_actions:
            action = Gio.PropertyAction.new(action_name, obj, prop_name)
            self.view_action_group.add_action(action)

        # Manually handle GAction additions
        actions = (
            ('add-sync-point', self.add_sync_point),
            ('remove-sync-point', self.remove_sync_point),
            ('clear-sync-point', self.clear_sync_points),
            ('copy', self.action_copy),
            ('copy-full-path', self.action_copy_full_path),
            ('cut', self.action_cut),
            ('file-previous-conflict', self.action_previous_conflict),
            ('file-next-conflict', self.action_next_conflict),
            ('file-push-left', self.action_push_change_left),
            ('file-push-right', self.action_push_change_right),
            ('file-pull-left', self.action_pull_change_left),
            ('file-pull-right', self.action_pull_change_right),
            ('file-copy-left-up', self.action_copy_change_left_up),
            ('file-copy-right-up', self.action_copy_change_right_up),
            ('file-copy-left-down', self.action_copy_change_left_down),
            ('file-copy-right-down', self.action_copy_change_right_down),
            ('file-delete', self.action_delete_change),
            ('find', self.action_find),
            ('find-next', self.action_find_next),
            ('find-previous', self.action_find_previous),
            ('find-replace', self.action_find_replace),
            ('format-as-patch', self.action_format_as_patch),
            ('go-to-line', self.action_go_to_line),
            ('merge-all-left', self.action_pull_all_changes_left),
            ('merge-all-right', self.action_pull_all_changes_right),
            ('merge-all', self.action_merge_all_changes),
            ('next-change', self.action_next_change),
            ('next-pane', self.action_next_pane),
            ('open-external', self.action_open_external),
            ('open-folder', self.action_open_folder),
            ('paste', self.action_paste),
            ('previous-change', self.action_previous_change),
            ('previous-pane', self.action_prev_pane),
            ('redo', self.action_redo),
            ('refresh', self.action_refresh),
            ('revert', self.action_revert),
            ('save', self.action_save),
            ('save-all', self.action_save_all),
            ('save-as', self.action_save_as),
            ('undo', self.action_undo),
            ('swap-2-panes', self.action_swap),
        )
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.view_action_group.add_action(action)

        state_actions = (
            ("text-filter", None, GLib.Variant.new_boolean(False)),
        )
        for (name, callback, state) in state_actions:
            action = Gio.SimpleAction.new_stateful(name, None, state)
            if callback:
                action.connect("change-state", callback)
            self.view_action_group.add_action(action)

        builder = Gtk.Builder.new_from_resource(
            '/org/gnome/meld/ui/filediff-menus.ui')
        self.popup_menu_model = builder.get_object('filediff-context-menu')
        self.popup_menu = Gtk.Menu.new_from_model(self.popup_menu_model)
        self.popup_menu.attach_to_widget(self)

        builder = Gtk.Builder.new_from_resource(
            '/org/gnome/meld/ui/filediff-actions.ui')
        self.toolbar_actions = builder.get_object('view-toolbar')
        self.copy_action_button = builder.get_object('copy_action_button')

        self.create_text_filters()

        # Handle overview map visibility binding. Because of how we use
        # grid packing, we need three revealers here instead of the
        # more obvious one.
        revealers = (
            self.toolbar_sourcemap_revealer,
            self.sourcemap_revealer,
            self.statusbar_sourcemap_revealer,
        )
        for revealer in revealers:
            self.bind_property(
                'show-overview-map', revealer, 'reveal-child',
                (
                    GObject.BindingFlags.DEFAULT |
                    GObject.BindingFlags.SYNC_CREATE
                ),
            )

        # Handle overview map style mapping manually
        self.connect(
            'notify::overview-map-style', self.on_overview_map_style_changed)
        self.on_overview_map_style_changed()

        for buf in self.textbuffer:
            buf.create_mark(LOAD_PROGRESS_MARK, buf.get_start_iter(), True)
            buf.undo_sequence = self.undosequence
            buf.connect(
                'notify::has-selection', self.update_text_actions_sensitivity)
            buf.data.file_changed_signal.connect(self.notify_file_changed)
        self.update_text_actions_sensitivity()

        self.findbar = FindBar(self.grid)
        self.grid.attach(self.findbar, 0, 2, 10, 1)

        self.set_num_panes(num_panes)
        self.cursor = CursorDetails()
        for t in self.textview:
            t.connect("focus-in-event", self.on_current_diff_changed)
            t.connect("focus-out-event", self.on_current_diff_changed)
            t.connect(
                "drag_data_received", self.on_textview_drag_data_received)

        for label in self.filelabel:
            label.connect(
                "drag_data_received", self.on_textview_drag_data_received
            )

        # Bind all overwrite properties together, so that toggling
        # overwrite mode is per-FileDiff.
        for t in self.textview[1:]:
            t.bind_property(
                'overwrite', self.textview[0], 'overwrite',
                GObject.BindingFlags.BIDIRECTIONAL)

        for gutter in self.actiongutter:
            self.bind_property('action_mode', gutter, 'action_mode')
            gutter.connect(
                'chunk_action_activated', self.on_chunk_action_activated)

        self.linediffer.connect("diffs-changed", self.on_diffs_changed)
        self.undosequence.connect("checkpointed", self.on_undo_checkpointed)
        self.undosequence.connect("can-undo", self.on_can_undo)
        self.undosequence.connect("can-redo", self.on_can_redo)
        self.connect("next-conflict-changed", self.on_next_conflict_changed)

        # TODO: If UndoSequence expose can_undo and can_redo as
        # GProperties instead, this would be much, much nicer.
        self.set_action_enabled('redo', self.undosequence.can_redo())
        self.set_action_enabled('undo', self.undosequence.can_undo())

        for statusbar, buf in zip(self.statusbar, self.textbuffer):
            buf.bind_property(
                'cursor-position', statusbar, 'cursor_position',
                GObject.BindingFlags.DEFAULT,
                self.bind_adapt_cursor_position,
            )

            buf.bind_property(
                'language', statusbar, 'source-language',
                GObject.BindingFlags.BIDIRECTIONAL)

            buf.data.bind_property(
                'encoding', statusbar, 'source-encoding',
                GObject.BindingFlags.DEFAULT)

            def reload_with_encoding(widget, encoding, pane):
                buffer = self.textbuffer[pane]
                if not self.check_unsaved_changes([buffer]):
                    return
                self.set_file(pane, buffer.data.gfile, encoding)

            def go_to_line(widget, line, pane):
                if self.cursor.pane == pane and self.cursor.line == line:
                    return
                self.move_cursor(pane, line, focus=False)

            pane = self.statusbar.index(statusbar)
            statusbar.connect('encoding-changed', reload_with_encoding, pane)
            statusbar.connect('go-to-line', go_to_line, pane)

        # Prototype implementation
        for pane, t in enumerate(self.textview):
            # FIXME: set_num_panes will break this good
            direction = t.get_direction()

            # TODO: This renderer handling should all be part of
            # MeldSourceView, but our current diff-chunk-handling makes
            # this difficult.
            window = Gtk.TextWindowType.LEFT
            if direction == Gtk.TextDirection.RTL:
                window = Gtk.TextWindowType.RIGHT
            renderer = GutterRendererChunkLines(
                pane, pane - 1, self.linediffer)
            gutter = t.get_gutter(window)
            gutter.insert(renderer, -30)
            t.line_renderer = renderer

        self.connect("notify::ignore-blank-lines", self.refresh_comparison)

    def do_realize(self):
        Gtk.Box().do_realize(self)

        builder = Gtk.Builder.new_from_resource(
            '/org/gnome/meld/ui/filediff-menus.ui')
        filter_menu = builder.get_object('file-copy-actions-menu')

        self.copy_action_button.set_popover(
            Gtk.Popover.new_from_model(self.copy_action_button, filter_menu))

    def get_keymask(self):
        return self._keymask

    def set_keymask(self, value):
        if value & MASK_SHIFT:
            mode = ActionMode.Delete
        elif value & MASK_CTRL:
            mode = ActionMode.Insert
        else:
            mode = ActionMode.Replace
        self._keymask = value
        self.action_mode = mode

    keymask = property(get_keymask, set_keymask)

    @Gtk.Template.Callback()
    def on_key_event(self, object, event):
        keymap = Gdk.Keymap.get_default()
        ok, keyval, group, lvl, consumed = keymap.translate_keyboard_state(
            event.hardware_keycode, 0, event.group)
        mod_key = self.keylookup.get(keyval, 0)
        if event.type == Gdk.EventType.KEY_PRESS:
            self.keymask |= mod_key
            if event.keyval == Gdk.KEY_Escape:
                self.findbar.hide()
        elif event.type == Gdk.EventType.KEY_RELEASE:
            self.keymask &= ~mod_key

    def on_overview_map_style_changed(self, *args):
        style = self.props.overview_map_style
        self.chunkmap_hbox.set_visible(style == 'chunkmap')
        self.sourcemap_hbox.set_visible(
            style in ('compact-sourcemap', 'full-sourcemap'))
        for sourcemap in self.sourcemap:
            sourcemap.props.compact_view = style == 'compact-sourcemap'

    def get_filter_visibility(self) -> Tuple[bool, bool, bool]:
        return True, False, False

    def get_conflict_visibility(self) -> bool:
        return self.num_panes == 3

    def on_text_filters_changed(self, app):
        relevant_change = self.create_text_filters()
        if relevant_change:
            self.refresh_comparison()

    def _update_text_filter(self, action, state):
        self._action_text_filter_map[action].active = state.get_boolean()
        action.set_state(state)
        self.refresh_comparison()

    def create_text_filters(self):
        meld_settings = get_meld_settings()

        # In contrast to file filters, ordering of text filters can matter
        old_active = [f.filter_string for f in self.text_filters if f.active]
        new_active = [
            f.filter_string for f in meld_settings.text_filters if f.active
        ]
        active_filters_changed = old_active != new_active

        # TODO: Rework text_filters to use a map-like structure so that we
        # don't need _action_text_filter_map.
        self._action_text_filter_map = {}
        self.text_filters = [copy.copy(f) for f in meld_settings.text_filters]
        for i, filt in enumerate(self.text_filters):
            action = Gio.SimpleAction.new_stateful(
                name=TEXT_FILTER_ACTION_FORMAT.format(i),
                parameter_type=None,
                state=GLib.Variant.new_boolean(filt.active),
            )
            action.connect('change-state', self._update_text_filter)
            action.set_enabled(filt.filter is not None)
            self.view_action_group.add_action(action)
            self._action_text_filter_map[action] = filt

        return active_filters_changed

    def _disconnect_buffer_handlers(self):
        for textview in self.textview:
            textview.set_sensitive(False)
        for buf in self.textbuffer:
            for h in buf.handlers:
                buf.disconnect(h)
            buf.handlers = []

    def _connect_buffer_handlers(self):
        for textview in self.textview:
            textview.set_sensitive(True)
        for buf in self.textbuffer:
            id0 = buf.connect("insert-text", self.on_text_insert_text)
            id1 = buf.connect("delete-range", self.on_text_delete_range)
            id2 = buf.connect_after("insert-text", self.after_text_insert_text)
            id3 = buf.connect_after(
                "delete-range", self.after_text_delete_range)
            id4 = buf.connect(
                "notify::cursor-position", self.on_cursor_position_changed)
            buf.handlers = id0, id1, id2, id3, id4

        if self.comparison_mode == FileComparisonMode.AutoMerge:
            self.textview[0].set_editable(0)
            self.textview[2].set_editable(0)

    def bind_adapt_cursor_position(self, binding, from_value):
        buf = binding.get_source()
        textview = self.textview[self.textbuffer.index(buf)]

        cursor_it = buf.get_iter_at_offset(from_value)
        offset = textview.get_visual_column(cursor_it)
        line = cursor_it.get_line()

        return (line, offset)

    def on_cursor_position_changed(self, buf, pspec, force=False):

        # Avoid storing cursor changes for non-focused panes. These
        # happen when we e.g., copy a chunk between panes.
        if not self.focus_pane or self.focus_pane.get_buffer() != buf:
            return

        pane = self.textbuffer.index(buf)
        pos = buf.props.cursor_position
        if pane == self.cursor.pane and pos == self.cursor.pos and not force:
            return
        self.cursor.pane, self.cursor.pos = pane, pos

        cursor_it = buf.get_iter_at_offset(pos)
        line = cursor_it.get_line()

        if line != self.cursor.line or force:
            chunk, prev, next_ = self.linediffer.locate_chunk(pane, line)
            if chunk != self.cursor.chunk or force:
                self.cursor.chunk = chunk
                self.on_current_diff_changed()
            if prev != self.cursor.prev or next_ != self.cursor.next or force:
                self.set_action_enabled("previous-change", prev is not None)
                self.set_action_enabled("next-change", next_ is not None)

            prev_conflict, next_conflict = None, None
            for conflict in self.linediffer.conflicts:
                if prev is not None and conflict <= prev:
                    prev_conflict = conflict
                if next_ is not None and conflict >= next_:
                    next_conflict = conflict
                    break
            if prev_conflict != self.cursor.prev_conflict or \
               next_conflict != self.cursor.next_conflict or force:
                self.emit("next-conflict-changed", prev_conflict is not None,
                          next_conflict is not None)

            self.cursor.prev, self.cursor.next = prev, next_
            self.cursor.prev_conflict = prev_conflict
            self.cursor.next_conflict = next_conflict

        self.cursor.line = line

    def on_current_diff_changed(self, *args):
        try:
            pane = self.textview.index(self.focus_pane)
        except ValueError:
            pane = -1

        if pane != -1:
            # While this *should* be redundant, it's possible for focus pane
            # and cursor pane to be different in several situations.
            pane = self.cursor.pane
            chunk_id = self.cursor.chunk

        if pane == -1 or chunk_id is None:
            push_left, push_right, pull_left, pull_right, delete, \
                copy_left, copy_right = (False,) * 7
        else:
            push_left, push_right, pull_left, pull_right, delete, \
                copy_left, copy_right = (True,) * 7

            three_way = self.num_panes == 3

            # Push and Delete are active if the current pane has something to
            # act on, and the target pane exists and is editable. Pull is
            # sensitive if the source pane has something to get, and the
            # current pane is editable. Copy actions are sensitive if the
            # conditions for push are met, *and* there is some content in the
            # target pane.
            editable = self.textview[pane].get_editable()
            # editable_left is relative to current pane and it is False for the
            # leftmost frame. The same logic applies to editable_right.
            editable_left = pane > 0 and self.textview[pane - 1].get_editable()
            editable_right = (
                pane < self.num_panes - 1 and
                self.textview[pane + 1].get_editable()
            )
            if pane == 0 or pane == 2:
                chunk = self.linediffer.get_chunk(chunk_id, pane)
                is_insert = chunk[1] == chunk[2]
                is_delete = chunk[3] == chunk[4]
                push_left = editable_left
                push_right = editable_right
                pull_left = pane == 2 and editable and not is_delete
                pull_right = pane == 0 and editable and not is_delete
                delete = editable and not is_insert
                copy_left = editable_left and not (is_insert or is_delete)
                copy_right = editable_right and not (is_insert or is_delete)
            elif pane == 1:
                chunk0 = self.linediffer.get_chunk(chunk_id, 1, 0)
                chunk2 = None
                if three_way:
                    chunk2 = self.linediffer.get_chunk(chunk_id, 1, 2)
                left_mid_exists = bool(chunk0 and chunk0[1] != chunk0[2])
                left_exists = bool(chunk0 and chunk0[3] != chunk0[4])
                right_mid_exists = bool(chunk2 and chunk2[1] != chunk2[2])
                right_exists = bool(chunk2 and chunk2[3] != chunk2[4])
                push_left = editable_left and bool(not three_way or chunk0)
                push_right = editable_right and bool(not three_way or chunk2)
                pull_left = editable and left_exists
                pull_right = editable and right_exists
                delete = editable and (left_mid_exists or right_mid_exists)
                copy_left = editable_left and left_mid_exists and left_exists
                copy_right = (
                    editable_right and right_mid_exists and right_exists)

            # If there is chunk and there are only two panes (#25)
            if self.num_panes == 2:
                pane0_editable = self.textview[0].get_editable()
                pane1_editable = self.textview[1].get_editable()
                push_left = pane0_editable
                push_right = pane1_editable

        self.set_action_enabled('file-push-left', push_left)
        self.set_action_enabled('file-push-right', push_right)
        self.set_action_enabled('file-pull-left', pull_left)
        self.set_action_enabled('file-pull-right', pull_right)
        self.set_action_enabled('file-delete', delete)
        self.set_action_enabled('file-copy-left-up', copy_left)
        self.set_action_enabled('file-copy-left-down', copy_left)
        self.set_action_enabled('file-copy-right-up', copy_right)
        self.set_action_enabled('file-copy-right-down', copy_right)
        self.set_action_enabled('previous-pane', pane > 0)
        self.set_action_enabled('next-pane', pane < self.num_panes - 1)
        self.set_action_enabled('swap-2-panes', self.num_panes == 2)

        self.update_text_actions_sensitivity()

        # FIXME: don't queue_draw() on everything... just on what changed
        self.queue_draw()

    def on_next_conflict_changed(self, doc, have_prev, have_next):
        self.set_action_enabled('file-previous-conflict', have_prev)
        self.set_action_enabled('file-next-conflict', have_next)

    def scroll_to_chunk_index(self, chunk_index, tolerance):
        """Scrolls chunks with the given index on screen in all panes"""
        starts = self.linediffer.get_chunk_starts(chunk_index)
        for pane, start in enumerate(starts):
            if start is None:
                continue
            buf = self.textbuffer[pane]
            it = buf.get_iter_at_line(start)
            self.textview[pane].scroll_to_iter(it, tolerance, True, 0.5, 0.5)

    def go_to_chunk(self, target, pane=None, centered=False):
        if target is None:
            self.error_bell()
            return

        if pane is None:
            pane = self._get_focused_pane()
            if pane == -1:
                pane = 1 if self.num_panes > 1 else 0

        chunk = self.linediffer.get_chunk(target, pane)
        if not chunk:
            self.error_bell()
            return

        # Warp the cursor to the first line of the chunk
        buf = self.textbuffer[pane]
        if self.cursor.line != chunk[1]:
            buf.place_cursor(buf.get_iter_at_line(chunk[1]))

        # Scroll all panes to the given chunk, and then ensure that the newly
        # placed cursor is definitely on-screen.
        tolerance = 0.0 if centered else 0.2
        self.scroll_to_chunk_index(target, tolerance)
        self.textview[pane].scroll_to_mark(
            buf.get_insert(), tolerance, True, 0.5, 0.5)

        # If we've moved to a valid chunk (or stayed in the first/last chunk)
        # then briefly highlight the chunk for better visual orientation.
        chunk_start = buf.get_iter_at_line_or_eof(chunk[1])
        chunk_end = buf.get_iter_at_line_or_eof(chunk[2])
        mark0 = buf.create_mark(None, chunk_start, True)
        mark1 = buf.create_mark(None, chunk_end, True)
        self.textview[pane].add_fading_highlight(
            mark0, mark1, 'focus-highlight', 400000, starting_alpha=0.3,
            anim_type=TextviewLineAnimationType.stroke)

    @Gtk.Template.Callback()
    def on_linkmap_scroll_event(self, linkmap, event):
        self.next_diff(event.direction, use_viewport=True)

    def _is_chunk_in_area(
            self, chunk_id: Optional[int], pane: int, area: Gdk.Rectangle):

        if chunk_id is None:
            return False

        chunk = self.linediffer.get_chunk(chunk_id, pane)
        target_iter = self.textbuffer[pane].get_iter_at_line(chunk.start_a)
        target_y, _height = self.textview[pane].get_line_yrange(target_iter)
        return area.y <= target_y <= area.y + area.height

    def next_diff(self, direction, centered=False, use_viewport=False):
        # use_viewport: seek next and previous diffes based on where
        # the user is currently scrolling at.
        scroll_down = direction == Gdk.ScrollDirection.DOWN
        target = self.cursor.next if scroll_down else self.cursor.prev

        if use_viewport:
            pane = self.cursor.pane
            text_area = self.textview[pane].get_visible_rect()

            # Only do viewport-relative calculations if the chunk we'd
            # otherwise scroll to is *not* on screen. This avoids 3-way
            # comparison cases where scrolling won't go past a chunk
            # because the scroll doesn't go past 50% of the screen.
            if not self._is_chunk_in_area(target, pane, text_area):
                halfscreen = text_area.y + text_area.height / 2
                halfline = self.textview[pane].get_line_at_y(
                    halfscreen).target_iter.get_line()

                _, prev, next_ = self.linediffer.locate_chunk(1, halfline)
                target = next_ if scroll_down else prev

        self.go_to_chunk(target, centered=centered)

    def action_previous_change(self, *args):
        self.next_diff(Gdk.ScrollDirection.UP)

    def action_next_change(self, *args):
        self.next_diff(Gdk.ScrollDirection.DOWN)

    def action_previous_conflict(self, *args):
        self.go_to_chunk(self.cursor.prev_conflict, self.cursor.pane)

    def action_next_conflict(self, *args):
        self.go_to_chunk(self.cursor.next_conflict, self.cursor.pane)

    def action_previous_diff(self, *args):
        self.go_to_chunk(self.cursor.prev)

    def action_next_diff(self, *args):
        self.go_to_chunk(self.cursor.next)

    def get_action_chunk(self, src, dst):
        valid_panes = list(range(0, self.num_panes))
        if src not in valid_panes or dst not in valid_panes:
            raise ValueError("Action was taken on invalid panes")
        if self.cursor.chunk is None:
            raise ValueError("Action was taken without chunk")

        chunk = self.linediffer.get_chunk(self.cursor.chunk, src, dst)
        if chunk is None:
            raise ValueError("Action was taken on a missing chunk")
        return chunk

    def get_action_panes(self, direction, reverse=False):
        src = self._get_focused_pane()
        dst = src + direction
        return (dst, src) if reverse else (src, dst)

    def on_chunk_action_activated(
            self, gutter, action, from_view, to_view, chunk):

        try:
            chunk_action = ChunkAction(action)
        except ValueError:
            log.error('Invalid chunk action %s', action)
            return

        # TODO: There's no reason the replace_chunk(), etc. calls should take
        # an index instead of just taking the views themselves.
        from_pane = self.textview.index(from_view)
        to_pane = self.textview.index(to_view)

        if chunk_action == ChunkAction.replace:
            self.replace_chunk(from_pane, to_pane, chunk)
        elif chunk_action == ChunkAction.delete:
            self.delete_chunk(from_pane, chunk)
        elif chunk_action == ChunkAction.copy_up:
            self.copy_chunk(from_pane, to_pane, chunk, copy_up=True)
        elif chunk_action == ChunkAction.copy_down:
            self.copy_chunk(from_pane, to_pane, chunk, copy_up=False)

    def action_push_change_left(self, *args):
        if self.num_panes == 2:
            src, dst = 1, 0
        else:
            src, dst = self.get_action_panes(PANE_LEFT)
        self.replace_chunk(src, dst, self.get_action_chunk(src, dst))

    def action_push_change_right(self, *args):
        if self.num_panes == 2:
            src, dst = 0, 1
        else:
            src, dst = self.get_action_panes(PANE_RIGHT)
        self.replace_chunk(src, dst, self.get_action_chunk(src, dst))

    def action_pull_change_left(self, *args):
        src, dst = self.get_action_panes(PANE_LEFT, reverse=True)
        self.replace_chunk(src, dst, self.get_action_chunk(src, dst))

    def action_pull_change_right(self, *args):
        src, dst = self.get_action_panes(PANE_RIGHT, reverse=True)
        self.replace_chunk(src, dst, self.get_action_chunk(src, dst))

    def action_copy_change_left_up(self, *args):
        src, dst = self.get_action_panes(PANE_LEFT)
        self.copy_chunk(
            src, dst, self.get_action_chunk(src, dst), copy_up=True)

    def action_copy_change_right_up(self, *args):
        src, dst = self.get_action_panes(PANE_RIGHT)
        self.copy_chunk(
            src, dst, self.get_action_chunk(src, dst), copy_up=True)

    def action_copy_change_left_down(self, *args):
        src, dst = self.get_action_panes(PANE_LEFT)
        self.copy_chunk(
            src, dst, self.get_action_chunk(src, dst), copy_up=False)

    def action_copy_change_right_down(self, *args):
        src, dst = self.get_action_panes(PANE_RIGHT)
        self.copy_chunk(
            src, dst, self.get_action_chunk(src, dst), copy_up=False)

    def pull_all_non_conflicting_changes(self, src, dst):
        merger = Merger()
        merger.differ = self.linediffer
        merger.texts = self.buffer_texts
        for mergedfile in merger.merge_2_files(src, dst):
            pass
        self._sync_vscroll_lock = True
        self.textbuffer[dst].begin_user_action()
        self.textbuffer[dst].set_text(mergedfile)
        self.textbuffer[dst].end_user_action()

        def resync():
            self._sync_vscroll_lock = False
            self._sync_vscroll(self.scrolledwindow[src].get_vadjustment(), src)
        self.scheduler.add_task(resync)

    def action_pull_all_changes_left(self, *args):
        src, dst = self.get_action_panes(PANE_LEFT, reverse=True)
        self.pull_all_non_conflicting_changes(src, dst)

    def action_pull_all_changes_right(self, *args):
        src, dst = self.get_action_panes(PANE_RIGHT, reverse=True)
        self.pull_all_non_conflicting_changes(src, dst)

    def action_merge_all_changes(self, *args):
        dst = 1
        merger = Merger()
        merger.differ = self.linediffer
        merger.texts = self.buffer_texts
        for mergedfile in merger.merge_3_files(False):
            pass
        self._sync_vscroll_lock = True
        self.textbuffer[dst].begin_user_action()
        self.textbuffer[dst].set_text(mergedfile)
        self.textbuffer[dst].end_user_action()

        def resync():
            self._sync_vscroll_lock = False
            self._sync_vscroll(self.scrolledwindow[0].get_vadjustment(), 0)
        self.scheduler.add_task(resync)

    @with_focused_pane
    def action_delete_change(self, pane, *args):
        if self.cursor.chunk is None:
            return

        chunk = self.linediffer.get_chunk(self.cursor.chunk, pane)
        if chunk is None:
            return

        self.delete_chunk(pane, chunk)

    def _synth_chunk(self, pane0, pane1, line):
        """Returns the Same chunk that would exist at
           the given location if we didn't remove Same chunks"""

        # This method is a hack around our existing diffutil data structures;
        # getting rid of the Same chunk removal is difficult, as several places
        # have baked in the assumption of only being given changed blocks.

        buf0, buf1 = self.textbuffer[pane0], self.textbuffer[pane1]
        start0, end0 = 0, buf0.get_line_count() - 1
        start1, end1 = 0, buf1.get_line_count() - 1

        # This hack is required when pane0's prev/next chunk doesn't exist
        # (i.e., is Same) between pane0 and pane1.
        prev_chunk0, prev_chunk1, next_chunk0, next_chunk1 = (None,) * 4
        _, prev, next_ = self.linediffer.locate_chunk(pane0, line)
        if prev is not None:
            while prev >= 0:
                prev_chunk0 = self.linediffer.get_chunk(prev, pane0, pane1)
                prev_chunk1 = self.linediffer.get_chunk(prev, pane1, pane0)
                if None not in (prev_chunk0, prev_chunk1):
                    start0 = prev_chunk0[2]
                    start1 = prev_chunk1[2]
                    break
                prev -= 1

        if next_ is not None:
            while next_ < self.linediffer.diff_count():
                next_chunk0 = self.linediffer.get_chunk(next_, pane0, pane1)
                next_chunk1 = self.linediffer.get_chunk(next_, pane1, pane0)
                if None not in (next_chunk0, next_chunk1):
                    end0 = next_chunk0[1]
                    end1 = next_chunk1[1]
                    break
                next_ += 1

        # TODO: Move myers.DiffChunk to a more general place, update
        # this to use it, and update callers to use nice attributes.
        return "Same", start0, end0, start1, end1

    def _corresponding_chunk_line(self, chunk, line, pane, new_pane):
        """Approximates the corresponding line between panes"""

        new_buf = self.textbuffer[new_pane]

        # Special-case cross-pane jumps
        if (pane == 0 and new_pane == 2) or (pane == 2 and new_pane == 0):
            proxy = self._corresponding_chunk_line(chunk, line, pane, 1)
            return self._corresponding_chunk_line(chunk, proxy, 1, new_pane)

        # Either we are currently in a identifiable chunk, or we are in a Same
        # chunk; if we establish the start/end of that chunk in both panes, we
        # can figure out what our new offset should be.
        cur_chunk = None
        if chunk is not None:
            cur_chunk = self.linediffer.get_chunk(chunk, pane, new_pane)

        if cur_chunk is None:
            cur_chunk = self._synth_chunk(pane, new_pane, line)
        cur_start, cur_end, new_start, new_end = cur_chunk[1:5]

        # If the new buffer's current cursor is already in the correct chunk,
        # assume that we have in-progress editing, and don't move it.
        cursor_it = new_buf.get_iter_at_mark(new_buf.get_insert())
        cursor_line = cursor_it.get_line()

        cursor_chunk, _, _ = self.linediffer.locate_chunk(
            new_pane, cursor_line)
        if cursor_chunk is not None:
            already_in_chunk = cursor_chunk == chunk
        else:
            cursor_chunk = self._synth_chunk(pane, new_pane, cursor_line)
            already_in_chunk = (
                cursor_chunk[3] == new_start and cursor_chunk[4] == new_end)

        if already_in_chunk:
            new_line = cursor_line
        else:
            # Guess where to put the cursor: in the same chunk, at about the
            # same place within the chunk, calculated proportionally by line.
            # Insert chunks and one-line chunks are placed at the top.
            if cur_end == cur_start:
                chunk_offset = 0.0
            else:
                chunk_offset = (line - cur_start) / float(cur_end - cur_start)
            new_line = new_start + int(chunk_offset * (new_end - new_start))

        return new_line

    def move_cursor(self, pane, line, focus=True):
        buf, view = self.textbuffer[pane], self.textview[pane]
        if focus:
            view.grab_focus()
        buf.place_cursor(buf.get_iter_at_line(line))
        view.scroll_to_mark(buf.get_insert(), 0.1, True, 0.5, 0.5)

    def move_cursor_pane(self, pane, new_pane):
        chunk, line = self.cursor.chunk, self.cursor.line
        new_line = self._corresponding_chunk_line(chunk, line, pane, new_pane)
        self.move_cursor(new_pane, new_line)

    def action_prev_pane(self, *args):
        pane = self._get_focused_pane()
        new_pane = (pane - 1) % self.num_panes
        self.move_cursor_pane(pane, new_pane)

    def action_next_pane(self, *args):
        pane = self._get_focused_pane()
        new_pane = (pane + 1) % self.num_panes
        self.move_cursor_pane(pane, new_pane)

    def _set_external_action_sensitivity(self):
        # FIXME: This sensitivity is very confused. Essentially, it's always
        # enabled because we don't unset focus_pane, but the action uses the
        # current pane focus (i.e., _get_focused_pane) instead of focus_pane.
        have_file = self.focus_pane is not None
        self.set_action_enabled("open-external", have_file)

    def on_textview_drag_data_received(
            self, widget, context, x, y, selection_data, info, time):
        uris = selection_data.get_uris()
        if uris:
            gfiles = [Gio.File.new_for_uri(uri) for uri in uris]

            if len(gfiles) == self.num_panes:
                if self.check_unsaved_changes():
                    self.set_files(gfiles)
            elif len(gfiles) == 1:
                if widget in self.textview:
                    pane = self.textview.index(widget)
                elif widget in self.filelabel:
                    pane = self.filelabel.index(widget)
                else:
                    log.error("Unrecognised drag destination")
                    return True
                buffer = self.textbuffer[pane]
                if self.check_unsaved_changes([buffer]):
                    self.set_file(pane, gfiles[0])
            return True

    @Gtk.Template.Callback()
    def on_textview_focus_in_event(self, view, event):
        self.focus_pane = view
        self.findbar.set_text_view(self.focus_pane)
        self.on_cursor_position_changed(view.get_buffer(), None, True)
        self._set_save_action_sensitivity()
        self._set_merge_action_sensitivity()
        self._set_external_action_sensitivity()

    @Gtk.Template.Callback()
    def on_textview_focus_out_event(self, view, event):
        self.keymask = 0
        self._set_merge_action_sensitivity()
        self._set_external_action_sensitivity()

    def _after_text_modified(self, buf, startline, sizechange):
        if self.num_panes > 1:
            pane = self.textbuffer.index(buf)
            if not self.linediffer.syncpoints:
                self.linediffer.change_sequence(pane, startline, sizechange,
                                                self.buffer_filtered)
            # TODO: We should have a diff-changed signal for the
            # current buffer instead of passing everything through
            # cursor change logic.
            focused_pane = self._get_focused_pane()
            if focused_pane != -1:
                self.on_cursor_position_changed(self.textbuffer[focused_pane],
                                                None, True)

    def _filter_text(self, txt, buf, txt_start_iter, txt_end_iter):
        dimmed_tag = buf.get_tag_table().lookup("dimmed")
        buf.remove_tag(dimmed_tag, txt_start_iter, txt_end_iter)

        def highlighter(start, end):
            start_iter = txt_start_iter.copy()
            start_iter.forward_chars(start)
            end_iter = txt_start_iter.copy()
            end_iter.forward_chars(end)
            buf.apply_tag(dimmed_tag, start_iter, end_iter)

        try:
            regexes = [f.filter for f in self.text_filters if f.active]
            txt = misc.apply_text_filters(txt, regexes, apply_fn=highlighter)
        except AssertionError:
            if not self.warned_bad_comparison:
                misc.error_dialog(
                    primary=_("Comparison results will be inaccurate"),
                    secondary=_(
                        "A filter changed the number of lines in the "
                        "file, which is unsupported. The comparison will "
                        "not be accurate."),
                )
                self.warned_bad_comparison = True

        return txt

    def after_text_insert_text(self, buf, it, newtext, textlen):
        start_mark = buf.get_mark("insertion-start")
        starting_at = buf.get_iter_at_mark(start_mark).get_line()
        buf.delete_mark(start_mark)
        lines_added = it.get_line() - starting_at
        self._after_text_modified(buf, starting_at, lines_added)

    def after_text_delete_range(self, buf, it0, it1):
        starting_at = it0.get_line()
        self._after_text_modified(buf, starting_at, -self.lines_removed)
        self.lines_removed = 0

    def check_save_modified(self, buffers=None):
        response = Gtk.ResponseType.OK
        buffers = buffers or self.textbuffer[:self.num_panes]
        if any(b.get_modified() for b in buffers):
            builder = Gtk.Builder.new_from_resource(
                '/org/gnome/meld/ui/save-confirm-dialog.ui')
            dialog = builder.get_object('save-confirm-dialog')
            dialog.set_transient_for(self.get_toplevel())
            message_area = dialog.get_message_area()

            buttons = []
            for buf in buffers:
                button = Gtk.CheckButton.new_with_label(buf.data.label)
                needs_save = buf.get_modified()
                button.set_sensitive(needs_save)
                button.set_active(needs_save)
                message_area.pack_start(
                    button, expand=False, fill=True, padding=0)
                buttons.append(button)
            message_area.show_all()

            response = dialog.run()
            try_save = [b.get_active() for b in buttons]
            dialog.destroy()

            if response == Gtk.ResponseType.OK:
                for i, buf in enumerate(buffers):
                    if try_save[i]:
                        self.save_file(self.textbuffer.index(buf))

                # We return an APPLY instead of OK here to indicate that other
                # closing logic shouldn't run. Instead, the file-saved callback
                # from save_file() handles closing files and setting state.
                return Gtk.ResponseType.APPLY
            elif response == Gtk.ResponseType.DELETE_EVENT:
                response = Gtk.ResponseType.CANCEL
            elif response == Gtk.ResponseType.CLOSE:
                response = Gtk.ResponseType.OK

        if response == Gtk.ResponseType.OK and self.meta:
            self.prompt_resolve_conflict()
        elif response == Gtk.ResponseType.CANCEL:
            self.state = ComparisonState.Normal

        return response

    def prompt_resolve_conflict(self):
        parent = self.meta.get('parent', None)
        saved = self.meta.get('middle_saved', False)
        prompt_resolve = self.meta.get('prompt_resolve', False)
        if prompt_resolve and saved and parent.has_command('resolve'):
            primary = _("Mark conflict as resolved?")
            secondary = _(
                "If the conflict was resolved successfully, you may mark "
                "it as resolved now.")
            buttons = (
                (_("Cancel"), Gtk.ResponseType.CANCEL, None),
                (_("Mark _Resolved"), Gtk.ResponseType.OK, None),
            )
            resolve_response = misc.modal_dialog(
                primary, secondary, buttons, parent=self,
                messagetype=Gtk.MessageType.QUESTION)

            if resolve_response == Gtk.ResponseType.OK:
                bufdata = self.textbuffer[1].data
                conflict_gfile = bufdata.savefile or bufdata.gfile
                # It's possible that here we're in a quit callback,
                # so we can't schedule the resolve action to an
                # idle loop; it might never happen.
                parent.command(
                    'resolve', [conflict_gfile.get_path()], sync=True)

    def on_delete_event(self):
        self.state = ComparisonState.Closing
        response = self.check_save_modified()
        if response == Gtk.ResponseType.OK:
            meld_settings = get_meld_settings()
            for h in self.settings_handlers:
                meld_settings.disconnect(h)

            # This is a workaround for cleaning up file monitors.
            for buf in self.textbuffer:
                buf.data.disconnect_monitor()

            try:
                self._cached_match.stop()
                self._cached_match = None
            except Exception:
                # Ignore any cross-process exceptions that happen when
                # shutting down our matcher process.
                log.exception('Failed to shut down matcher process')
            # TODO: Base the return code on something meaningful for VC tools
            self.close_signal.emit(0)
        elif response == Gtk.ResponseType.CANCEL:
            self.state = ComparisonState.Normal
        elif response == Gtk.ResponseType.APPLY:
            # We have triggered an async save, and need to let it finish
            ...

        return response

    def _scroll_to_actions(self, actions):
        """Scroll all views affected by *actions* to the current cursor"""

        affected_buffers = set(a.buffer for a in actions)
        for buf in affected_buffers:
            buf_index = self.textbuffer.index(buf)
            view = self.textview[buf_index]
            view.scroll_mark_onscreen(buf.get_insert())

    def action_undo(self, *args):
        if self.undosequence.can_undo():
            actions = self.undosequence.undo()
            self._scroll_to_actions(actions)

    def action_redo(self, *args):
        if self.undosequence.can_redo():
            actions = self.undosequence.redo()
            self._scroll_to_actions(actions)

    def on_text_insert_text(self, buf, it, text, textlen):
        self.undosequence.add_action(
            BufferInsertionAction(buf, it.get_offset(), text))
        buf.create_mark("insertion-start", it, True)

    def on_text_delete_range(self, buf, it0, it1):
        text = buf.get_text(it0, it1, False)
        self.lines_removed = it1.get_line() - it0.get_line()
        self.undosequence.add_action(
            BufferDeletionAction(buf, it0.get_offset(), text))

    def on_undo_checkpointed(self, undosequence, buf, checkpointed):
        buf.set_modified(not checkpointed)
        self.recompute_label()

    def on_can_undo(self, undosequence, can_undo):
        self.set_action_enabled('undo', can_undo)

    def on_can_redo(self, undosequence, can_redo):
        self.set_action_enabled('redo', can_redo)

    @with_focused_pane
    def action_copy_full_path(self, pane, *args):
        gfile = self.textbuffer[pane].data.gfile
        if not gfile:
            return

        path = gfile.get_path() or gfile.get_uri()
        clip = Gtk.Clipboard.get_default(Gdk.Display.get_default())
        clip.set_text(path, -1)
        clip.store()

    @with_focused_pane
    def action_open_folder(self, pane, *args):
        gfile = self.textbuffer[pane].data.gfile
        if not gfile:
            return

        parent = gfile.get_parent()
        if parent:
            open_files_external(gfiles=[parent])

    @with_focused_pane
    def action_open_external(self, pane, *args):
        if not self.textbuffer[pane].data.gfile:
            return
        pos = self.textbuffer[pane].props.cursor_position
        cursor_it = self.textbuffer[pane].get_iter_at_offset(pos)
        line = cursor_it.get_line() + 1
        gfiles = [self.textbuffer[pane].data.gfile]
        open_files_external(gfiles=gfiles, line=line)

    def update_text_actions_sensitivity(self, *args):
        widget = self.focus_pane
        if not widget:
            cut, copy, paste = False, False, False
        else:
            cut = copy = widget.get_buffer().get_has_selection()
            paste = widget.get_editable()

        for action, enabled in zip(
                ('cut', 'copy', 'paste'), (cut, copy, paste)):
            self.set_action_enabled(action, enabled)

    @with_focused_pane
    def get_selected_text(self, pane):
        """Returns selected text of active pane"""
        buf = self.textbuffer[pane]
        sel = buf.get_selection_bounds()
        if sel:
            return buf.get_text(sel[0], sel[1], False)

    def action_find(self, *args):
        selected_text = self.get_selected_text()
        self.findbar.start_find(
            textview=self.focus_pane, replace=False, text=selected_text)

    def action_find_replace(self, *args):
        selected_text = self.get_selected_text()
        self.findbar.start_find(
            textview=self.focus_pane, replace=True, text=selected_text)

    def action_find_next(self, *args):
        self.findbar.start_find_next(self.focus_pane)

    def action_find_previous(self, *args):
        self.findbar.start_find_previous(self.focus_pane)

    @with_focused_pane
    def action_go_to_line(self, pane, *args):
        self.statusbar[pane].emit('start-go-to-line')

    @Gtk.Template.Callback()
    def on_scrolledwindow_size_allocate(self, scrolledwindow, allocation):
        index = self.scrolledwindow.index(scrolledwindow)
        if index == 0 or index == 1:
            self.linkmap[0].queue_draw()
        if index == 1 or index == 2:
            self.linkmap[1].queue_draw()

    @Gtk.Template.Callback()
    def on_textview_popup_menu(self, textview):
        buffer = textview.get_buffer()
        cursor_it = buffer.get_iter_at_mark(buffer.get_insert())
        location = textview.get_iter_location(cursor_it)

        rect = Gdk.Rectangle()
        rect.x, rect.y = textview.buffer_to_window_coords(
            Gtk.TextWindowType.WIDGET, location.x, location.y)

        pane = self.textview.index(textview)
        self.set_syncpoint_menuitem(pane)

        self.popup_menu.popup_at_rect(
            Gtk.Widget.get_window(textview),
            rect,
            Gdk.Gravity.SOUTH_EAST,
            Gdk.Gravity.NORTH_WEST,
            None,
        )
        return True

    @Gtk.Template.Callback()
    def on_textview_button_press_event(self, textview, event):
        if event.button == 3:
            textview.grab_focus()
            pane = self.textview.index(textview)
            self.set_syncpoint_menuitem(pane)
            self.popup_menu.popup_at_pointer(event)
            return True
        return False

    def set_syncpoint_menuitem(self, pane):
        menu_actions = {
            SyncpointAction.ADD: [
                _("Add Synchronization Point"),
                "view.add-sync-point"
            ],
            SyncpointAction.DELETE: [
                _("Remove Synchronization Point"),
                "view.remove-sync-point"
            ],
            SyncpointAction.MOVE: [
                _("Move Synchronization Point"),
                "view.add-sync-point"
            ],
            SyncpointAction.MATCH: [
                _("Match Synchronization Point"),
                "view.add-sync-point"
            ],
            SyncpointAction.DISABLED: [
                _("Add Synchronization Point"),
                "view.add-sync-point"
            ],
        }

        def get_mark():
            return self.textbuffer[pane].get_insert()

        action = self.syncpoints.action(pane, get_mark)

        self.set_action_enabled(
            "add-sync-point",
            action != SyncpointAction.DISABLED
        )

        label, action_id = menu_actions[action]

        syncpoint_menu = Gio.Menu()
        syncpoint_menu.append(label=label, detailed_action=action_id)
        syncpoint_menu.append(
            label=_("Clear Synchronization Points"),
            detailed_action='view.clear-sync-point',
        )
        section = Gio.MenuItem.new_section(None, syncpoint_menu)
        section.set_attribute([("id", "s", "syncpoint-section")])
        replace_menu_section(self.popup_menu_model, section)

        self.popup_menu = Gtk.Menu.new_from_model(self.popup_menu_model)
        self.popup_menu.attach_to_widget(self)

    def set_labels(self, labels):
        labels = labels[:self.num_panes]
        for label, buf, flabel in zip(labels, self.textbuffer, self.filelabel):
            if label:
                buf.data.label = label
                flabel.props.custom_label = label

    def set_merge_output_file(self, gfile):
        if self.num_panes < 2:
            return
        buf = self.textbuffer[1]
        buf.data.savefile = gfile
        buf.data.label = gfile.get_path()
        self.update_buffer_writable(buf)
        self.filelabel[1].props.gfile = gfile
        self.recompute_label()

    def _set_save_action_sensitivity(self):
        pane = self._get_focused_pane()
        modified_panes = [b.get_modified() for b in self.textbuffer]
        self.set_action_enabled('save', pane != -1 and modified_panes[pane])
        self.set_action_enabled('save-all', any(modified_panes))

    def recompute_label(self):
        self._set_save_action_sensitivity()
        buffers = self.textbuffer[:self.num_panes]
        filenames = [b.data.label for b in buffers]
        shortnames = misc.shorten_names(*filenames)

        for i, buf in enumerate(buffers):
            if buf.get_modified():
                shortnames[i] += "*"
            self.file_save_button[i].set_sensitive(buf.get_modified())
            self.file_save_button[i].get_child().props.icon_name = (
                'document-save-symbolic' if buf.data.writable else
                'document-save-as-symbolic')

        parent_path = find_shared_parent_path(
            [b.data.gfiletarget for b in buffers]
        )
        for pathlabel in self.filelabel:
            pathlabel.props.parent_gfile = parent_path

        label = self.meta.get("tablabel", "")
        if label:
            self.label_text = label
            tooltip_names = [label]
        else:
            self.label_text = " — ".join(shortnames)
            tooltip_names = filenames
        self.tooltip_text = "\n".join((_("File comparison:"), *tooltip_names))
        self.label_changed.emit(self.label_text, self.tooltip_text)

    def pre_comparison_init(self):
        self._disconnect_buffer_handlers()
        self.linediffer.clear()
        for bufferlines in self.buffer_filtered:
            bufferlines.clear_cache()

        for buf in self.textbuffer:
            tag = buf.get_tag_table().lookup("inline")
            buf.remove_tag(tag, buf.get_start_iter(), buf.get_end_iter())

        for mgr in self.msgarea_mgr:
            if mgr.get_msg_id() in self.TRANSIENT_MESSAGES:
                mgr.clear()

    def set_files(self, gfiles, encodings=None):
        """Load the given files

        If an element is None, the text of a pane is left as is.
        """
        if len(gfiles) != self.num_panes:
            return

        self.pre_comparison_init()
        self.undosequence.clear()

        encodings = encodings or ((None,) * len(gfiles))

        files = []
        for pane, (gfile, encoding) in enumerate(zip(gfiles, encodings)):
            if gfile:
                files.append((pane, gfile, encoding))
            else:
                self.textbuffer[pane].data.state = MeldBufferState.LOAD_FINISHED

        if not files:
            self.scheduler.add_task(self._compare_files_internal())

        for pane, gfile, encoding in files:
            self.load_file_in_pane(pane, gfile, encoding)

    def set_file(
            self,
            pane: int,
            gfile: Gio.File,
            encoding: GtkSource.Encoding = None):
        self.pre_comparison_init()
        self.undosequence.clear()
        self.load_file_in_pane(pane, gfile, encoding)

    def load_file_in_pane(
            self,
            pane: int,
            gfile: Gio.File,
            encoding: GtkSource.Encoding = None):
        """Load a file into the given pane

        Don't call this directly; use `set_file()` or `set_files()`,
        which handle sensitivity and signal connection. Even if you
        don't care about those things, you need it because they'll be
        unconditionally added after file load, which will cause
        duplicate handlers, etc. if you don't do this thing.
        """

        self.msgarea_mgr[pane].clear()

        buf = self.textbuffer[pane]
        buf.data.reset(gfile, MeldBufferState.LOADING)
        self.file_open_button[pane].props.file = gfile

        self.filelabel[pane].props.parent_gfile = None
        # FIXME: this was self.textbuffer[pane].data.label, which could be
        # either a custom label or the fallback
        self.filelabel[pane].props.gfile = gfile

        if buf.data.is_special:
            loader = GtkSource.FileLoader.new_from_stream(
                buf, buf.data.sourcefile, buf.data.gfile.read())
        else:
            loader = GtkSource.FileLoader.new(buf, buf.data.sourcefile)

        custom_candidates = get_custom_encoding_candidates()
        if encoding:
            custom_candidates = [encoding]
        if custom_candidates:
            loader.set_candidate_encodings(custom_candidates)

        buf.move_mark_by_name(LOAD_PROGRESS_MARK, buf.get_start_iter())
        cancellable = Gio.Cancellable()
        errors = {}
        loader.load_async(
            GLib.PRIORITY_HIGH,
            cancellable=cancellable,
            progress_callback=self.file_load_progress,
            progress_callback_data=(loader, cancellable, errors),
            callback=self.file_loaded,
            user_data=(pane, errors),
        )

    def get_comparison(self):
        uris = [b.data.gfile for b in self.textbuffer[:self.num_panes]]

        if self.comparison_mode == FileComparisonMode.AutoMerge:
            comparison_type = RecentType.Merge
        else:
            comparison_type = RecentType.File

        return comparison_type, uris

    def file_load_progress(
        self,
        current_bytes: int,
        total_bytes: int,
        loader: GtkSource.FileLoader,
        cancellable: Gio.Cancellable,
        errors: dict[int, str],
    ) -> None:
        failed_it = None
        buffer = loader.get_buffer()
        progress_mark = buffer.get_mark(LOAD_PROGRESS_MARK)

        # If forward_line() returns False it points to the current end of the
        # buffer after the movement; if this happens, we assume that we don't
        # yet have a full line, and so don't can't check it for length.
        it = buffer.get_iter_at_mark(progress_mark)
        last_it = it.copy()
        while it.forward_line():
            # last_it is now on a fully-loaded line, so we can check it
            if last_it.get_chars_in_line() > LINE_LENGTH_LIMIT:
                failed_it = last_it
                break
            last_it.assign(it)

        # We also have to check the last line in the file, which would
        # otherwise be skipped by the above logic.
        if (current_bytes == total_bytes) and (it.get_chars_in_line() > LINE_LENGTH_LIMIT):
            failed_it = it

        if failed_it:
            # Ideally we'd have custom GError handling here instead, but
            # set_error_if_cancelled() doesn't appear to work in pygobject
            # bindings.
            errors[self.textbuffer.index(buffer)] = (
                FileLoadError.LINE_TOO_LONG,
                _(
                    "Line {line_number} exceeded maximum line length "
                    "({line_length} > {LINE_LENGTH_LIMIT})"
                ).format(
                    line_number=failed_it.get_line() + 1,
                    line_length=failed_it.get_chars_in_line(),
                    LINE_LENGTH_LIMIT=LINE_LENGTH_LIMIT,
                )
            )
            cancellable.cancel()

        # Moving the mark invalidates the text iterators, so this must happen
        # *last* here, or the above line length accesses will be incorrect.
        buffer.move_mark(progress_mark, last_it)

    def file_loaded(
        self,
        loader: GtkSource.FileLoader,
        result: Gio.AsyncResult,
        user_data: Tuple[int, dict[int, str]],
    ):
        gfile = loader.get_location()
        buf = loader.get_buffer()
        pane, errors = user_data

        try:
            loader.load_finish(result)
            buf.data.state = MeldBufferState.LOAD_FINISHED
        except GLib.Error as err:
            if err.matches(
                    GLib.convert_error_quark(),
                    GLib.ConvertError.ILLEGAL_SEQUENCE):
                # While there are probably others, this is the main
                # case where GtkSourceView's loader doesn't finish its
                # in-progress user-action on error. See bgo#795387 for
                # the GtkSourceView bug report.
                #
                # The handling here is fragile, but it's better than
                # getting into a non-obvious corrupt state.
                buf.end_not_undoable_action()
                buf.end_user_action()

            if err.domain == GLib.quark_to_string(
                    GtkSource.FileLoaderError.quark()):
                # TODO: Add custom reload-with-encoding handling for
                # GtkSource.FileLoaderError.CONVERSION_FALLBACK and
                # GtkSource.FileLoaderError.ENCODING_AUTO_DETECTION_FAILED
                pass

            filename = GLib.markup_escape_text(
                gfile.get_parse_name())
            primary = _("There was a problem opening the file “%s”." % filename)
            # If we have custom errors defined, use those instead
            if errors.get(pane):
                error, error_text = errors[pane]
            else:
                error_text = err.message
            self.msgarea_mgr[pane].add_dismissable_msg(
                "dialog-error-symbolic", primary, error_text
            )
            buf.data.state = MeldBufferState.LOAD_ERROR

        start, end = buf.get_bounds()
        buffer_text = buf.get_text(start, end, False)

        # Don't risk overwriting a more-important "we didn't load the file
        # correctly" message with this semi-helpful "is it binary?" prompt
        if (
            not loader.get_encoding()
            and "\\00" in buffer_text
            and not self.msgarea_mgr[pane].has_message()
        ):
            filename = GLib.markup_escape_text(gfile.get_parse_name())
            primary = _("File %s appears to be a binary file.") % filename
            secondary = _(
                "Do you want to open the file using the default application?")
            self.msgarea_mgr[pane].add_action_msg(
                'dialog-warning-symbolic', primary, secondary, _("Open"),
                functools.partial(open_files_external, gfiles=[gfile]))

        # We checkpoint first, which will set modified state via the
        # checkpointed callback. We then check whether we're saving the
        # file to a different location than it was loaded from, in
        # which case we assume that this needs to be saved to persist
        # what the user is seeing. Finally, we update the writability,
        # which does label calculation.
        self.undosequence.checkpoint(buf)
        if buf.data.savefile:
            buf.set_modified(True)
        self.update_buffer_writable(buf)

        buf.data.update_mtime()

        buffer_states = [b.data.state for b in self.textbuffer[:self.num_panes]]
        if all(state == MeldBufferState.LOAD_FINISHED for state in buffer_states):
            self.scheduler.add_task(self._compare_files_internal())

        self.recompute_label()

    def _merge_files(self):
        if self.comparison_mode == FileComparisonMode.AutoMerge:
            yield _("[%s] Merging files") % self.label_text
            merger = Merger()
            step = merger.initialize(self.buffer_filtered, self.buffer_texts)
            while next(step) is None:
                yield 1
            for merged_text in merger.merge_3_files():
                yield 1
            self.linediffer.unresolved = merger.unresolved
            self.textbuffer[1].set_text(merged_text)
            self.recompute_label()
        else:
            yield 1

    def _diff_files(self, refresh=False):
        yield _("[%s] Computing differences") % self.label_text
        texts = self.buffer_filtered[:self.num_panes]
        self.linediffer.ignore_blanks = self.props.ignore_blank_lines
        step = self.linediffer.set_sequences_iter(texts)
        while next(step) is None:
            yield 1

        if not refresh:
            for buf in self.textbuffer:
                buf.place_cursor(buf.get_start_iter())

            chunk, prev, next_ = self.linediffer.locate_chunk(1, 0)
            target_chunk = chunk if chunk is not None else next_
            if target_chunk is not None:
                self.scheduler.add_task(
                    lambda: self.go_to_chunk(target_chunk, centered=True),
                    True)

        self.queue_draw()
        self._connect_buffer_handlers()
        self._set_merge_action_sensitivity()

        # Changing textview sensitivity removes focus and so triggers
        # our focus-out sensitivity handling. We manually trigger the
        # focus-in here to restablish the previous state.
        if self.cursor.pane is not None:
            self.on_textview_focus_in_event(
                self.textview[self.cursor.pane], None
            )

        langs = [LanguageManager.get_language_from_file(buf.data.gfile)
                 for buf in self.textbuffer[:self.num_panes]]

        # If we have only one identified language then we assume that all of
        # the files are actually of that type.
        real_langs = [lang for lang in langs if lang]
        if real_langs and real_langs.count(real_langs[0]) == len(real_langs):
            langs = (real_langs[0],) * len(langs)

        for i in range(self.num_panes):
            self.textbuffer[i].set_language(langs[i])

    def _compare_files_internal(self):
        for i in self._merge_files():
            yield i
        for i in self._diff_files():
            yield i
        focus_pane = 0 if self.num_panes < 2 else 1
        self.textview[focus_pane].grab_focus()

    def set_meta(self, meta):
        self.meta = meta
        labels = meta.get('labels', ())
        if labels:
            for i, label in enumerate(labels):
                self.filelabel[i].props.custom_label = label

    def notify_file_changed(self, data):
        try:
            pane = [b.data for b in self.textbuffer].index(data)
        except ValueError:
            # Notification for unknown buffer
            return
        display_name = data.gfile.get_parse_name()
        primary = _("File %s has changed on disk") % display_name
        secondary = _("Do you want to reload the file?")
        self.msgarea_mgr[pane].add_action_msg(
            'dialog-warning-symbolic', primary, secondary, _("_Reload"),
            self.action_revert)

    def refresh_comparison(self, *args):
        """Refresh the view by clearing and redoing all comparisons"""
        self.pre_comparison_init()
        self.queue_draw()
        self.scheduler.add_task(self._diff_files(refresh=True))

    def _set_merge_action_sensitivity(self):
        if self.focus_pane:
            editable = self.focus_pane.get_editable()
            pane_idx = self.textview.index(self.focus_pane)
            mergeable = self.linediffer.has_mergeable_changes(pane_idx)
        else:
            editable = False
            mergeable = (False, False)

        self.set_action_enabled('merge-all-left', mergeable[0] and editable)
        self.set_action_enabled('merge-all-right', mergeable[1] and editable)

        if self.num_panes == 3 and self.textview[1].get_editable():
            mergeable = self.linediffer.has_mergeable_changes(1)
        else:
            mergeable = (False, False)

        self.set_action_enabled('merge-all', mergeable[0] or mergeable[1])

    def on_diffs_changed(self, linediffer, chunk_changes):

        for pane in range(self.num_panes):
            pane_changes = list(self.linediffer.single_changes(pane))
            self.chunkmap[pane].chunks = pane_changes

        # TODO: Break out highlight recalculation to its own method,
        # and just update chunk lists in children here.
        for gutter in self.actiongutter:
            from_pane = self.textview.index(gutter.source_view)
            to_pane = self.textview.index(gutter.target_view)
            gutter.chunks = list(linediffer.paired_all_single_changes(
                from_pane, to_pane))

        removed_chunks, added_chunks, modified_chunks = chunk_changes

        # We need to clear removed and modified chunks, and need to
        # re-highlight added and modified chunks.
        need_clearing = sorted(
            list(removed_chunks), key=merged_chunk_order)
        need_highlighting = sorted(
            list(added_chunks) + [modified_chunks], key=merged_chunk_order)

        alltags = [b.get_tag_table().lookup("inline") for b in self.textbuffer]

        for chunks in need_clearing:
            for i, chunk in enumerate(chunks):
                if not chunk or chunk.tag != "replace":
                    continue
                to_idx = 2 if i == 1 else 0
                bufs = self.textbuffer[1], self.textbuffer[to_idx]
                tags = alltags[1], alltags[to_idx]

                bufs[0].remove_tag(tags[0], *chunk.to_iters(buffer_a=bufs[0]))
                bufs[1].remove_tag(tags[1], *chunk.to_iters(buffer_b=bufs[1]))

        for chunks in need_highlighting:
            clear = chunks == modified_chunks
            for merge_cache_index, chunk in enumerate(chunks):
                if not chunk or chunk[0] != "replace":
                    continue
                to_pane = 2 if merge_cache_index == 1 else 0
                bufs = self.textbuffer[1], self.textbuffer[to_pane]
                tags = alltags[1], alltags[to_pane]

                buf_from_iters = chunk.to_iters(buffer_a=bufs[0])
                buf_to_iters = chunk.to_iters(buffer_b=bufs[1])

                # We don't use self.buffer_texts here, as removing line
                # breaks messes with inline highlighting in CRLF cases
                text1 = bufs[0].get_text(*buf_from_iters, False)
                textn = bufs[1].get_text(*buf_to_iters, False)

                # Bail on long sequences, rather than try a slow comparison
                inline_limit = 20000
                if len(text1) + len(textn) > inline_limit and \
                        not self.force_highlight:

                    bufs[0].apply_tag(tags[0], *buf_from_iters)
                    bufs[1].apply_tag(tags[1], *buf_to_iters)
                    self._prompt_long_highlighting()
                    continue

                def apply_highlight(
                        bufs, tags, start_marks, end_marks, texts, to_pane,
                        chunk, matches):
                    starts = [bufs[0].get_iter_at_mark(start_marks[0]),
                              bufs[1].get_iter_at_mark(start_marks[1])]
                    ends = [bufs[0].get_iter_at_mark(end_marks[0]),
                            bufs[1].get_iter_at_mark(end_marks[1])]

                    bufs[0].delete_mark(start_marks[0])
                    bufs[0].delete_mark(end_marks[0])
                    bufs[1].delete_mark(start_marks[1])
                    bufs[1].delete_mark(end_marks[1])

                    if not self.linediffer.has_chunk(to_pane, chunk):
                        return

                    text1 = bufs[0].get_text(starts[0], ends[0], False)
                    textn = bufs[1].get_text(starts[1], ends[1], False)

                    if texts != (text1, textn):
                        return

                    if clear:
                        bufs[0].remove_tag(tags[0], starts[0], ends[0])
                        bufs[1].remove_tag(tags[1], starts[1], ends[1])

                    offsets = [ends[0].get_offset() - starts[0].get_offset(),
                               ends[1].get_offset() - starts[1].get_offset()]

                    def process_matches(match):
                        if match.tag != "equal":
                            return True
                        # Always keep matches occurring at the start or end
                        is_start = match.start_a == 0 and match.start_b == 0
                        is_end = (
                            match.end_a == offsets[0] and
                            match.end_b == offsets[1])
                        if is_start or is_end:
                            return False
                        # Remove equal matches of size less than 3
                        too_short = ((match.end_a - match.start_a < 3) or
                                     (match.end_b - match.start_b < 3))
                        return too_short

                    matches = [m for m in matches if process_matches(m)]

                    for i in range(2):
                        start, end = starts[i].copy(), starts[i].copy()
                        offset = start.get_offset()
                        for o in matches:
                            start.set_offset(offset + o[1 + 2 * i])
                            end.set_offset(offset + o[2 + 2 * i])

                            # Check whether the identified difference is just a
                            # combining diacritic. If so, we want to highlight
                            # the visual character it's a part of
                            if not start.is_cursor_position():
                                start.backward_cursor_position()
                            if not end.is_cursor_position():
                                end.forward_cursor_position()

                            bufs[i].apply_tag(tags[i], start, end)

                start_marks = [
                    bufs[0].create_mark(None, buf_from_iters[0], True),
                    bufs[1].create_mark(None, buf_to_iters[0], True),
                ]
                end_marks = [
                    bufs[0].create_mark(None, buf_from_iters[1], True),
                    bufs[1].create_mark(None, buf_to_iters[1], True),
                ]
                match_cb = functools.partial(
                    apply_highlight, bufs, tags, start_marks, end_marks, (text1, textn),
                    to_pane, chunk)
                self._cached_match.match(text1, textn, match_cb)

        self._cached_match.clean(self.linediffer.diff_count())

        self._set_merge_action_sensitivity()

        # Check for self-comparison using Gio's file IDs, so that we catch
        # symlinks, admin:// URIs and similar situations.
        duplicate_file = None
        seen_file_ids = []
        for tb in self.textbuffer:
            if not tb.data.gfile:
                continue
            if tb.data.file_id in seen_file_ids:
                duplicate_file = tb.data.label
                break
            seen_file_ids.append(tb.data.file_id)

        if duplicate_file:
            for index in range(self.num_panes):
                primary = _("File {} is being compared to itself").format(duplicate_file)
                self.msgarea_mgr[index].add_dismissable_msg(
                    'dialog-warning-symbolic', primary, '', self.msgarea_mgr)
        elif self.linediffer.sequences_identical():
            error_message = True in [m.has_message() for m in self.msgarea_mgr]
            if self.num_panes == 1 or error_message:
                return
            for index, mgr in enumerate(self.msgarea_mgr):
                primary = _("Files are identical")
                secondary_text = None
                # TODO: Currently this only checks to see whether text filters
                # are active, and may be altering the comparison. It would be
                # better if we only showed this message if the filters *did*
                # change the text in question.
                active_filters = any([f.active for f in self.text_filters])

                bufs = self.textbuffer[:self.num_panes]
                newlines = [b.data.sourcefile.get_newline_type() for b in bufs]
                different_newlines = not misc.all_same(newlines)

                if active_filters:
                    secondary_text = _("Text filters are being used, and may "
                                       "be masking differences between files. "
                                       "Would you like to compare the "
                                       "unfiltered files?")
                elif different_newlines:
                    primary = _("Files differ in line endings only")
                    secondary_text = _(
                        "Files are identical except for differing line "
                        "endings:\n%s")

                    labels = [b.data.label for b in bufs]
                    newline_types = [
                        n if isinstance(n, tuple) else (n,) for n in newlines]
                    newline_strings = []
                    for label, nl_types in zip(labels, newline_types):
                        nl_string = ", ".join(NEWLINES[n][1] for n in nl_types)
                        newline_strings.append("\t%s: %s" % (label, nl_string))
                    secondary_text %= "\n".join(newline_strings)

                msgarea = mgr.new_from_text_and_icon(primary, secondary_text)
                mgr.set_msg_id(FileDiff.MSG_SAME)
                button = msgarea.add_button(_("Hide"), Gtk.ResponseType.CLOSE)
                if index == 0:
                    button.props.label = _("Hi_de")

                if active_filters:
                    msgarea.add_button(_("Show without filters"),
                                       Gtk.ResponseType.OK)

                msgarea.connect("response", self.on_msgarea_identical_response)
                msgarea.show_all()
        else:
            for m in self.msgarea_mgr:
                if m.get_msg_id() == FileDiff.MSG_SAME:
                    m.clear()

    def _prompt_long_highlighting(self):

        def on_msgarea_highlighting_response(msgarea, respid):
            for mgr in self.msgarea_mgr:
                mgr.clear()
            if respid == Gtk.ResponseType.OK:
                self.force_highlight = True
                self.refresh_comparison()

        for index, mgr in enumerate(self.msgarea_mgr):
            msgarea = mgr.new_from_text_and_icon(
                _("Change highlighting incomplete"),
                _("Some changes were not highlighted because they were too "
                  "large. You can force Meld to take longer to highlight "
                  "larger changes, though this may be slow."),
            )
            mgr.set_msg_id(FileDiff.MSG_SLOW_HIGHLIGHT)
            button = msgarea.add_button(_("Hi_de"), Gtk.ResponseType.CLOSE)
            if index == 0:
                button.props.label = _("Hi_de")
            button = msgarea.add_button(
                _("Keep highlighting"), Gtk.ResponseType.OK)
            if index == 0:
                button.props.label = _("_Keep highlighting")
            msgarea.connect("response",
                            on_msgarea_highlighting_response)
            msgarea.show_all()

    def on_msgarea_identical_response(self, msgarea, respid):
        for mgr in self.msgarea_mgr:
            mgr.clear()
        if respid == Gtk.ResponseType.OK:
            self.text_filters = []
            self.refresh_comparison()

    @user_critical(
        _("Saving failed"),
        _("Please consider copying any critical changes to "
          "another program or file to avoid data loss."),
    )
    def save_file(self, pane, saveas=False, force_overwrite=False):
        buf = self.textbuffer[pane]
        bufdata = buf.data
        if saveas or not (bufdata.gfile or bufdata.savefile) \
                or not bufdata.writable:
            if pane == 0:
                prompt = _("Save Left Pane As")
            elif pane == 1 and self.num_panes == 3:
                prompt = _("Save Middle Pane As")
            else:
                prompt = _("Save Right Pane As")
            gfile = prompt_save_filename(prompt, self)
            if not gfile:
                return False
            bufdata.label = gfile.get_path()
            bufdata.gfile = gfile
            bufdata.savefile = None
            self.filelabel[pane].props.gfile = gfile

        if not force_overwrite and not bufdata.current_on_disk():
            primary = (
                _("File %s has changed on disk since it was opened") %
                bufdata.gfile.get_parse_name())
            secondary = _("If you save it, any external changes will be lost.")
            msgarea = self.msgarea_mgr[pane].new_from_text_and_icon(
                primary, secondary, "dialog-warning-symbolic"
            )
            msgarea.add_button(_("Save Anyway"), Gtk.ResponseType.ACCEPT)
            msgarea.add_button(_("Don’t Save"), Gtk.ResponseType.CLOSE)

            def on_file_changed_response(msgarea, response_id, *args):
                self.msgarea_mgr[pane].clear()
                if response_id == Gtk.ResponseType.ACCEPT:
                    self.save_file(pane, saveas, force_overwrite=True)

            msgarea.connect("response", on_file_changed_response)
            msgarea.show_all()
            return False

        saver = GtkSource.FileSaver.new_with_target(
            self.textbuffer[pane], bufdata.sourcefile, bufdata.gfiletarget)
        # TODO: Think about removing this flag and above handling, and instead
        # handling the GtkSource.FileSaverError.EXTERNALLY_MODIFIED error
        if force_overwrite:
            saver.set_flags(GtkSource.FileSaverFlags.IGNORE_MODIFICATION_TIME)
        bufdata.disconnect_monitor()
        saver.save_async(
            GLib.PRIORITY_HIGH,
            callback=self.file_saved_cb,
            user_data=(pane,)
        )
        return True

    def file_saved_cb(self, saver, result, user_data):
        gfile = saver.get_location()
        pane = user_data[0]
        buf = saver.get_buffer()
        buf.data.connect_monitor()

        try:
            saver.save_finish(result)
        except GLib.Error as err:
            # TODO: Handle recoverable error cases, like external modifications
            # or invalid buffer characters.
            filename = GLib.markup_escape_text(
                gfile.get_parse_name())

            if err.matches(Gio.io_error_quark(), Gio.IOErrorEnum.INVALID_DATA):
                encoding = saver.get_file().get_encoding()
                secondary = _(
                    "File “{}” contains characters that can’t be encoded "
                    "using its current encoding “{}”."
                ).format(filename, encoding.to_string())
            else:
                secondary = _("Couldn’t save file due to:\n%s") % (
                    GLib.markup_escape_text(str(err)))

            misc.error_dialog(
                primary=_("Could not save file %s.") % filename,
                secondary=secondary,
            )
            self.state = ComparisonState.SavingError
            return

        self.file_changed_signal.emit(gfile.get_path())
        self.undosequence.checkpoint(buf)
        buf.data.update_mtime()
        if pane == 1 and self.num_panes == 3:
            self.meta['middle_saved'] = True

        if self.state == ComparisonState.Closing:
            if not any(b.get_modified() for b in self.textbuffer):
                self.on_delete_event()
        else:
            self.state = ComparisonState.Normal

    def action_format_as_patch(self, *extra):
        dialog = PatchDialog(self)
        dialog.run()

    def update_buffer_writable(self, buf):
        writable = buf.data.writable
        self.recompute_label()
        index = self.textbuffer.index(buf)
        self.readonlytoggle[index].props.visible = not writable
        self.set_buffer_editable(buf, writable)

    def set_buffer_editable(self, buf, editable):
        index = self.textbuffer.index(buf)
        self.readonlytoggle[index].set_active(not editable)
        self.readonlytoggle[index].get_child().props.icon_name = (
            'changes-allow-symbolic' if editable else
            'changes-prevent-symbolic')
        self.textview[index].set_editable(editable)
        self.on_cursor_position_changed(buf, None, True)

    @with_focused_pane
    def action_save(self, pane, *args):
        self.save_file(pane)

    @with_focused_pane
    def action_save_as(self, pane, *args):
        self.save_file(pane, saveas=True)

    def action_save_all(self, *args):
        for i in range(self.num_panes):
            if self.textbuffer[i].get_modified():
                self.save_file(i)

    @Gtk.Template.Callback()
    def on_file_save_button_clicked(self, button):
        idx = self.file_save_button.index(button)
        self.save_file(idx)

    @Gtk.Template.Callback()
    def on_file_selected(
            self, button: Gtk.Button, pane: int, file: Gio.File) -> None:

        if not self.check_unsaved_changes():
            return

        self.set_file(pane, file)

    def _get_focused_pane(self):
        for i in range(self.num_panes):
            if self.textview[i].is_focus():
                return i
        return -1

    def check_unsaved_changes(self, buffers=None):
        """Confirm discard of any unsaved changes

        Unlike `check_save_modified`, this does *not* prompt the user
        to save, but rather just confirms whether they want to discard
        changes. This simplifies call sites a *lot* because they don't
        then need to deal with the async state/callback issues
        associated with saving a file.
        """
        buffers = buffers or self.textbuffer
        unsaved = [b.data.label for b in buffers if b.get_modified()]
        if not unsaved:
            return True

        builder = Gtk.Builder.new_from_resource(
            '/org/gnome/meld/ui/revert-dialog.ui')
        dialog = builder.get_object('revert_dialog')
        dialog.set_transient_for(self.get_toplevel())

        filelist = Gtk.Label("\n".join(["\t• " + f for f in unsaved]))
        filelist.props.xalign = 0.0
        filelist.show()
        message_area = dialog.get_message_area()
        message_area.pack_start(filelist, expand=False, fill=True, padding=0)

        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def action_revert(self, *extra):
        if not self.check_unsaved_changes():
            return

        buffers = self.textbuffer[:self.num_panes]
        gfiles = [b.data.gfile for b in buffers]
        encodings = [b.data.encoding for b in buffers]
        self.set_files(gfiles, encodings=encodings)

    def action_refresh(self, *extra):
        self.refresh_comparison()

    def queue_draw(self, junk=None):
        for t in self.textview:
            t.queue_draw()
        for i in range(self.num_panes - 1):
            self.linkmap[i].queue_draw()
        for gutter in self.actiongutter:
            gutter.queue_draw()

    @Gtk.Template.Callback()
    def on_readonly_button_toggled(self, button):
        index = self.readonlytoggle.index(button)
        buf = self.textbuffer[index]
        self.set_buffer_editable(buf, not button.get_active())

    @with_scroll_lock('_sync_hscroll_lock')
    def _sync_hscroll(self, adjustment):
        val = adjustment.get_value()
        for sw in self.scrolledwindow[:self.num_panes]:
            adj = sw.get_hadjustment()
            if adj is not adjustment:
                adj.set_value(val)

    @with_scroll_lock('_sync_vscroll_lock')
    def _sync_vscroll(self, adjustment, master):
        syncpoint = misc.calc_syncpoint(adjustment)

        # Sync point in buffer coords; this will usually be the middle
        # of the screen, except at the top and bottom of the document.
        sync_y = (
            adjustment.get_value() + adjustment.get_page_size() * syncpoint)

        # Find the target line. This is a float because, especially for
        # wrapped lines, the sync point may be half way through a line.
        # Not doing this calculation makes scrolling jerky.
        sync_iter, _ = self.textview[master].get_line_at_y(int(sync_y))
        line_y, height = self.textview[master].get_line_yrange(sync_iter)
        height = height or 1
        target_line = sync_iter.get_line() + ((sync_y - line_y) / height)

        # In the case of two pane scrolling, it's clear how to bind
        # scrollbars: if the user moves the left pane, we move the
        # right pane, and vice versa.
        #
        # For three pane scrolling, we want panes to be tied, but need
        # an influence mapping. In Meld, all influence flows through
        # the middle pane, e.g., the user moves the left pane, that
        # moves the middle pane, and the middle pane moves the right
        # pane. If the user moves the middle pane, then the left and
        # right panes are moved directly.

        scrollbar_influence = ((1, 2), (0, 2), (1, 0))

        for i in scrollbar_influence[master][:self.num_panes - 1]:
            adj = self.scrolledwindow[i].get_vadjustment()

            # Find the chunk, or more commonly the space between
            # chunks, that contains the target line.
            #
            # This is a naive linear search that remains because it's
            # never shown up in profiles. We can't reuse our line cache
            # here; it doesn't have the necessary information in three-
            # way diffs.
            mbegin, mend = 0, self.textbuffer[master].get_line_count()
            obegin, oend = 0, self.textbuffer[i].get_line_count()
            for chunk in self.linediffer.pair_changes(master, i):
                if chunk.start_a >= target_line:
                    mend = chunk.start_a
                    oend = chunk.start_b
                    break
                elif chunk.end_a >= target_line:
                    mbegin, mend = chunk.start_a, chunk.end_a
                    obegin, oend = chunk.start_b, chunk.end_b
                    break
                else:
                    mbegin = chunk.end_a
                    obegin = chunk.end_b

            fraction = (target_line - mbegin) / ((mend - mbegin) or 1)
            other_line = obegin + fraction * (oend - obegin)

            # At this point, we've identified the line within the
            # corresponding chunk that we want to sync to.
            it = self.textbuffer[i].get_iter_at_line(int(other_line))
            val, height = self.textview[i].get_line_yrange(it)
            # Special case line-height adjustment for EOF
            line_factor = 1.0 if it.is_end() else other_line - int(other_line)
            val += line_factor * height
            if syncpoint > 0.5:
                # If we're in the last half page, gradually factor in
                # the overscroll margin.
                overscroll_scale = (syncpoint - 0.5) / 0.5
                overscroll_height = self.textview[i].get_bottom_margin()
                val += overscroll_height * overscroll_scale
            val -= adj.get_page_size() * syncpoint
            val = min(max(val, adj.get_lower()),
                      adj.get_upper() - adj.get_page_size())
            val = math.floor(val)
            adj.set_value(val)

            # If we just changed the central bar, make it the master
            if i == 1:
                master, target_line = 1, other_line

        # FIXME: We should really hook into the adjustments directly on
        # the widgets instead of doing this.
        for lm in self.linkmap:
            lm.queue_draw()
        for gutter in self.actiongutter:
            gutter.queue_draw()

    def set_num_panes(self, n):
        if n == self.num_panes or n not in (1, 2, 3):
            return

        self.num_panes = n
        for widget in (
                self.vbox[:n] + self.file_toolbar[:n] + self.sourcemap[:n] +
                self.linkmap[:n - 1] + self.dummy_toolbar_linkmap[:n - 1] +
                self.statusbar[:n] +
                self.chunkmap[:n] +
                self.actiongutter[:(n - 1) * 2] +
                self.dummy_toolbar_actiongutter[:(n - 1) * 2]):
            widget.show()

        for widget in (
                self.vbox[n:] + self.file_toolbar[n:] + self.sourcemap[n:] +
                self.linkmap[n - 1:] + self.dummy_toolbar_linkmap[n - 1:] +
                self.statusbar[n:] +
                self.chunkmap[n:] +
                self.actiongutter[(n - 1) * 2:] +
                self.dummy_toolbar_actiongutter[(n - 1) * 2:]):
            widget.hide()

        self.set_action_enabled('format-as-patch', n > 1)

        def chunk_iter(i):
            def chunks(bounds):
                for chunk in self.linediffer.single_changes(i, bounds):
                    yield chunk
            return chunks

        def current_chunk_check(i):
            def chunks(change):
                chunk = self.linediffer.locate_chunk(i, change[1])[0]
                return chunk == self.cursor.chunk
            return chunks

        for (w, i) in zip(self.textview, range(self.num_panes)):
            w.chunk_iter = chunk_iter(i)
            w.current_chunk_check = current_chunk_check(i)

        for (w, i) in zip(self.linkmap, (0, self.num_panes - 2)):
            w.associate(self, self.textview[i], self.textview[i + 1])

        for i in range(self.num_panes):
            self.file_save_button[i].set_sensitive(
                self.textbuffer[i].get_modified())
        self.queue_draw()
        self.recompute_label()

    @with_focused_pane
    def action_cut(self, pane, *args):
        buffer = self.textbuffer[pane]
        view = self.textview[pane]

        clipboard = view.get_clipboard(Gdk.SELECTION_CLIPBOARD)
        buffer.cut_clipboard(clipboard, view.get_editable())
        view.scroll_to_mark(buffer.get_insert(), 0.1, False, 0, 0)

    @with_focused_pane
    def action_copy(self, pane, *args):
        buffer = self.textbuffer[pane]
        view = self.textview[pane]

        clipboard = view.get_clipboard(Gdk.SELECTION_CLIPBOARD)
        buffer.copy_clipboard(clipboard)

    @with_focused_pane
    def action_paste(self, pane, *args):
        buffer = self.textbuffer[pane]
        view = self.textview[pane]

        clipboard = view.get_clipboard(Gdk.SELECTION_CLIPBOARD)
        buffer.paste_clipboard(clipboard, None, view.get_editable())
        view.scroll_to_mark(buffer.get_insert(), 0.1, False, 0, 0)

    def copy_chunk(self, src, dst, chunk, copy_up):
        b0, b1 = self.textbuffer[src], self.textbuffer[dst]
        start = b0.get_iter_at_line_or_eof(chunk.start_a)
        end = b0.get_iter_at_line_or_eof(chunk.end_a)
        t0 = b0.get_text(start, end, False)

        if copy_up:
            if chunk.end_a >= b0.get_line_count() and \
               chunk.start_b < b1.get_line_count():
                # TODO: We need to insert a linebreak here, but there is no
                # way to be certain what kind of linebreak to use.
                t0 = t0 + "\n"
            dst_start = b1.get_iter_at_line_or_eof(chunk.start_b)
            mark0 = b1.create_mark(None, dst_start, True)
            new_end = b1.insert_at_line(chunk.start_b, t0)
        else:
            dst_start = b1.get_iter_at_line_or_eof(chunk.end_b)
            mark0 = b1.create_mark(None, dst_start, True)
            new_end = b1.insert_at_line(chunk.end_b, t0)

        mark1 = b1.create_mark(None, new_end, True)
        # FIXME: If the inserted chunk ends up being an insert chunk, then
        # this animation is not visible; this happens often in three-way diffs
        self.textview[dst].add_fading_highlight(mark0, mark1, 'insert', 500000)

    def replace_chunk(self, src, dst, chunk):
        b0, b1 = self.textbuffer[src], self.textbuffer[dst]
        src_start = b0.get_iter_at_line_or_eof(chunk.start_a)
        src_end = b0.get_iter_at_line_or_eof(chunk.end_a)
        dst_start = b1.get_iter_at_line_or_eof(chunk.start_b)
        dst_end = b1.get_iter_at_line_or_eof(chunk.end_b)
        t0 = b0.get_text(src_start, src_end, False)
        mark0 = b1.create_mark(None, dst_start, True)
        b1.begin_user_action()
        b1.delete(dst_start, dst_end)
        new_end = b1.insert_at_line(chunk.start_b, t0)
        b1.place_cursor(b1.get_iter_at_line(chunk.start_b))
        b1.end_user_action()
        mark1 = b1.create_mark(None, new_end, True)
        if chunk.start_a == chunk.end_a:
            # TODO: Need a more specific colour here; conflict is wrong
            colour = 'conflict'
        else:
            # FIXME: If the inserted chunk ends up being an insert chunk, then
            # this animation is not visible; this happens often in three-way
            # diffs
            colour = 'insert'
        self.textview[dst].add_fading_highlight(mark0, mark1, colour, 500000)

    def delete_chunk(self, src, chunk):
        b0 = self.textbuffer[src]
        it = b0.get_iter_at_line_or_eof(chunk.start_a)
        if chunk.end_a >= b0.get_line_count():
            # If this is the end of the buffer, we need to remove the
            # previous newline, because the current line has none.
            it.backward_cursor_position()
        b0.delete(it, b0.get_iter_at_line_or_eof(chunk.end_a))
        mark0 = b0.create_mark(None, it, True)
        mark1 = b0.create_mark(None, it, True)
        # TODO: Need a more specific colour here; conflict is wrong
        self.textview[src].add_fading_highlight(
            mark0, mark1, 'conflict', 500000)

    @with_focused_pane
    def add_sync_point(self, pane, *args):
        cursor_it = self.textbuffer[pane].get_iter_at_mark(
            self.textbuffer[pane].get_insert())

        self.syncpoints.add(
            pane,
            self.textbuffer[pane].create_mark(None, cursor_it)
        )

        self.refresh_sync_points()

    @with_focused_pane
    def remove_sync_point(self, pane, *args):
        self.syncpoints.remove(pane, self.textbuffer[pane].get_insert())
        self.refresh_sync_points()

    def refresh_sync_points(self):
        for i, t in enumerate(self.textview[:self.num_panes]):
            t.syncpoints = self.syncpoints.points(i)

        def make_line_retriever(pane, marks):
            buf = self.textbuffer[pane]
            mark = marks[pane]

            def get_line_for_mark():
                return buf.get_iter_at_mark(mark).get_line()
            return get_line_for_mark

        valid_points = self.syncpoints.valid_points()

        if valid_points and self.num_panes == 2:
            self.linediffer.syncpoints = [
                ((make_line_retriever(1, p), make_line_retriever(0, p)), )
                for p in valid_points
            ]
        elif valid_points and self.num_panes == 3:
            self.linediffer.syncpoints = [
                ((make_line_retriever(1, p), make_line_retriever(0, p)),
                 (make_line_retriever(1, p), make_line_retriever(2, p)))
                for p in valid_points
            ]
        elif not valid_points:
            self.linediffer.syncpoints = []

        if valid_points:
            for mgr in self.msgarea_mgr:
                msgarea = mgr.new_from_text_and_icon(
                    _("Live comparison updating disabled"),
                    _("Live updating of comparisons is disabled when "
                      "synchronization points are active. You can still "
                      "manually refresh the comparison, and live updates will "
                      "resume when synchronization points are cleared."),
                )
                mgr.set_msg_id(FileDiff.MSG_SYNCPOINTS)
                msgarea.show_all()

        self.refresh_comparison()

    def clear_sync_points(self, *args):
        self.syncpoints.clear()
        self.linediffer.syncpoints = []
        for t in self.textview:
            t.syncpoints = []
        for mgr in self.msgarea_mgr:
            if mgr.get_msg_id() == FileDiff.MSG_SYNCPOINTS:
                mgr.clear()
        self.refresh_comparison()

    def action_swap(self, *args):
        buffers = self.textbuffer[:self.num_panes]
        gfiles = [buf.data.gfile for buf in buffers]

        have_unnamed_files = any(gfile is None for gfile in gfiles)
        have_modified_files = any(buf.get_modified() for buf in buffers)

        if have_unnamed_files or have_modified_files:
            misc.error_dialog(
                primary=_("Can't swap unsaved files"),
                secondary=_(
                    "Files must be saved to disk before swapping panes."
                )
            )
            return

        if self.meta.get("tablabel", None):
            misc.error_dialog(
                primary=_("Can't swap version control comparisons"),
                secondary=_(
                    "Swapping panes is not supported in version control mode."
                )
            )
            return

        self.set_labels([self.filelabel[1].props.label,
                        self.filelabel[0].props.label])
        self.set_files([gfiles[1], gfiles[0]])


FileDiff.set_css_name('meld-file-diff')


class SyncpointAction(Enum):
    # A dangling syncpoint can be moved to the line
    MOVE = "move"
    # A dangling syncpoint sits can be remove from this line
    DELETE = "delete"
    # A syncpoint can be added to this line to match existing ones
    # in other panes
    MATCH = "match"
    # A new, dangling syncpoint can be added to this line
    ADD = "add"
    # No syncpoint-related action can be taken on this line
    DISABLED = "disabled"


class Syncpoints:
    def __init__(self, num_panes: int, comparator):
        self._num_panes = num_panes
        self._points = [[] for _i in range(0, num_panes)]
        self._comparator = comparator

    def add(self, pane_idx: int, point):
        pane_state = self._pane_state(pane_idx)

        if pane_state == self.PaneState.DANGLING:
            self._points[pane_idx].pop()

        self._points[pane_idx].append(point)

        lengths = set(len(p) for p in self._points)

        if len(lengths) == 1:
            for (i, p) in enumerate(self._points):
                p.sort(key=lambda point: self._comparator(i, point))

    def remove(self, pane_idx: int, cursor_point):
        cursor_key = self._comparator(pane_idx, cursor_point)

        index = -1

        for (i, point) in enumerate(self._points[pane_idx]):
            if self._comparator(pane_idx, point) == cursor_key:
                index = i
                break

        assert index is not None

        pane_state = self._pane_state(pane_idx)

        assert pane_state != self.PaneState.SHORT

        if pane_state == self.PaneState.MATCHED:
            for pane in self._points:
                pane.pop(index)
        elif pane_state == self.PaneState.DANGLING:
            self._points[pane_idx].pop()

    def clear(self):
        self._points = [[] for _i in range(0, self._num_panes)]

    def points(self, pane_idx: int):
        return self._points[pane_idx].copy()

    def valid_points(self):
        num_matched = min(len(p) for p in self._points)

        if not num_matched:
            return []

        matched = [p[:num_matched] for p in self._points]

        return [
            tuple(matched_point[i] for matched_point in matched)
            for i in range(0, num_matched)
        ]

    def _pane_state(self, pane_idx: int):
        lengths = set(len(points) for points in self._points)

        if len(lengths) == 1:
            return self.PaneState.MATCHED

        if len(self._points[pane_idx]) == min(lengths):
            return self.PaneState.SHORT
        else:
            return self.PaneState.DANGLING

    def action(self, pane_idx: int, get_mark):
        state = self._pane_state(pane_idx)

        if state == self.PaneState.SHORT:
            return SyncpointAction.MATCH

        target = self._comparator(pane_idx, get_mark())

        points = self._points[pane_idx]

        if state == self.PaneState.MATCHED:
            is_syncpoint = any(
                self._comparator(pane_idx, point) == target
                for point in points
            )

            if is_syncpoint:
                return SyncpointAction.DELETE
            else:
                return SyncpointAction.ADD

        # state == DANGLING
        if target == self._comparator(pane_idx, points[-1]):
            return SyncpointAction.DELETE

        is_syncpoint = any(
            self._comparator(pane_idx, point) == target
            for point in points
        )

        if is_syncpoint:
            return SyncpointAction.DISABLED
        else:
            return SyncpointAction.MOVE

    class PaneState(Enum):
        # The state of a pane with all its syncpoints matched
        MATCHED = "matched"
        # The state of a pane waiting to be matched to existing syncpoints
        # in other panes
        SHORT = "short"
        # The state of a pane with a dangling syncpoint, not yet matched
        # across all panes
        DANGLING = "DANGLING"
