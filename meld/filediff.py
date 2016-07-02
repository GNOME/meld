# coding=UTF-8

# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009-2015 Kai Willadsen <kai.willadsen@gmail.com>
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
import os
import time

from multiprocessing import Pool
from multiprocessing.pool import ThreadPool


from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gio
from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.conf import _
from . import diffutil
from . import matchers
from . import meldbuffer
from . import melddoc
from . import merge
from . import misc
from . import patchdialog
from . import recent
from . import undo
from .ui import findbar
from .ui import gnomeglade

from meld.const import MODE_REPLACE, MODE_DELETE, MODE_INSERT, NEWLINES
from meld.settings import bind_settings, meldsettings
from .util.compat import text_type
from meld.sourceview import LanguageManager, get_custom_encoding_candidates


def with_focused_pane(function):
    @functools.wraps(function)
    def wrap_function(*args, **kwargs):
        pane = args[0]._get_focused_pane()
        if pane == -1:
            return
        return function(args[0], pane, *args[1:], **kwargs)
    return wrap_function


class CachedSequenceMatcher(object):
    """Simple class for caching diff results, with LRU-based eviction

    Results from the SequenceMatcher are cached and timestamped, and
    subsequently evicted based on least-recent generation/usage. The LRU-based
    eviction is overly simplistic, but is okay for our usage pattern.
    """

    process_pool = None

    def __init__(self):
        if self.process_pool is None:
            if os.name == "nt":
                CachedSequenceMatcher.process_pool = ThreadPool(None)
            else:
                CachedSequenceMatcher.process_pool = Pool(
                    None, matchers.init_worker, maxtasksperchild=1)
        self.cache = {}

    def match(self, text1, textn, cb):
        try:
            self.cache[(text1, textn)][1] = time.time()
            opcodes = self.cache[(text1, textn)][0]
            GLib.idle_add(lambda: cb(opcodes))
        except KeyError:
            def inline_cb(opcodes):
                self.cache[(text1, textn)] = [opcodes, time.time()]
                GLib.idle_add(lambda: cb(opcodes))
            self.process_pool.apply_async(matchers.matcher_worker,
                                          (text1, textn),
                                          callback=inline_cb)

    def clean(self, size_hint):
        """Clean the cache if necessary

        @param size_hint: the recommended minimum number of cache entries
        """
        if len(self.cache) < size_hint * 3:
            return
        items = self.cache.items()
        items.sort(key=lambda it: it[1][1])
        for item in items[:-size_hint * 2]:
            del self.cache[item[0]]


MASK_SHIFT, MASK_CTRL = 1, 2
PANE_LEFT, PANE_RIGHT = -1, +1


class CursorDetails(object):
    __slots__ = ("pane", "pos", "line", "offset", "chunk", "prev", "next",
                 "prev_conflict", "next_conflict")

    def __init__(self):
        for var in self.__slots__:
            setattr(self, var, None)


class FileDiff(melddoc.MeldDoc, gnomeglade.Component):
    """Two or three way comparison of text files"""

    __gtype_name__ = "FileDiff"

    __gsettings_bindings__ = (
        ('ignore-blank-lines', 'ignore-blank-lines'),
    )

    ignore_blank_lines = GObject.property(
        type=bool,
        nick="Ignore blank lines",
        blurb="Whether to ignore blank lines when comparing file contents",
        default=False,
    )

    differ = diffutil.Differ

    keylookup = {
        Gdk.KEY_Shift_L: MASK_SHIFT,
        Gdk.KEY_Shift_R: MASK_SHIFT,
        Gdk.KEY_Control_L: MASK_CTRL,
        Gdk.KEY_Control_R: MASK_CTRL,
    }

    # Identifiers for MsgArea messages
    (MSG_SAME, MSG_SLOW_HIGHLIGHT, MSG_SYNCPOINTS) = list(range(3))

    __gsignals__ = {
        'next-conflict-changed': (GObject.SignalFlags.RUN_FIRST, None, (bool, bool)),
        'action-mode-changed': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self, num_panes):
        """Start up an filediff with num_panes empty contents.
        """
        melddoc.MeldDoc.__init__(self)
        gnomeglade.Component.__init__(
            self, "filediff.ui", "filediff", ["FilediffActions"])
        bind_settings(self)

        widget_lists = [
            "diffmap", "file_save_button", "file_toolbar", "fileentry",
            "linkmap", "msgarea_mgr", "readonlytoggle",
            "scrolledwindow", "selector_hbox", "textview", "vbox",
            "dummy_toolbar_linkmap", "filelabel_toolitem", "filelabel",
            "fileentry_toolitem", "dummy_toolbar_diffmap"
        ]
        self.map_widgets_into_lists(widget_lists)

        # This SizeGroup isn't actually necessary for FileDiff; it's for
        # handling non-homogenous selectors in FileComp. It's also fragile.
        column_sizes = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        column_sizes.set_ignore_hidden(True)
        for widget in self.selector_hbox:
            column_sizes.add_widget(widget)

        self.warned_bad_comparison = False
        self._keymask = 0
        self.meta = {}
        self.deleted_lines_pending = -1
        self.textview_overwrite = 0
        self.focus_pane = None
        self.textview_overwrite_handlers = [ t.connect("toggle-overwrite", self.on_textview_toggle_overwrite) for t in self.textview ]
        self.textbuffer = [v.get_buffer() for v in self.textview]
        self.buffer_texts = [meldbuffer.BufferLines(b) for b in self.textbuffer]
        self.undosequence = undo.UndoSequence()
        self.text_filters = []
        self.create_text_filters()
        self.settings_handlers = [
            meldsettings.connect("text-filters-changed",
                                 self.on_text_filters_changed)
        ]
        self.buffer_filtered = [meldbuffer.BufferLines(b, self._filter_text)
                                for b in self.textbuffer]
        for (i, w) in enumerate(self.scrolledwindow):
            w.get_vadjustment().connect("value-changed", self._sync_vscroll, i)
            w.get_hadjustment().connect("value-changed", self._sync_hscroll)
            # Revert overlay scrolling that messes with widget interactivity
            if hasattr(w, 'set_overlay_scrolling'):
                w.set_overlay_scrolling(False)
        self._connect_buffer_handlers()
        self._sync_vscroll_lock = False
        self._sync_hscroll_lock = False
        self._scroll_lock = False
        self.linediffer = self.differ()
        self.force_highlight = False
        self.syncpoints = []
        self.in_nested_textview_gutter_expose = False
        self._cached_match = CachedSequenceMatcher()

        for buf in self.textbuffer:
            buf.undo_sequence = self.undosequence
            buf.connect("notify::has-selection",
                        self.update_text_actions_sensitivity)
            buf.data.connect('file-changed', self.notify_file_changed)

        self.ui_file = gnomeglade.ui_file("filediff-ui.xml")
        self.actiongroup = self.FilediffActions
        self.actiongroup.set_translation_domain("meld")

        self.findbar = findbar.FindBar(self.grid)
        self.grid.attach(self.findbar.widget, 1, 2, 5, 1)

        self.set_num_panes(num_panes)
        self.cursor = CursorDetails()
        self.connect("current-diff-changed", self.on_current_diff_changed)
        for t in self.textview:
            t.connect("focus-in-event", self.on_current_diff_changed)
            t.connect("focus-out-event", self.on_current_diff_changed)
        self.linediffer.connect("diffs-changed", self.on_diffs_changed)
        self.undosequence.connect("checkpointed", self.on_undo_checkpointed)
        self.connect("next-conflict-changed", self.on_next_conflict_changed)

        for diffmap in self.diffmap:
            self.linediffer.connect('diffs-changed', diffmap.on_diffs_changed)

        overwrite_label = Gtk.Label()
        overwrite_label.show()
        cursor_label = Gtk.Label()
        cursor_label.show()
        self.status_info_labels = [overwrite_label, cursor_label]
        self.statusbar.set_info_box(self.status_info_labels)

        # Prototype implementation

        from meld.gutterrendererchunk import GutterRendererChunkAction, GutterRendererChunkLines

        for pane, t in enumerate(self.textview):
            # FIXME: set_num_panes will break this good
            direction = t.get_direction()

            if pane == 0 or (pane == 1 and self.num_panes == 3):
                window = Gtk.TextWindowType.RIGHT
                if direction == Gtk.TextDirection.RTL:
                    window = Gtk.TextWindowType.LEFT
                views = [self.textview[pane], self.textview[pane + 1]]
                renderer = GutterRendererChunkAction(pane, pane + 1, views, self, self.linediffer)
                gutter = t.get_gutter(window)
                gutter.insert(renderer, 10)
            if pane in (1, 2):
                window = Gtk.TextWindowType.LEFT
                if direction == Gtk.TextDirection.RTL:
                    window = Gtk.TextWindowType.RIGHT
                views = [self.textview[pane], self.textview[pane - 1]]
                renderer = GutterRendererChunkAction(pane, pane - 1, views, self, self.linediffer)
                gutter = t.get_gutter(window)
                gutter.insert(renderer, -40)

            # TODO: This renderer handling should all be part of
            # MeldSourceView, but our current diff-chunk-handling makes
            # this difficult.
            window = Gtk.TextWindowType.LEFT
            if direction == Gtk.TextDirection.RTL:
                window = Gtk.TextWindowType.RIGHT
            renderer = GutterRendererChunkLines(pane, pane - 1, self.linediffer)
            renderer.set_properties(
                "alignment-mode", GtkSource.GutterRendererAlignmentMode.FIRST,
                "yalign", 0.5,
                "xalign", 1.0,
                "xpad", 3,
            )
            gutter = t.get_gutter(window)
            gutter.insert(renderer, -30)
            t.line_renderer = renderer

        self.connect("notify::ignore-blank-lines", self.refresh_comparison)

    def get_keymask(self):
        return self._keymask
    def set_keymask(self, value):
        if value & MASK_SHIFT:
            mode = MODE_DELETE
        elif value & MASK_CTRL:
            mode = MODE_INSERT
        else:
            mode = MODE_REPLACE
        self._keymask = value
        self.emit("action-mode-changed", mode)
    keymask = property(get_keymask, set_keymask)

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
            if event.keyval == Gdk.KEY_Return and self.keymask & MASK_SHIFT:
                self.findbar.start_find_previous(self.focus_pane)
            self.keymask &= ~mod_key

    def on_focus_change(self):
        self.keymask = 0

    def on_text_filters_changed(self, app):
        relevant_change = self.create_text_filters()
        if relevant_change:
            self.refresh_comparison()

    def create_text_filters(self):
        # In contrast to file filters, ordering of text filters can matter
        old_active = [f.filter_string for f in self.text_filters if f.active]
        new_active = [f.filter_string for f in meldsettings.text_filters
                      if f.active]
        active_filters_changed = old_active != new_active

        self.text_filters = [copy.copy(f) for f in meldsettings.text_filters]

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
            id3 = buf.connect_after("delete-range", self.after_text_delete_range)
            id4 = buf.connect("notify::cursor-position",
                              self.on_cursor_position_changed)
            buf.handlers = id0, id1, id2, id3, id4

    # Abbreviations for insert and overwrite that fit in the status bar
    _insert_overwrite_text = (_("INS"), _("OVR"))
    # Abbreviation for line, column so that it will fit in the status bar
    _line_column_text = _("Ln %i, Col %i")

    def on_cursor_position_changed(self, buf, pspec, force=False):
        pane = self.textbuffer.index(buf)
        pos = buf.props.cursor_position
        if pane == self.cursor.pane and pos == self.cursor.pos and not force:
            return
        self.cursor.pane, self.cursor.pos = pane, pos

        cursor_it = buf.get_iter_at_offset(pos)
        offset = cursor_it.get_line_offset()
        line = cursor_it.get_line()

        insert_overwrite = self._insert_overwrite_text[self.textview_overwrite]
        line_column = self._line_column_text % (line + 1, offset + 1)
        self.status_info_labels[0].set_text(insert_overwrite)
        self.status_info_labels[1].set_text(line_column)

        if line != self.cursor.line or force:
            chunk, prev, next_ = self.linediffer.locate_chunk(pane, line)
            if chunk != self.cursor.chunk or force:
                self.cursor.chunk = chunk
                self.emit("current-diff-changed")
            if prev != self.cursor.prev or next_ != self.cursor.next or force:
                self.emit("next-diff-changed", prev is not None,
                          next_ is not None)

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
        self.cursor.line, self.cursor.offset = line, offset

    def on_current_diff_changed(self, widget, *args):
        pane = self._get_focused_pane()
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

            # Push and Delete are active if the current pane has something to
            # act on, and the target pane exists and is editable. Pull is
            # sensitive if the source pane has something to get, and the
            # current pane is editable. Copy actions are sensitive if the
            # conditions for push are met, *and* there is some content in the
            # target pane.
            editable = self.textview[pane].get_editable()
            editable_left = pane > 0 and self.textview[pane - 1].get_editable()
            editable_right = pane < self.num_panes - 1 and \
                             self.textview[pane + 1].get_editable()
            if pane == 0 or pane == 2:
                chunk = self.linediffer.get_chunk(chunk_id, pane)
                insert_chunk = chunk[1] == chunk[2]
                delete_chunk = chunk[3] == chunk[4]
                push_left = editable_left
                push_right = editable_right
                pull_left = pane == 2 and editable and not delete_chunk
                pull_right = pane == 0 and editable and not delete_chunk
                delete = editable and not insert_chunk
                copy_left = editable_left and not (insert_chunk or delete_chunk)
                copy_right = editable_right and not (insert_chunk or delete_chunk)
            elif pane == 1:
                chunk0 = self.linediffer.get_chunk(chunk_id, 1, 0)
                chunk2 = None
                if self.num_panes == 3:
                    chunk2 = self.linediffer.get_chunk(chunk_id, 1, 2)
                left_mid_exists = chunk0 is not None and chunk0[1] != chunk0[2]
                left_exists = chunk0 is not None and chunk0[3] != chunk0[4]
                right_mid_exists = chunk2 is not None and chunk2[1] != chunk2[2]
                right_exists = chunk2 is not None and chunk2[3] != chunk2[4]
                push_left = editable_left
                push_right = editable_right
                pull_left = editable and left_exists
                pull_right = editable and right_exists
                delete = editable and (left_mid_exists or right_mid_exists)
                copy_left = editable_left and left_mid_exists and left_exists
                copy_right = editable_right and right_mid_exists and right_exists
        self.actiongroup.get_action("PushLeft").set_sensitive(push_left)
        self.actiongroup.get_action("PushRight").set_sensitive(push_right)
        self.actiongroup.get_action("PullLeft").set_sensitive(pull_left)
        self.actiongroup.get_action("PullRight").set_sensitive(pull_right)
        self.actiongroup.get_action("Delete").set_sensitive(delete)
        self.actiongroup.get_action("CopyLeftUp").set_sensitive(copy_left)
        self.actiongroup.get_action("CopyLeftDown").set_sensitive(copy_left)
        self.actiongroup.get_action("CopyRightUp").set_sensitive(copy_right)
        self.actiongroup.get_action("CopyRightDown").set_sensitive(copy_right)

        prev_pane = pane > 0
        next_pane = pane < self.num_panes - 1
        self.actiongroup.get_action("PrevPane").set_sensitive(prev_pane)
        self.actiongroup.get_action("NextPane").set_sensitive(next_pane)
        # FIXME: don't queue_draw() on everything... just on what changed
        self.queue_draw()

    def on_next_conflict_changed(self, doc, have_prev, have_next):
        self.actiongroup.get_action("PrevConflict").set_sensitive(have_prev)
        self.actiongroup.get_action("NextConflict").set_sensitive(have_next)

    def go_to_chunk(self, target, pane=None, centered=False):
        if target is None:
            return

        if pane is None:
            pane = self._get_focused_pane()
            if pane == -1:
                pane = 1 if self.num_panes > 1 else 0

        chunk = self.linediffer.get_chunk(target, pane)
        if not chunk:
            return

        # Warp the cursor to the first line of the chunk
        buf = self.textbuffer[pane]
        if self.cursor.line != chunk[1]:
            buf.place_cursor(buf.get_iter_at_line(chunk[1]))

        tolerance = 0.0 if centered else 0.2
        self.textview[pane].scroll_to_mark(
            buf.get_insert(), tolerance, True, 0.5, 0.5)

    def next_diff(self, direction, centered=False):
        target = (self.cursor.next if direction == Gdk.ScrollDirection.DOWN
                  else self.cursor.prev)
        self.go_to_chunk(target, centered=centered)

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
        if (src not in valid_panes or dst not in valid_panes or
                self.cursor.chunk is None):
            raise ValueError("Action was taken on invalid panes")

        chunk = self.linediffer.get_chunk(self.cursor.chunk, src, dst)
        if chunk is None:
            raise ValueError("Action was taken on a missing chunk")
        return chunk

    def get_action_panes(self, direction, reverse=False):
        src = self._get_focused_pane()
        dst = src + direction
        return (dst, src) if reverse else (src, dst)

    def action_push_change_left(self, *args):
        src, dst = self.get_action_panes(PANE_LEFT)
        self.replace_chunk(src, dst, self.get_action_chunk(src, dst))

    def action_push_change_right(self, *args):
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
        merger = merge.Merger()
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

    def merge_all_non_conflicting_changes(self, *args):
        dst = 1
        merger = merge.Merger()
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
    def delete_change(self, pane):
        chunk = self.linediffer.get_chunk(self.cursor.chunk, pane)
        assert(self.cursor.chunk is not None)
        assert(chunk is not None)
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

        return "Same", start0, end0, start1, end1

    def _corresponding_chunk_line(self, chunk, line, pane, new_pane):
        """Approximates the corresponding line between panes"""

        old_buf, new_buf = self.textbuffer[pane], self.textbuffer[new_pane]

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

        cursor_chunk, _, _ = self.linediffer.locate_chunk(new_pane, cursor_line)
        if cursor_chunk is not None:
            already_in_chunk = cursor_chunk == chunk
        else:
            cursor_chunk = self._synth_chunk(pane, new_pane, cursor_line)
            already_in_chunk = cursor_chunk[3] == new_start and \
                               cursor_chunk[4] == new_end

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

    def move_cursor_pane(self, pane, new_pane):
        chunk, line = self.cursor.chunk, self.cursor.line
        new_line = self._corresponding_chunk_line(chunk, line, pane, new_pane)

        new_buf = self.textbuffer[new_pane]
        self.textview[new_pane].grab_focus()
        new_buf.place_cursor(new_buf.get_iter_at_line(new_line))
        self.textview[new_pane].scroll_to_mark(
            new_buf.get_insert(), 0.1, True, 0.5, 0.5)

    def action_prev_pane(self, *args):
        pane = self._get_focused_pane()
        new_pane = (pane - 1) % self.num_panes
        self.move_cursor_pane(pane, new_pane)

    def action_next_pane(self, *args):
        pane = self._get_focused_pane()
        new_pane = (pane + 1) % self.num_panes
        self.move_cursor_pane(pane, new_pane)

    def _set_external_action_sensitivity(self):
        have_file = self.focus_pane is not None
        try:
            self.main_actiongroup.get_action("OpenExternal").set_sensitive(
                have_file)
        except AttributeError:
            pass

    def on_textview_focus_in_event(self, view, event):
        self.focus_pane = view
        self.findbar.textview = view
        self.on_cursor_position_changed(view.get_buffer(), None, True)
        self._set_save_action_sensitivity()
        self._set_merge_action_sensitivity()
        self._set_external_action_sensitivity()
        self.update_text_actions_sensitivity()

    def on_textview_focus_out_event(self, view, event):
        self._set_merge_action_sensitivity()
        self._set_external_action_sensitivity()

    def _after_text_modified(self, buffer, startline, sizechange):
        if self.num_panes > 1:
            pane = self.textbuffer.index(buffer)
            if not self.linediffer.syncpoints:
                self.linediffer.change_sequence(pane, startline, sizechange,
                                                self.buffer_filtered)
            # FIXME: diff-changed signal for the current buffer would be cleaner
            focused_pane = self._get_focused_pane()
            if focused_pane != -1:
                self.on_cursor_position_changed(self.textbuffer[focused_pane],
                                                None, True)
            self.queue_draw()

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
                    primary=_(u"Comparison results will be inaccurate"),
                    secondary=_(
                        u"A filter changed the number of lines in the "
                        u"file, which is unsupported. The comparison will "
                        u"not be accurate."),
                )
                self.warned_bad_comparison = True

        return txt

    def after_text_insert_text(self, buf, it, newtext, textlen):
        start_mark = buf.get_mark("insertion-start")
        starting_at = buf.get_iter_at_mark(start_mark).get_line()
        buf.delete_mark(start_mark)
        lines_added = it.get_line() - starting_at
        self._after_text_modified(buf, starting_at, lines_added)

    def after_text_delete_range(self, buffer, it0, it1):
        starting_at = it0.get_line()
        assert self.deleted_lines_pending != -1
        self._after_text_modified(buffer, starting_at, -self.deleted_lines_pending)
        self.deleted_lines_pending = -1


    def check_save_modified(self):
        response = Gtk.ResponseType.OK
        modified = [b.get_modified() for b in self.textbuffer[:self.num_panes]]
        labels = [b.data.label for b in self.textbuffer[:self.num_panes]]
        if True in modified:
            dialog = gnomeglade.Component("filediff.ui", "check_save_dialog")
            dialog.widget.set_transient_for(self.widget.get_toplevel())
            message_area = dialog.widget.get_message_area()
            buttons = []
            for label, should_save in zip(labels, modified):
                button = Gtk.CheckButton.new_with_label(label)
                button.set_sensitive(should_save)
                button.set_active(should_save)
                message_area.pack_start(
                    button, expand=False, fill=True, padding=0)
                buttons.append(button)
            message_area.show_all()
            response = dialog.widget.run()
            try_save = [b.get_active() for b in buttons]
            dialog.widget.destroy()
            if response == Gtk.ResponseType.OK and any(try_save):
                for i in range(self.num_panes):
                    if try_save[i]:
                        self.save_file(i)
                return Gtk.ResponseType.CANCEL

        if response == Gtk.ResponseType.DELETE_EVENT:
            response = Gtk.ResponseType.CANCEL
        elif response == Gtk.ResponseType.CLOSE:
            response = Gtk.ResponseType.OK

        if response == Gtk.ResponseType.OK and self.meta:
            parent = self.meta.get('parent', None)
            saved = self.meta.get('middle_saved', False)
            prompt_resolve = self.meta.get('prompt_resolve', False)
            if prompt_resolve and saved and parent.has_command('resolve'):
                primary = _("Mark conflict as resolved?")
                secondary = _(
                    "If the conflict was resolved successfully, you may mark "
                    "it as resolved now.")
                buttons = ((_("Cancel"), Gtk.ResponseType.CANCEL),
                           (_("Mark _Resolved"), Gtk.ResponseType.OK))
                resolve_response = misc.modal_dialog(
                    primary, secondary, buttons, parent=self.widget,
                    messagetype=Gtk.MessageType.QUESTION)

                if resolve_response == Gtk.ResponseType.OK:
                    bufdata = self.textbuffer[1].data
                    conflict_file = bufdata.savefile or bufdata.filename
                    parent.command('resolve', [conflict_file])
        elif response == Gtk.ResponseType.CANCEL:
            self.state = melddoc.STATE_NORMAL

        return response

    def on_delete_event(self):
        self.state = melddoc.STATE_CLOSING
        response = self.check_save_modified()
        if response == Gtk.ResponseType.OK:
            for h in self.settings_handlers:
                meldsettings.disconnect(h)
            # TODO: Base the return code on something meaningful for VC tools
            self.emit('close', 0)
        return response

    def _scroll_to_actions(self, actions):
        """Scroll all views affected by *actions* to the current cursor"""

        affected_buffers = set(a.buffer for a in actions)
        for buf in affected_buffers:
            buf_index = self.textbuffer.index(buf)
            view = self.textview[buf_index]
            view.scroll_mark_onscreen(buf.get_insert())

    def on_undo_activate(self):
        if self.undosequence.can_undo():
            actions = self.undosequence.undo()
        self._scroll_to_actions(actions)

    def on_redo_activate(self):
        if self.undosequence.can_redo():
            actions = self.undosequence.redo()
        self._scroll_to_actions(actions)

    def on_text_insert_text(self, buf, it, text, textlen):
        text = text_type(text, 'utf8')
        self.undosequence.add_action(
            meldbuffer.BufferInsertionAction(buf, it.get_offset(), text))
        buf.create_mark("insertion-start", it, True)

    def on_text_delete_range(self, buf, it0, it1):
        text = text_type(buf.get_text(it0, it1, False), 'utf8')
        assert self.deleted_lines_pending == -1
        self.deleted_lines_pending = it1.get_line() - it0.get_line()
        self.undosequence.add_action(
            meldbuffer.BufferDeletionAction(buf, it0.get_offset(), text))

    def on_undo_checkpointed(self, undosequence, buf, checkpointed):
        buf.set_modified(not checkpointed)
        self.recompute_label()

    @with_focused_pane
    def open_external(self, pane):
        if not self.textbuffer[pane].data.filename:
            return
        pos = self.textbuffer[pane].props.cursor_position
        cursor_it = self.textbuffer[pane].get_iter_at_offset(pos)
        line = cursor_it.get_line() + 1
        self._open_files([self.textbuffer[pane].data.filename], line)

    def update_text_actions_sensitivity(self, *args):
        widget = self.focus_pane
        if not widget:
            cut, copy, paste = False, False, False
        else:
            cut = copy = widget.get_buffer().get_has_selection()
            # Ideally, this would check whether the clipboard included
            # something pasteable. However, there is no changed signal.
            # widget.get_clipboard(
            #    Gdk.SELECTION_CLIPBOARD).wait_is_text_available()
            paste = widget.get_editable()
        if self.main_actiongroup:
            for action, sens in zip(
                    ("Cut", "Copy", "Paste"), (cut, copy, paste)):
                self.main_actiongroup.get_action(action).set_sensitive(sens)

    @with_focused_pane
    def get_selected_text(self, pane):
        """Returns selected text of active pane"""
        buf = self.textbuffer[pane]
        sel = buf.get_selection_bounds()
        if sel:
            return text_type(buf.get_text(sel[0], sel[1], False), 'utf8')

    def on_find_activate(self, *args):
        selected_text = self.get_selected_text()
        self.findbar.start_find(self.focus_pane, selected_text)
        self.keymask = 0

    def on_replace_activate(self, *args):
        selected_text = self.get_selected_text()
        self.findbar.start_replace(self.focus_pane, selected_text)
        self.keymask = 0

    def on_find_next_activate(self, *args):
        self.findbar.start_find_next(self.focus_pane)

    def on_find_previous_activate(self, *args):
        self.findbar.start_find_previous(self.focus_pane)

    def on_scrolledwindow_size_allocate(self, scrolledwindow, allocation):
        index = self.scrolledwindow.index(scrolledwindow)
        if index == 0 or index == 1:
            self.linkmap[0].queue_draw()
        if index == 1 or index == 2:
            self.linkmap[1].queue_draw()

    def on_textview_popup_menu(self, textview):
        self.popup_menu.popup(None, None, None, None, 0,
                              Gtk.get_current_event_time())
        return True

    def on_textview_button_press_event(self, textview, event):
        if event.button == 3:
            textview.grab_focus()
            self.popup_menu.popup(None, None, None, None, event.button, event.time)
            return True
        return False

    def on_textview_toggle_overwrite(self, view):
        self.textview_overwrite = not self.textview_overwrite
        for v,h in zip(self.textview, self.textview_overwrite_handlers):
            v.disconnect(h)
            if v != view:
                v.emit("toggle-overwrite")
        self.textview_overwrite_handlers = [ t.connect("toggle-overwrite", self.on_textview_toggle_overwrite) for t in self.textview ]
        self.on_cursor_position_changed(view.get_buffer(), None, True)

    def set_labels(self, labels):
        labels = labels[:self.num_panes]
        for label, buf in zip(labels, self.textbuffer):
            if label:
                buf.data.label = label

    def set_merge_output_file(self, filename):
        if self.num_panes < 2:
            return
        buf = self.textbuffer[1]
        buf.data.savefile = os.path.abspath(filename)
        buf.data.label = filename
        self.update_buffer_writable(buf)

        # FIXME: Hack around bgo#737804; remove after GTK+ 3.18 is required
        def set_merge_file_entry():
            self.fileentry[1].set_filename(buf.data.savefile)
        self.scheduler.add_task(set_merge_file_entry)
        self.recompute_label()

    def _set_save_action_sensitivity(self):
        pane = self._get_focused_pane()
        modified = (
            False if pane == -1 else self.textbuffer[pane].get_modified())
        if self.main_actiongroup:
            self.main_actiongroup.get_action("Save").set_sensitive(modified)
        any_modified = any(b.get_modified() for b in self.textbuffer)
        self.actiongroup.get_action("SaveAll").set_sensitive(any_modified)

    def recompute_label(self):
        self._set_save_action_sensitivity()
        filenames = [b.data.label for b in self.textbuffer[:self.num_panes]]
        shortnames = misc.shorten_names(*filenames)

        for i, buf in enumerate(self.textbuffer[:self.num_panes]):
            if buf.get_modified():
                shortnames[i] += "*"
            self.file_save_button[i].set_sensitive(buf.get_modified())
            self.file_save_button[i].props.icon_name = (
                'document-save-symbolic' if buf.data.writable else
                'document-save-as-symbolic')

        label = self.meta.get("tablabel", "")
        if label:
            self.label_text = label
        else:
            self.label_text = (" — ").decode('utf8').join(shortnames)
        self.tooltip_text = self.label_text
        self.label_changed()

    def set_files(self, files):
        """Load the given files

        If an element is None, the text of a pane is left as is.
        """
        if len(files) != self.num_panes:
            return

        self._disconnect_buffer_handlers()
        self.undosequence.clear()
        self.linediffer.clear()

        custom_candidates = get_custom_encoding_candidates()

        files = [(pane, Gio.File.new_for_path(filename))
                 for pane, filename in enumerate(files) if filename]

        if not files:
            self.scheduler.add_task(self._compare_files_internal())

        for pane, gfile in files:
            self.fileentry[pane].set_file(gfile)
            self.msgarea_mgr[pane].clear()

            buf = self.textbuffer[pane]
            buf.data.reset(gfile)

            if buf.data.is_special:
                loader = GtkSource.FileLoader.new_from_stream(
                    buf, buf.data.sourcefile, buf.data.gfile.read())
            else:
                loader = GtkSource.FileLoader.new(buf, buf.data.sourcefile)

            if custom_candidates:
                loader.set_candidate_encodings(custom_candidates)
            loader.load_async(
                GLib.PRIORITY_HIGH,
                callback=self.file_loaded,
                user_data=(pane,)
            )

    def get_comparison(self):
        files = [b.data.filename for b in self.textbuffer[:self.num_panes]]
        return recent.TYPE_FILE, files

    def file_loaded(self, loader, result, user_data):

        gfile = loader.get_location()
        pane = user_data[0]

        try:
            loader.load_finish(result)
        except GLib.Error as err:
            # TODO: Find sane error domain constants
            if err.domain == 'gtk-source-file-loader-error':
                # TODO: Add custom reload-with-encoding handling for
                # GtkSource.FileLoaderError.CONVERSION_FALLBACK and
                # GtkSource.FileLoaderError.ENCODING_AUTO_DETECTION_FAILED
                pass

            filename = GLib.markup_escape_text(
                gfile.get_parse_name()).decode('utf-8')
            primary = _(
                u"There was a problem opening the file “%s”." % filename)
            self.msgarea_mgr[pane].add_dismissable_msg(
                'dialog-error-symbolic', primary, err.message)

        buf = loader.get_buffer()
        start, end = buf.get_bounds()
        buffer_text = buf.get_text(start, end, False)
        if not loader.get_encoding() and '\\00' in buffer_text:
            primary = _("File %s appears to be a binary file.") % filename
            secondary = _(
                "Do you want to open the file using the default application?")
            self.msgarea_mgr[pane].add_action_msg(
                'dialog-warning-symbolic', primary, secondary, _("Open"),
                functools.partial(self._open_files, [gfile.get_path()]))

        self.update_buffer_writable(buf)

        self.undosequence.checkpoint(buf)
        buf.data.update_mtime()
        buf.data.loaded = True

        if all(b.data.loaded for b in self.textbuffer[:self.num_panes]):
            self.scheduler.add_task(self._compare_files_internal())

    def _merge_files(self):
        yield 1

    def _diff_files(self, refresh=False):
        yield _("[%s] Computing differences") % self.label_text
        texts = self.buffer_filtered[:self.num_panes]
        self.linediffer.ignore_blanks = self.props.ignore_blank_lines
        step = self.linediffer.set_sequences_iter(texts)
        while next(step) is None:
            yield 1

        if not refresh:
            chunk, prev, next_ = self.linediffer.locate_chunk(1, 0)
            self.cursor.next = chunk
            if self.cursor.next is None:
                self.cursor.next = next_
            for buf in self.textbuffer:
                buf.place_cursor(buf.get_start_iter())

            if self.cursor.next is not None:
                self.scheduler.add_task(
                    lambda: self.go_to_chunk(self.cursor.next, centered=True),
                    True)
            else:
                buf = self.textbuffer[1 if self.num_panes > 1 else 0]
                self.on_cursor_position_changed(buf, None, True)

        self.queue_draw()
        self._connect_buffer_handlers()
        self._set_merge_action_sensitivity()

        langs = [LanguageManager.get_language_from_file(buf.data.gfile)
                 for buf in self.textbuffer[:self.num_panes]]

        # If we have only one identified language then we assume that all of
        # the files are actually of that type.
        real_langs = [l for l in langs if l]
        if real_langs and real_langs.count(real_langs[0]) == len(real_langs):
            langs = (real_langs[0],) * len(langs)

        for i in range(self.num_panes):
            self.textbuffer[i].set_language(langs[i])

    def _compare_files_internal(self):
        for i in self._merge_files():
            yield i
        for i in self._diff_files():
            yield i
        focus_pane = 0 if self.num_panes < 3 else 1
        self.textview[focus_pane].grab_focus()

    def set_meta(self, meta):
        self.meta = meta
        labels = meta.get('labels', ())
        if labels:
            for i, l in enumerate(labels):
                if l:
                    self.filelabel[i].set_text(l)
                    self.filelabel_toolitem[i].set_visible(True)
                    self.fileentry_toolitem[i].set_visible(False)

    def notify_file_changed(self, data):
        try:
            pane = [b.data for b in self.textbuffer].index(data)
        except ValueError:
            # Notification for unknown buffer
            return
        gfile = Gio.File.new_for_path(data.filename)
        display_name = gfile.get_parse_name().decode('utf-8')
        primary = _("File %s has changed on disk") % display_name
        secondary = _("Do you want to reload the file?")
        self.msgarea_mgr[pane].add_action_msg(
            'dialog-warning-symbolic', primary, secondary, _("_Reload"),
            self.on_revert_activate)

    def refresh_comparison(self, *args):
        """Refresh the view by clearing and redoing all comparisons"""
        self._disconnect_buffer_handlers()
        self.linediffer.clear()

        for buf in self.textbuffer:
            tag = buf.get_tag_table().lookup("inline")
            buf.remove_tag(tag, buf.get_start_iter(), buf.get_end_iter())

        self.queue_draw()
        self.scheduler.add_task(self._diff_files(refresh=True))

    def _set_merge_action_sensitivity(self):
        pane = self._get_focused_pane()
        if pane != -1:
            editable = self.textview[pane].get_editable()
            mergeable = self.linediffer.has_mergeable_changes(pane)
        else:
            editable = False
            mergeable = (False, False)
        self.actiongroup.get_action("MergeFromLeft").set_sensitive(mergeable[0] and editable)
        self.actiongroup.get_action("MergeFromRight").set_sensitive(mergeable[1] and editable)
        if self.num_panes == 3 and self.textview[1].get_editable():
            mergeable = self.linediffer.has_mergeable_changes(1)
        else:
            mergeable = (False, False)
        self.actiongroup.get_action("MergeAll").set_sensitive(mergeable[0] or mergeable[1])

    def on_diffs_changed(self, linediffer, chunk_changes):
        removed_chunks, added_chunks, modified_chunks = chunk_changes

        # We need to clear removed and modified chunks, and need to
        # re-highlight added and modified chunks.
        need_clearing = sorted(list(removed_chunks))
        need_highlighting = sorted(list(added_chunks) + [modified_chunks])

        alltags = [b.get_tag_table().lookup("inline") for b in self.textbuffer]

        for chunk in need_clearing:
            for i, c in enumerate(chunk):
                if not c or c[0] != "replace":
                    continue
                to_idx = 2 if i == 1 else 0
                bufs = self.textbuffer[1], self.textbuffer[to_idx]
                tags = alltags[1], alltags[to_idx]

                starts = [b.get_iter_at_line_or_eof(l) for b, l in
                          zip(bufs, (c[1], c[3]))]
                ends = [b.get_iter_at_line_or_eof(l) for b, l in
                        zip(bufs, (c[2], c[4]))]
                bufs[0].remove_tag(tags[0], starts[0], ends[0])
                bufs[1].remove_tag(tags[1], starts[1], ends[1])

        for chunk in need_highlighting:
            clear = chunk == modified_chunks
            for i, c in enumerate(chunk):
                if not c or c[0] != "replace":
                    continue
                to_idx = 2 if i == 1 else 0
                bufs = self.textbuffer[1], self.textbuffer[to_idx]
                tags = alltags[1], alltags[to_idx]

                starts = [b.get_iter_at_line_or_eof(l) for b, l in
                          zip(bufs, (c[1], c[3]))]
                ends = [b.get_iter_at_line_or_eof(l) for b, l in
                        zip(bufs, (c[2], c[4]))]

                # We don't use self.buffer_texts here, as removing line
                # breaks messes with inline highlighting in CRLF cases
                text1 = bufs[0].get_text(starts[0], ends[0], False)
                text1 = text_type(text1, 'utf8')
                textn = bufs[1].get_text(starts[1], ends[1], False)
                textn = text_type(textn, 'utf8')

                # Bail on long sequences, rather than try a slow comparison
                inline_limit = 10000
                if len(text1) + len(textn) > inline_limit and \
                        not self.force_highlight:
                    for i in range(2):
                        bufs[i].apply_tag(tags[i], starts[i], ends[i])
                    self._prompt_long_highlighting()
                    continue

                def apply_highlight(bufs, tags, start_marks, end_marks, texts, matches):
                    starts = [bufs[0].get_iter_at_mark(start_marks[0]),
                              bufs[1].get_iter_at_mark(start_marks[1])]
                    ends = [bufs[0].get_iter_at_mark(end_marks[0]),
                            bufs[1].get_iter_at_mark(end_marks[1])]
                    text1 = bufs[0].get_text(starts[0], ends[0], False)
                    text1 = text_type(text1, 'utf8')
                    textn = bufs[1].get_text(starts[1], ends[1], False)
                    textn = text_type(textn, 'utf8')

                    bufs[0].delete_mark(start_marks[0])
                    bufs[0].delete_mark(end_marks[0])
                    bufs[1].delete_mark(start_marks[1])
                    bufs[1].delete_mark(end_marks[1])

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
                        start_or_end = (
                            (match.start_a == 0 and match.start_b == 0) or
                            (match.end_a == offsets[0] and match.end_b == offsets[1]))
                        if start_or_end:
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
                            bufs[i].apply_tag(tags[i], start, end)

                starts = [bufs[0].create_mark(None, starts[0], True),
                          bufs[1].create_mark(None, starts[1], True)]
                ends = [bufs[0].create_mark(None, ends[0], True),
                        bufs[1].create_mark(None, ends[1], True)]
                match_cb = functools.partial(apply_highlight, bufs, tags,
                                             starts, ends, (text1, textn))
                self._cached_match.match(text1, textn, match_cb)

        self._cached_match.clean(self.linediffer.diff_count())

        self._set_merge_action_sensitivity()
        if self.linediffer.sequences_identical():
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

                msgarea = mgr.new_from_text_and_icon(
                    'dialog-information-symbolic', primary, secondary_text)
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
                'dialog-information-symbolic',
                _("Change highlighting incomplete"),
                _("Some changes were not highlighted because they were too "
                  "large. You can force Meld to take longer to highlight "
                  "larger changes, though this may be slow."))
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

    def _get_filename_for_saving(self, title ):
        dialog = Gtk.FileChooserDialog(title,
            parent=self.widget.get_toplevel(),
            action=Gtk.FileChooserAction.SAVE,
            buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK) )
        dialog.set_default_response(Gtk.ResponseType.OK)
        response = dialog.run()
        filename = None
        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
        dialog.destroy()
        if filename:
            if os.path.exists(filename):
                parent_name = os.path.dirname(filename)
                file_name = os.path.basename(filename)
                dialog_buttons = [
                    (_("_Cancel"), Gtk.ResponseType.CANCEL),
                    (_("_Replace"), Gtk.ResponseType.OK),
                ]
                replace = misc.modal_dialog(
                    primary=_(u"Replace file “%s”?") % file_name,
                    secondary=_(
                        u"A file with this name already exists in “%s”.\n"
                        u"If you replace the existing file, its contents "
                        u"will be lost.") % parent_name,
                    buttons=dialog_buttons,
                    messagetype=Gtk.MessageType.WARNING,
                )
                if replace != Gtk.ResponseType.OK:
                    return None
            return filename
        return None

    def save_file(self, pane, saveas=False, force_overwrite=False):
        buf = self.textbuffer[pane]
        bufdata = buf.data
        if saveas or not (bufdata.filename or bufdata.savefile) \
                or not bufdata.writable:
            if pane == 0:
                prompt = _("Save Left Pane As")
            elif pane == 1 and self.num_panes == 3:
                prompt = _("Save Middle Pane As")
            else:
                prompt = _("Save Right Pane As")
            filename = self._get_filename_for_saving(prompt)
            if not filename:
                return False
            filename = os.path.abspath(filename)
            bufdata.label = filename
            bufdata.gfile = Gio.File.new_for_path(filename)
            bufdata.savefile = None
            self.fileentry[pane].set_filename(bufdata.filename)
            self.filelabel_toolitem[pane].set_visible(False)
            self.fileentry_toolitem[pane].set_visible(True)

        if not force_overwrite and not bufdata.current_on_disk():
            primary = (
                _("File %s has changed on disk since it was opened") %
                bufdata.gfile.get_parse_name().decode('utf-8'))
            secondary = _("If you save it, any external changes will be lost.")
            msgarea = self.msgarea_mgr[pane].new_from_text_and_icon(
                'dialog-warning-symbolic', primary, secondary)
            msgarea.add_button(_("Save Anyway"), Gtk.ResponseType.ACCEPT)
            msgarea.add_button(_("Don't Save"), Gtk.ResponseType.CLOSE)

            def on_file_changed_response(msgarea, response_id, *args):
                self.msgarea_mgr[pane].clear()
                if response_id == Gtk.ResponseType.ACCEPT:
                    self.save_file(pane, saveas, force_overwrite=True)

            msgarea.connect("response", on_file_changed_response)
            msgarea.show_all()
            return False

        start, end = buf.get_bounds()
        text = text_type(buf.get_text(start, end, False), 'utf8')

        source_encoding = bufdata.sourcefile.get_encoding()
        while isinstance(text, unicode):
            try:
                encoding = source_encoding.get_charset()
                text = text.encode(encoding)
            except UnicodeEncodeError:
                dialog_buttons = [
                    (_("_Cancel"), Gtk.ResponseType.CANCEL),
                    (_("_Save as UTF-8"), Gtk.ResponseType.OK),
                ]
                reencode = misc.modal_dialog(
                    primary=_(u"Couldn't encode text as “%s”") % encoding,
                    secondary=_(
                        u"File “%s” contains characters that can't be encoded "
                        u"using encoding “%s”.\n"
                        u"Would you like to save as UTF-8?") % (
                        bufdata.label, encoding),
                    buttons=dialog_buttons,
                    messagetype=Gtk.MessageType.WARNING
                )
                if reencode != Gtk.ResponseType.OK:
                    return False

                source_encoding = GtkSource.Encoding.get_utf8()

        saver = GtkSource.FileSaver.new_with_target(
            self.textbuffer[pane], bufdata.sourcefile, bufdata.gfiletarget)
        # TODO: Think about removing this flag and above handling, and instead
        # handling the GtkSource.FileSaverError.EXTERNALLY_MODIFIED error
        if force_overwrite:
            saver.set_flags(GtkSource.FileSaverFlags.IGNORE_MODIFICATION_TIME)
        saver.save_async(
            GLib.PRIORITY_HIGH,
            callback=self.file_saved_cb,
            user_data=(pane,)
        )
        return True

    def file_saved_cb(self, saver, result, user_data):
        gfile = saver.get_location()
        pane = user_data[0]

        try:
            saver.save_finish(result)
        except GLib.Error as err:
            # TODO: Handle recoverable error cases, like external modifications
            # or invalid buffer characters.
            filename = GLib.markup_escape_text(
                gfile.get_parse_name()).decode('utf-8')
            misc.error_dialog(
                primary=_("Could not save file %s.") % filename,
                secondary=_("Couldn't save file due to:\n%s") % (
                    GLib.markup_escape_text(str(err))),
            )
            self.state = melddoc.STATE_SAVING_ERROR
            return

        buf = saver.get_buffer()
        self.emit('file-changed', gfile.get_path())
        self.undosequence.checkpoint(buf)
        buf.data.update_mtime()
        if pane == 1 and self.num_panes == 3:
            self.meta['middle_saved'] = True

        if (self.state == melddoc.STATE_CLOSING and
                not any(b.get_modified() for b in self.textbuffer)):
            self.on_delete_event()
        else:
            self.state = melddoc.STATE_NORMAL

    def make_patch(self, *extra):
        dialog = patchdialog.PatchDialog(self)
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
        self.readonlytoggle[index].props.icon_name = (
            'changes-allow-symbolic' if editable else
            'changes-prevent-symbolic')
        self.textview[index].set_editable(editable)
        self.on_cursor_position_changed(buf, None, True)
        for linkmap in self.linkmap:
            linkmap.queue_draw()

    @with_focused_pane
    def save(self, pane):
        self.save_file(pane)

    @with_focused_pane
    def save_as(self, pane):
        self.save_file(pane, saveas=True)

    def on_save_all_activate(self, action):
        for i in range(self.num_panes):
            if self.textbuffer[i].get_modified():
                self.save_file(i)

    def on_file_save_button_clicked(self, button):
        idx = self.file_save_button.index(button)
        self.save_file(idx)

    def on_fileentry_file_set(self, entry):
        entries = self.fileentry[:self.num_panes]
        if self.check_save_modified() != Gtk.ResponseType.CANCEL:
            files = [e.get_file() for e in entries]
            paths = [f.get_path() for f in files]
            self.set_files(paths)
        else:
            idx = entries.index(entry)
            existing_path = self.textbuffer[idx].data.filename
            entry.set_filename(existing_path)
        return True

    def _get_focused_pane(self):
        for i in range(self.num_panes):
            if self.textview[i].is_focus():
                return i
        return -1

    def on_revert_activate(self, *extra):
        response = Gtk.ResponseType.OK
        unsaved = [b.data.label for b in self.textbuffer if b.get_modified()]
        if unsaved:
            dialog = gnomeglade.Component("filediff.ui", "revert_dialog")
            dialog.widget.set_transient_for(self.widget.get_toplevel())
            # FIXME: Should be packed into dialog.widget.get_message_area(),
            # but this is unbound on currently required PyGTK.
            filelist = "\n".join(["\t" + f for f in unsaved])
            dialog.widget.props.secondary_text += filelist
            response = dialog.widget.run()
            dialog.widget.destroy()

        if response == Gtk.ResponseType.OK:
            files = [b.data.filename for b in self.textbuffer[:self.num_panes]]
            self.set_files(files)

    def on_refresh_activate(self, *extra):
        self.refresh_comparison()

    def queue_draw(self, junk=None):
        for t in self.textview:
            t.queue_draw()
        for i in range(self.num_panes-1):
            self.linkmap[i].queue_draw()
        self.diffmap0.queue_draw()
        self.diffmap1.queue_draw()

    def on_action_lock_scrolling_toggled(self, action):
        self.toggle_scroll_lock(action.get_active())

    def toggle_scroll_lock(self, locked):
        self.actiongroup.get_action("LockScrolling").set_active(locked)
        self._scroll_lock = not locked

    def on_readonly_button_toggled(self, button):
        index = self.readonlytoggle.index(button)
        buf = self.textbuffer[index]
        self.set_buffer_editable(buf, not button.get_active())

    def _sync_hscroll(self, adjustment):
        if self._sync_hscroll_lock or self._scroll_lock:
            return

        self._sync_hscroll_lock = True
        val = adjustment.get_value()
        for sw in self.scrolledwindow[:self.num_panes]:
            adj = sw.get_hadjustment()
            if adj is not adjustment:
                adj.set_value(val)
        self._sync_hscroll_lock = False

    def _sync_vscroll(self, adjustment, master):
        # only allow one scrollbar to be here at a time
        if self._sync_vscroll_lock:
            return

        if not self._scroll_lock and (self.keymask & MASK_SHIFT) == 0:
            self._sync_vscroll_lock = True
            syncpoint = 0.5

            # the line to search for in the 'master' text
            master_y = (adjustment.get_value() + adjustment.get_page_size() *
                        syncpoint)
            it = self.textview[master].get_line_at_y(int(master_y))[0]
            line_y, height = self.textview[master].get_line_yrange(it)
            line = it.get_line() + ((master_y-line_y)/height)

            # scrollbar influence 0->1->2 or 0<-1->2 or 0<-1<-2
            scrollbar_influence = ((1, 2), (0, 2), (1, 0))

            for i in scrollbar_influence[master][:self.num_panes - 1]:
                adj = self.scrolledwindow[i].get_vadjustment()
                mbegin, mend = 0, self.textbuffer[master].get_line_count()
                obegin, oend = 0, self.textbuffer[i].get_line_count()
                # look for the chunk containing 'line'
                for c in self.linediffer.pair_changes(master, i):
                    if c[1] >= line:
                        mend = c[1]
                        oend = c[3]
                        break
                    elif c[2] >= line:
                        mbegin, mend = c[1], c[2]
                        obegin, oend = c[3], c[4]
                        break
                    else:
                        mbegin = c[2]
                        obegin = c[4]
                fraction = (line - mbegin) / ((mend - mbegin) or 1)
                other_line = (obegin + fraction * (oend - obegin))
                it = self.textbuffer[i].get_iter_at_line(int(other_line))
                val, height = self.textview[i].get_line_yrange(it)
                val -= (adj.get_page_size()) * syncpoint
                val += (other_line-int(other_line)) * height
                val = min(max(val, adj.get_lower()),
                          adj.get_upper() - adj.get_page_size())
                adj.set_value(val)

                # If we just changed the central bar, make it the master
                if i == 1:
                    master, line = 1, other_line
            self._sync_vscroll_lock = False

        for lm in self.linkmap:
            lm.queue_draw()

    def set_num_panes(self, n):
        if n != self.num_panes and n in (1, 2, 3):
            self.num_panes = n
            for widget in (
                    self.vbox[:n] + self.file_toolbar[:n] + self.diffmap[:n] +
                    self.linkmap[:n - 1] + self.dummy_toolbar_linkmap[:n - 1] +
                    self.dummy_toolbar_diffmap[:n - 1]):
                widget.show()

            for widget in (
                    self.vbox[n:] + self.file_toolbar[n:] + self.diffmap[n:] +
                    self.linkmap[n - 1:] + self.dummy_toolbar_linkmap[n - 1:] +
                    self.dummy_toolbar_diffmap[n - 1:]):
                widget.hide()

            self.actiongroup.get_action("MakePatch").set_sensitive(n > 1)

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

            def coords_iter(i):
                buf_index = 2 if i == 1 and self.num_panes == 3 else i
                get_end_iter = self.textbuffer[buf_index].get_end_iter
                get_iter_at_line = self.textbuffer[buf_index].get_iter_at_line
                get_line_yrange = self.textview[buf_index].get_line_yrange

                def coords_by_chunk():
                    y, h = get_line_yrange(get_end_iter())
                    max_y = float(y + h)
                    for c in self.linediffer.single_changes(i):
                        y0, _ = get_line_yrange(get_iter_at_line(c[1]))
                        if c[1] == c[2]:
                            y, h = y0, 0
                        else:
                            y, h = get_line_yrange(get_iter_at_line(c[2] - 1))
                        yield c[0], y0 / max_y, (y + h) / max_y
                return coords_by_chunk

            for (w, i) in zip(self.diffmap, (0, self.num_panes - 1)):
                scroll = self.scrolledwindow[i].get_vscrollbar()
                w.setup(scroll, coords_iter(i))

            for (w, i) in zip(self.linkmap, (0, self.num_panes - 2)):
                w.associate(self, self.textview[i], self.textview[i + 1])

            for i in range(self.num_panes):
                self.file_save_button[i].set_sensitive(
                    self.textbuffer[i].get_modified())
            self.queue_draw()
            self.recompute_label()

    def copy_chunk(self, src, dst, chunk, copy_up):
        b0, b1 = self.textbuffer[src], self.textbuffer[dst]
        start = b0.get_iter_at_line_or_eof(chunk[1])
        end = b0.get_iter_at_line_or_eof(chunk[2])
        t0 = text_type(b0.get_text(start, end, False), 'utf8')

        if copy_up:
            if chunk[2] >= b0.get_line_count() and \
               chunk[3] < b1.get_line_count():
                # TODO: We need to insert a linebreak here, but there is no
                # way to be certain what kind of linebreak to use.
                t0 = t0 + "\n"
            dst_start = b1.get_iter_at_line_or_eof(chunk[3])
            mark0 = b1.create_mark(None, dst_start, True)
            new_end = b1.insert_at_line(chunk[3], t0)
        else:
            dst_start = b1.get_iter_at_line_or_eof(chunk[4])
            mark0 = b1.create_mark(None, dst_start, True)
            new_end = b1.insert_at_line(chunk[4], t0)

        mark1 = b1.create_mark(None, new_end, True)
        # FIXME: If the inserted chunk ends up being an insert chunk, then
        # this animation is not visible; this happens often in three-way diffs
        self.textview[dst].add_fading_highlight(mark0, mark1, 'insert', 500000)

    def replace_chunk(self, src, dst, chunk):
        b0, b1 = self.textbuffer[src], self.textbuffer[dst]
        src_start = b0.get_iter_at_line_or_eof(chunk[1])
        src_end = b0.get_iter_at_line_or_eof(chunk[2])
        dst_start = b1.get_iter_at_line_or_eof(chunk[3])
        dst_end = b1.get_iter_at_line_or_eof(chunk[4])
        t0 = text_type(b0.get_text(src_start, src_end, False), 'utf8')
        mark0 = b1.create_mark(None, dst_start, True)
        self.textbuffer[dst].begin_user_action()
        b1.delete(dst_start, dst_end)
        new_end = b1.insert_at_line(chunk[3], t0)
        self.textbuffer[dst].end_user_action()
        mark1 = b1.create_mark(None, new_end, True)
        if chunk[1] == chunk[2]:
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
        it = b0.get_iter_at_line_or_eof(chunk[1])
        if chunk[2] >= b0.get_line_count():
            it.backward_char()
        b0.delete(it, b0.get_iter_at_line_or_eof(chunk[2]))
        mark0 = b0.create_mark(None, it, True)
        mark1 = b0.create_mark(None, it, True)
        # TODO: Need a more specific colour here; conflict is wrong
        self.textview[src].add_fading_highlight(
            mark0, mark1, 'conflict', 500000)

    @with_focused_pane
    def add_sync_point(self, pane, action):
        # Find a non-complete syncpoint, or create a new one
        if self.syncpoints and None in self.syncpoints[-1]:
            syncpoint = self.syncpoints.pop()
        else:
            syncpoint = [None] * self.num_panes
        cursor_it = self.textbuffer[pane].get_iter_at_mark(
            self.textbuffer[pane].get_insert())
        syncpoint[pane] = self.textbuffer[pane].create_mark(None, cursor_it)
        self.syncpoints.append(syncpoint)

        for i, t in enumerate(self.textview[:self.num_panes]):
            t.syncpoints = [p[i] for p in self.syncpoints if p[i] is not None]

        def make_line_retriever(pane, marks):
            buf = self.textbuffer[pane]
            mark = marks[pane]

            def get_line_for_mark():
                return buf.get_iter_at_mark(mark).get_line()
            return get_line_for_mark

        valid_points = [p for p in self.syncpoints if all(p)]
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

        if valid_points:
            for mgr in self.msgarea_mgr:
                msgarea = mgr.new_from_text_and_icon(
                    'dialog-information-symbolic',
                    _("Live comparison updating disabled"),
                    _("Live updating of comparisons is disabled when "
                      "synchronization points are active. You can still "
                      "manually refresh the comparison, and live updates will "
                      "resume when synchronization points are cleared."))
                mgr.set_msg_id(FileDiff.MSG_SYNCPOINTS)
                msgarea.show_all()

        self.refresh_comparison()

    def clear_sync_points(self, action):
        self.syncpoints = []
        self.linediffer.syncpoints = []
        for t in self.textview:
            t.syncpoints = []
        for mgr in self.msgarea_mgr:
            if mgr.get_msg_id() == FileDiff.MSG_SYNCPOINTS:
                mgr.clear()
        self.refresh_comparison()
