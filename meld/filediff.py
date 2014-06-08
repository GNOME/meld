### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2009-2012 Kai Willadsen <kai.willadsen@gmail.com>

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

import copy
import functools
import io
import os
from gettext import gettext as _
import time

from multiprocessing import Pool
from multiprocessing.pool import ThreadPool


import pango
import glib
import gobject
import gtk
import gtk.keysyms

from . import diffutil
from . import matchers
from . import meldbuffer
from . import melddoc
from . import merge
from . import misc
from . import patchdialog
from . import paths
from . import recent
from . import undo
from .ui import findbar
from .ui import gnomeglade

from .meldapp import app
from .util.compat import text_type
from .util.sourceviewer import srcviewer


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
                # maxtasksperchild is new in Python 2.7; this is for 2.6 compat
                try:
                    CachedSequenceMatcher.process_pool = Pool(
                        None, matchers.init_worker, maxtasksperchild=1)
                except TypeError:
                    CachedSequenceMatcher.process_pool = Pool(
                        None, matchers.init_worker)
        self.cache = {}

    def match(self, text1, textn, cb):
        try:
            self.cache[(text1, textn)][1] = time.time()
            cb(self.cache[(text1, textn)][0])
        except KeyError:
            def inline_cb(opcodes):
                self.cache[(text1, textn)] = [opcodes, time.time()]
                gobject.idle_add(lambda: cb(opcodes))
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
MODE_REPLACE, MODE_DELETE, MODE_INSERT = 0, 1, 2


class CursorDetails(object):
    __slots__ = ("pane", "pos", "line", "offset", "chunk", "prev", "next",
                 "prev_conflict", "next_conflict")

    def __init__(self):
        for var in self.__slots__:
            setattr(self, var, None)


class TaskEntry(object):
    __slots__ = ("filename", "file", "buf", "codec", "pane", "was_cr")

    def __init__(self, *args):
        for var, val in zip(self.__slots__, args):
            setattr(self, var, val)


class TextviewLineAnimation(object):
    __slots__ = ("start_mark", "end_mark", "start_rgba", "end_rgba",
                 "start_time", "duration")

    def __init__(self, mark0, mark1, rgba0, rgba1, duration):
        self.start_mark = mark0
        self.end_mark = mark1
        self.start_rgba = rgba0
        self.end_rgba = rgba1
        self.start_time = glib.get_current_time()
        self.duration = duration


class FileDiff(melddoc.MeldDoc, gnomeglade.Component):
    """Two or three way diff of text files.
    """

    differ = diffutil.Differ

    keylookup = {gtk.keysyms.Shift_L : MASK_SHIFT,
                 gtk.keysyms.Control_L : MASK_CTRL,
                 gtk.keysyms.Shift_R : MASK_SHIFT,
                 gtk.keysyms.Control_R : MASK_CTRL}

    # Identifiers for MsgArea messages
    (MSG_SAME, MSG_SLOW_HIGHLIGHT, MSG_SYNCPOINTS) = list(range(3))

    __gsignals__ = {
        'next-conflict-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (bool, bool)),
        'action-mode-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (int,)),
    }

    def __init__(self, prefs, num_panes):
        """Start up an filediff with num_panes empty contents.
        """
        melddoc.MeldDoc.__init__(self, prefs)
        gnomeglade.Component.__init__(self, paths.ui_dir("filediff.ui"), "filediff")
        self.map_widgets_into_lists(["textview", "fileentry", "diffmap",
                                     "scrolledwindow", "linkmap",
                                     "statusimage", "msgarea_mgr", "vbox",
                                     "selector_hbox", "readonlytoggle"])

        # This SizeGroup isn't actually necessary for FileDiff; it's for
        # handling non-homogenous selectors in FileComp. It's also fragile.
        column_sizes = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)
        column_sizes.set_ignore_hidden(True)
        for widget in self.selector_hbox:
            column_sizes.add_widget(widget)

        self.warned_bad_comparison = False
        # Some sourceviews bind their own undo mechanism, which we replace
        gtk.binding_entry_remove(srcviewer.GtkTextView, gtk.keysyms.z,
                                 gtk.gdk.CONTROL_MASK)
        gtk.binding_entry_remove(srcviewer.GtkTextView, gtk.keysyms.z,
                                 gtk.gdk.CONTROL_MASK | gtk.gdk.SHIFT_MASK)
        for v in self.textview:
            v.set_buffer(meldbuffer.MeldBuffer())
            v.set_show_line_numbers(self.prefs.show_line_numbers)
            v.set_insert_spaces_instead_of_tabs(self.prefs.spaces_instead_of_tabs)
            v.set_wrap_mode(self.prefs.edit_wrap_lines)
            if self.prefs.show_whitespace:
                v.set_draw_spaces(srcviewer.spaces_flag)
            srcviewer.set_tab_width(v, self.prefs.tab_size)
        self._keymask = 0
        self.load_font()
        self.deleted_lines_pending = -1
        self.textview_overwrite = 0
        self.focus_pane = None
        self.textview_overwrite_handlers = [ t.connect("toggle-overwrite", self.on_textview_toggle_overwrite) for t in self.textview ]
        self.textbuffer = [v.get_buffer() for v in self.textview]
        self.buffer_texts = [meldbuffer.BufferLines(b) for b in self.textbuffer]
        self.undosequence = undo.UndoSequence()
        self.text_filters = []
        self.create_text_filters()
        self.app_handlers = [app.connect("text-filters-changed",
                             self.on_text_filters_changed)]
        self.buffer_filtered = [meldbuffer.BufferLines(b, self._filter_text)
                                for b in self.textbuffer]
        for (i, w) in enumerate(self.scrolledwindow):
            w.get_vadjustment().connect("value-changed", self._sync_vscroll, i)
            w.get_hadjustment().connect("value-changed", self._sync_hscroll)
        self._connect_buffer_handlers()
        self._sync_vscroll_lock = False
        self._sync_hscroll_lock = False
        self._scroll_lock = False
        self.linediffer = self.differ()
        self.linediffer.ignore_blanks = self.prefs.ignore_blank_lines
        self.force_highlight = False
        self.syncpoints = []
        self.in_nested_textview_gutter_expose = False
        self._cached_match = CachedSequenceMatcher()
        self.anim_source_id = [None for buf in self.textbuffer]
        self.animating_chunks = [[] for buf in self.textbuffer]
        for buf in self.textbuffer:
            buf.create_tag("inline")
            buf.connect("notify::has-selection",
                        self.update_text_actions_sensitivity)

        actions = (
            ("MakePatch", None, _("Format as Patch..."), None,
                _("Create a patch using differences between files"),
                self.make_patch),
            ("SaveAll", None, _("Save A_ll"), "<Ctrl><Shift>L",
                _("Save all files in the current comparison"),
                self.on_save_all_activate),
            ("Revert", gtk.STOCK_REVERT_TO_SAVED, None, None,
                _("Revert files to their saved versions"),
                self.on_revert_activate),
            ("SplitAdd", None, _("Add Synchronization Point"), None,
                _("Add a manual point for synchronization of changes between "
                  "files"),
                self.add_sync_point),
            ("SplitClear", None, _("Clear Synchronization Points"), None,
                _("Clear manual change sychronization points"),
                self.clear_sync_points),
            ("PrevConflict", None, _("Previous Conflict"), "<Ctrl>I",
                _("Go to the previous conflict"),
                lambda x: self.on_next_conflict(gtk.gdk.SCROLL_UP)),
            ("NextConflict", None, _("Next Conflict"), "<Ctrl>K",
                _("Go to the next conflict"),
                lambda x: self.on_next_conflict(gtk.gdk.SCROLL_DOWN)),
            ("PushLeft", gtk.STOCK_GO_BACK, _("Push to Left"), "<Alt>Left",
                _("Push current change to the left"),
                lambda x: self.push_change(-1)),
            ("PushRight", gtk.STOCK_GO_FORWARD,
                _("Push to Right"), "<Alt>Right",
                _("Push current change to the right"),
                lambda x: self.push_change(1)),
            # FIXME: using LAST and FIRST is terrible and unreliable icon abuse
            ("PullLeft", gtk.STOCK_GOTO_LAST,
                _("Pull from Left"), "<Alt><Shift>Right",
                _("Pull change from the left"),
                lambda x: self.pull_change(-1)),
            ("PullRight", gtk.STOCK_GOTO_FIRST,
                _("Pull from Right"), "<Alt><Shift>Left",
                _("Pull change from the right"),
                lambda x: self.pull_change(1)),
            ("CopyLeftUp", None, _("Copy Above Left"), "<Alt>bracketleft",
                _("Copy change above the left chunk"),
                lambda x: self.copy_change(-1, -1)),
            ("CopyLeftDown", None, _("Copy Below Left"), "<Alt>semicolon",
                _("Copy change below the left chunk"),
                lambda x: self.copy_change(-1, 1)),
            ("CopyRightUp", None, _("Copy Above Right"), "<Alt>bracketright",
                _("Copy change above the right chunk"),
                lambda x: self.copy_change(1, -1)),
            ("CopyRightDown", None, _("Copy Below Right"), "<Alt>quoteright",
                _("Copy change below the right chunk"),
                lambda x: self.copy_change(1, 1)),
            ("Delete", gtk.STOCK_DELETE, _("Delete"), "<Alt>Delete",
                _("Delete change"),
                self.delete_change),
            ("MergeFromLeft", None, _("Merge All from Left"), None,
                _("Merge all non-conflicting changes from the left"),
                lambda x: self.pull_all_non_conflicting_changes(-1)),
            ("MergeFromRight", None, _("Merge All from Right"), None,
                _("Merge all non-conflicting changes from the right"),
                lambda x: self.pull_all_non_conflicting_changes(1)),
            ("MergeAll", None, _("Merge All"), None,
                _("Merge all non-conflicting changes from left and right "
                  "panes"),
                lambda x: self.merge_all_non_conflicting_changes()),
            ("CycleDocuments", None,
                _("Cycle Through Documents"), "<control>Escape",
                _("Move keyboard focus to the next document in this "
                  "comparison"),
                self.action_cycle_documents),
        )

        toggle_actions = (
            ("LockScrolling", None, _("Lock Scrolling"), None,
             _("Lock scrolling of all panes"),
             self.on_action_lock_scrolling_toggled, True),
        )

        self.ui_file = paths.ui_dir("filediff-ui.xml")
        self.actiongroup = gtk.ActionGroup('FilediffPopupActions')
        self.actiongroup.set_translation_domain("meld")
        self.actiongroup.add_actions(actions)
        self.actiongroup.add_toggle_actions(toggle_actions)
        self.main_actiongroup = None

        self.findbar = findbar.FindBar(self.table)

        self.widget.ensure_style()
        self.on_style_set(self.widget, None)
        self.widget.connect("style-set", self.on_style_set)

        self.set_num_panes(num_panes)
        gobject.idle_add( lambda *args: self.load_font()) # hack around Bug 316730
        gnomeglade.connect_signal_handlers(self)
        self.cursor = CursorDetails()
        self.connect("current-diff-changed", self.on_current_diff_changed)
        for t in self.textview:
            t.connect("focus-in-event", self.on_current_diff_changed)
            t.connect("focus-out-event", self.on_current_diff_changed)
        self.linediffer.connect("diffs-changed", self.on_diffs_changed)
        self.undosequence.connect("checkpointed", self.on_undo_checkpointed)
        self.connect("next-conflict-changed", self.on_next_conflict_changed)

        overwrite_label = gtk.Label()
        overwrite_label.show()
        cursor_label = gtk.Label()
        cursor_label.show()
        self.status_info_labels = [overwrite_label, cursor_label]

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

    def on_style_set(self, widget, prev_style):
        style = widget.get_style()

        lookup = lambda color_id, default: style.lookup_color(color_id) or \
                                           gtk.gdk.color_parse(default)

        for buf in self.textbuffer:
            tag = buf.get_tag_table().lookup("inline")
            tag.props.background = lookup("inline-bg", "LightSteelBlue2")
            tag.props.foreground = lookup("inline-fg", "Red")

        self.fill_colors = {"insert"  : lookup("insert-bg", "DarkSeaGreen1"),
                            "delete"  : lookup("insert-bg", "DarkSeaGreen1"),
                            "conflict": lookup("conflict-bg", "Pink"),
                            "replace" : lookup("replace-bg", "#ddeeff"),
                            "current-chunk-highlight":
                                lookup("current-chunk-highlight", '#ffffff')}
        self.line_colors = {"insert"  : lookup("insert-outline", "#77f077"),
                            "delete"  : lookup("insert-outline", "#77f077"),
                            "conflict": lookup("conflict-outline", "#f0768b"),
                            "replace" : lookup("replace-outline", "#8bbff3")}
        self.highlight_color = lookup("current-line-highlight", "#ffff00")
        self.syncpoint_color = lookup("syncpoint-outline", "#555555")

        for associated in self.diffmap + self.linkmap:
            associated.set_color_scheme([self.fill_colors, self.line_colors])

        self.queue_draw()

    def on_focus_change(self):
        self.keymask = 0

    def on_container_switch_in_event(self, ui):
        self.main_actiongroup = [a for a in ui.get_action_groups()
                                 if a.get_name() == "MainActions"][0]
        melddoc.MeldDoc.on_container_switch_in_event(self, ui)
        # FIXME: If no focussed textview, action sensitivity will be unset

    def on_text_filters_changed(self, app):
        relevant_change = self.create_text_filters()
        if relevant_change:
            self.refresh_comparison()

    def create_text_filters(self):
        # In contrast to file filters, ordering of text filters can matter
        old_active = [f.filter_string for f in self.text_filters if f.active]
        new_active = [f.filter_string for f in app.text_filters if f.active]
        active_filters_changed = old_active != new_active

        self.text_filters = [copy.copy(f) for f in app.text_filters]

        return active_filters_changed

    def _disconnect_buffer_handlers(self):
        for textview in self.textview:
            textview.set_editable(0)
        for buf in self.textbuffer:
            assert hasattr(buf,"handlers")
            for h in buf.handlers:
                buf.disconnect(h)

    def _connect_buffer_handlers(self):
        for textview, buf in zip(self.textview, self.textbuffer):
            textview.set_editable(buf.data.editable)
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
                push_left = editable_left and not insert_chunk
                push_right = editable_right and not insert_chunk
                pull_left = pane == 2 and editable and not delete_chunk
                pull_right = pane == 0 and editable and not delete_chunk
                delete = editable and not insert_chunk
                copy_left = push_left and not delete_chunk
                copy_right = push_right and not delete_chunk
            elif pane == 1:
                chunk0 = self.linediffer.get_chunk(chunk_id, 1, 0)
                chunk2 = None
                if self.num_panes == 3:
                    chunk2 = self.linediffer.get_chunk(chunk_id, 1, 2)
                left_mid_exists = chunk0 is not None and chunk0[1] != chunk0[2]
                left_exists = chunk0 is not None and chunk0[3] != chunk0[4]
                right_mid_exists = chunk2 is not None and chunk2[1] != chunk2[2]
                right_exists = chunk2 is not None and chunk2[3] != chunk2[4]
                push_left = editable_left and left_mid_exists
                push_right = editable_right and right_mid_exists
                pull_left = editable and left_exists
                pull_right = editable and right_exists
                delete = editable and (left_mid_exists or right_mid_exists)
                copy_left = push_left and left_exists
                copy_right = push_right and right_exists
        self.actiongroup.get_action("PushLeft").set_sensitive(push_left)
        self.actiongroup.get_action("PushRight").set_sensitive(push_right)
        self.actiongroup.get_action("PullLeft").set_sensitive(pull_left)
        self.actiongroup.get_action("PullRight").set_sensitive(pull_right)
        self.actiongroup.get_action("Delete").set_sensitive(delete)
        self.actiongroup.get_action("CopyLeftUp").set_sensitive(copy_left)
        self.actiongroup.get_action("CopyLeftDown").set_sensitive(copy_left)
        self.actiongroup.get_action("CopyRightUp").set_sensitive(copy_right)
        self.actiongroup.get_action("CopyRightDown").set_sensitive(copy_right)
        # FIXME: don't queue_draw() on everything... just on what changed
        self.queue_draw()

    def on_next_conflict_changed(self, doc, have_prev, have_next):
        self.actiongroup.get_action("PrevConflict").set_sensitive(have_prev)
        self.actiongroup.get_action("NextConflict").set_sensitive(have_next)

    def on_next_conflict(self, direction):
        if direction == gtk.gdk.SCROLL_DOWN:
            target = self.cursor.next_conflict
        else: # direction == gtk.gdk.SCROLL_UP
            target = self.cursor.prev_conflict

        if target is None:
            return

        buf = self.textbuffer[self.cursor.pane]
        chunk = self.linediffer.get_chunk(target, self.cursor.pane)
        buf.place_cursor(buf.get_iter_at_line(chunk[1]))
        self.textview[self.cursor.pane].scroll_to_mark(buf.get_insert(), 0.1)

    def push_change(self, direction):
        src = self._get_focused_pane()
        dst = src + direction
        chunk = self.linediffer.get_chunk(self.cursor.chunk, src, dst)
        assert(src != -1 and self.cursor.chunk is not None)
        assert(dst in (0, 1, 2))
        assert(chunk is not None)
        self.replace_chunk(src, dst, chunk)

    def pull_change(self, direction):
        dst = self._get_focused_pane()
        src = dst + direction
        chunk = self.linediffer.get_chunk(self.cursor.chunk, src, dst)
        assert(dst != -1 and self.cursor.chunk is not None)
        assert(src in (0, 1, 2))
        assert(chunk is not None)
        self.replace_chunk(src, dst, chunk)

    def copy_change(self, direction, copy_direction):
        src = self._get_focused_pane()
        dst = src + direction
        chunk = self.linediffer.get_chunk(self.cursor.chunk, src, dst)
        assert(src != -1 and self.cursor.chunk is not None)
        assert(dst in (0, 1, 2))
        assert(chunk is not None)
        copy_up = True if copy_direction < 0 else False
        self.copy_chunk(src, dst, chunk, copy_up)

    def pull_all_non_conflicting_changes(self, direction):
        assert direction in (-1, 1)
        dst = self._get_focused_pane()
        src = dst + direction
        assert src in range(self.num_panes)
        merger = merge.Merger()
        merger.differ = self.linediffer
        merger.texts = self.buffer_texts
        for mergedfile in merger.merge_2_files(src, dst):
            pass
        self._sync_vscroll_lock = True
        self.on_textbuffer__begin_user_action()
        self.textbuffer[dst].set_text(mergedfile)
        self.on_textbuffer__end_user_action()
        def resync():
            self._sync_vscroll_lock = False
            self._sync_vscroll(self.scrolledwindow[src].get_vadjustment(), src)
        self.scheduler.add_task(resync)

    def merge_all_non_conflicting_changes(self):
        dst = 1
        merger = merge.Merger()
        merger.differ = self.linediffer
        merger.texts = self.buffer_texts
        for mergedfile in merger.merge_3_files(False):
            pass
        self._sync_vscroll_lock = True
        self.on_textbuffer__begin_user_action()
        self.textbuffer[dst].set_text(mergedfile)
        self.on_textbuffer__end_user_action()
        def resync():
            self._sync_vscroll_lock = False
            self._sync_vscroll(self.scrolledwindow[0].get_vadjustment(), 0)
        self.scheduler.add_task(resync)

    def delete_change(self, widget):
        pane = self._get_focused_pane()
        chunk = self.linediffer.get_chunk(self.cursor.chunk, pane)
        assert(pane != -1 and self.cursor.chunk is not None)
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

    def action_cycle_documents(self, widget):
        pane = self._get_focused_pane()
        new_pane = (pane + 1) % self.num_panes
        chunk, line = self.cursor.chunk, self.cursor.line

        new_line = self._corresponding_chunk_line(chunk, line, pane, new_pane)

        new_buf = self.textbuffer[new_pane]
        self.textview[new_pane].grab_focus()
        new_buf.place_cursor(new_buf.get_iter_at_line(new_line))
        self.textview[new_pane].scroll_to_mark(new_buf.get_insert(), 0.1)

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

    def _filter_text(self, txt):
        def killit(m):
            assert m.group().count("\n") == 0
            if len(m.groups()):
                s = m.group()
                for g in m.groups():
                    if g:
                        s = s.replace(g,"")
                return s
            else:
                return ""
        try:
            for filt in self.text_filters:
                if filt.active:
                    txt = filt.filter.sub(killit, txt)
        except AssertionError:
            if not self.warned_bad_comparison:
                misc.run_dialog(_("Filter '%s' changed the number of lines in the file. "
                    "Comparison will be incorrect. See the user manual for more details.") % filt.label)
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

    def load_font(self):
        fontdesc = pango.FontDescription(self.prefs.get_current_font())
        context = self.textview0.get_pango_context()
        metrics = context.get_metrics( fontdesc, context.get_language() )
        line_height_points = metrics.get_ascent() + metrics.get_descent()
        self.pixels_per_line = line_height_points // 1024
        self.pango_char_width = metrics.get_approximate_char_width()
        tabs = pango.TabArray(10, 0)
        tab_size = self.prefs.tab_size
        for i in range(10):
            tabs.set_tab(i, pango.TAB_LEFT, i*tab_size*self.pango_char_width)
        for i in range(3):
            self.textview[i].modify_font(fontdesc)
            self.textview[i].set_tabs(tabs)
        for i in range(2):
            self.linkmap[i].queue_draw()

    def on_preference_changed(self, key, value):
        if key == "tab_size":
            tabs = pango.TabArray(10, 0)
            for i in range(10):
                tabs.set_tab(i, pango.TAB_LEFT, i*value*self.pango_char_width)
            for i in range(3):
                self.textview[i].set_tabs(tabs)
            for t in self.textview:
                srcviewer.set_tab_width(t, value)
        elif key == "use_custom_font" or key == "custom_font":
            self.load_font()
        elif key == "show_line_numbers":
            for t in self.textview:
                t.set_show_line_numbers( value )
        elif key == "show_whitespace":
            spaces_flag = srcviewer.spaces_flag if value else 0
            for v in self.textview:
                v.set_draw_spaces(spaces_flag)
        elif key == "use_syntax_highlighting":
            for i in range(self.num_panes):
                srcviewer.set_highlight_syntax(self.textbuffer[i], value)
        elif key == "edit_wrap_lines":
            for t in self.textview:
                t.set_wrap_mode(self.prefs.edit_wrap_lines)
            # FIXME: On changing wrap mode, we get one redraw using cached
            # coordinates, followed by a second redraw (e.g., on refocus) with
            # correct coordinates. Overly-aggressive textview lazy calculation?
            self.diffmap0.queue_draw()
            self.diffmap1.queue_draw()
        elif key == "spaces_instead_of_tabs":
            for t in self.textview:
                t.set_insert_spaces_instead_of_tabs(value)
        elif key == "ignore_blank_lines":
            self.linediffer.ignore_blanks = self.prefs.ignore_blank_lines
            self.refresh_comparison()

    def on_key_press_event(self, object, event):
        # The correct way to handle these modifiers would be to use
        # gdk_keymap_get_modifier_state method, available from GDK 3.4.
        keymap = gtk.gdk.keymap_get_default()
        x = self.keylookup.get(keymap.translate_keyboard_state(
                               event.hardware_keycode, 0, event.group)[0], 0)
        if self.keymask | x != self.keymask:
            self.keymask |= x
        elif event.keyval == gtk.keysyms.Escape:
            self.findbar.hide()

    def on_key_release_event(self, object, event):
        keymap = gtk.gdk.keymap_get_default()
        x = self.keylookup.get(keymap.translate_keyboard_state(
                               event.hardware_keycode, 0, event.group)[0], 0)
        if self.keymask & ~x != self.keymask:
            self.keymask &= ~x

    def check_save_modified(self, label=None):
        response = gtk.RESPONSE_OK
        modified = [b.data.modified for b in self.textbuffer]
        if True in modified:
            ui_path = paths.ui_dir("filediff.ui")
            dialog = gnomeglade.Component(ui_path, "check_save_dialog")
            dialog.widget.set_transient_for(self.widget.get_toplevel())
            if label:
                dialog.widget.props.text = label
            # FIXME: Should be packed into dialog.widget.get_message_area(),
            # but this is unbound on currently required PyGTK.
            buttons = []
            for i in range(self.num_panes):
                button = gtk.CheckButton(self.textbuffer[i].data.label)
                button.set_use_underline(False)
                button.set_sensitive(modified[i])
                button.set_active(modified[i])
                dialog.extra_vbox.pack_start(button, expand=True, fill=True)
                buttons.append(button)
            dialog.extra_vbox.show_all()
            response = dialog.widget.run()
            try_save = [b.get_active() for b in buttons]
            dialog.widget.destroy()
            if response == gtk.RESPONSE_OK:
                for i in range(self.num_panes):
                    if try_save[i]:
                        if not self.save_file(i):
                            return gtk.RESPONSE_CANCEL
            elif response == gtk.RESPONSE_DELETE_EVENT:
                response = gtk.RESPONSE_CANCEL
        return response

    def on_delete_event(self, appquit=0):
        response = self.check_save_modified()
        if response == gtk.RESPONSE_OK:
            for h in self.app_handlers:
                app.disconnect(h)
        return response

        #
        # text buffer undo/redo
        #

    def on_undo_activate(self):
        if self.undosequence.can_undo():
            self.undosequence.undo()

    def on_redo_activate(self):
        if self.undosequence.can_redo():
            self.undosequence.redo()

    def on_textbuffer__begin_user_action(self, *buffer):
        self.undosequence.begin_group()

    def on_textbuffer__end_user_action(self, *buffer):
        self.undosequence.end_group()

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
        self.set_buffer_modified(buf, not checkpointed)

        #
        #
        #

    def open_external(self):
        pane = self._get_focused_pane()
        if pane >= 0:
            if self.textbuffer[pane].data.filename:
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
            #    gtk.gdk.SELECTION_CLIPBOARD).wait_is_text_available()
            paste = widget.get_editable()
        if self.main_actiongroup:
            for action, sens in zip(
                    ("Cut", "Copy", "Paste"), (cut, copy, paste)):
                self.main_actiongroup.get_action(action).set_sensitive(sens)

    def get_selected_text(self):
        """Returns selected text of active pane"""
        pane = self._get_focused_pane()
        if pane != -1:
            buf = self.textbuffer[pane]
            sel = buf.get_selection_bounds()
            if sel:
                return text_type(buf.get_text(sel[0], sel[1], False), 'utf8')
        return None

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

    def on_filediff__key_press_event(self, entry, event):
        if event.keyval == gtk.keysyms.Escape:
            self.findbar.hide()

    def on_scrolledwindow__size_allocate(self, scrolledwindow, allocation):
        index = self.scrolledwindow.index(scrolledwindow)
        if index == 0 or index == 1:
            self.linkmap[0].queue_draw()
        if index == 1 or index == 2:
            self.linkmap[1].queue_draw()

    def on_textview_popup_menu(self, textview):
        self.popup_menu.popup(None, None, None, 0,
                              gtk.get_current_event_time())
        return True

    def on_textview_button_press_event(self, textview, event):
        if event.button == 3:
            textview.grab_focus()
            self.popup_menu.popup(None, None, None, event.button, event.time)
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


        #
        # text buffer loading/saving
        #

    def set_labels(self, labels):
        labels = labels[:len(self.textbuffer)]
        for label, buf in zip(labels, self.textbuffer):
            if label:
                buf.data.label = label

    def set_merge_output_file(self, filename):
        if len(self.textbuffer) < 2:
            return
        buf = self.textbuffer[1]
        buf.data.savefile = os.path.abspath(filename)
        buf.data.set_label(filename)
        self.set_buffer_writable(buf, os.access(buf.data.savefile, os.W_OK))
        self.fileentry[1].set_filename(os.path.abspath(filename))
        self.recompute_label()

    def _set_save_action_sensitivity(self):
        pane = self._get_focused_pane()
        modified = False if pane == -1 else self.textbuffer[pane].data.modified
        if self.main_actiongroup:
            self.main_actiongroup.get_action("Save").set_sensitive(modified)
        any_modified = any(b.data.modified for b in self.textbuffer)
        self.actiongroup.get_action("SaveAll").set_sensitive(any_modified)

    def recompute_label(self):
        self._set_save_action_sensitivity()
        filenames = []
        for i in range(self.num_panes):
            filenames.append(self.textbuffer[i].data.label)
        shortnames = misc.shorten_names(*filenames)
        for i in range(self.num_panes):
            stock = None
            if self.textbuffer[i].data.modified:
                shortnames[i] += "*"
                if self.textbuffer[i].data.writable:
                    stock = gtk.STOCK_SAVE
                else:
                    stock = gtk.STOCK_SAVE_AS
            if stock:
                self.statusimage[i].show()
                self.statusimage[i].set_from_stock(stock, gtk.ICON_SIZE_MENU)
                self.statusimage[i].set_size_request(self.diffmap[0].size_request()[0],-1)
            else:
                self.statusimage[i].hide()
        self.label_text = " : ".join(shortnames)
        self.tooltip_text = self.label_text
        self.label_changed()

    def set_files(self, files):
        """Set num panes to len(files) and load each file given.
           If an element is None, the text of a pane is left as is.
        """
        self._disconnect_buffer_handlers()
        files = list(files)
        for i, f in enumerate(files):
            if not f:
                continue
            if not isinstance(f, unicode):
                files[i] = f = f.decode('utf8')
            absfile = os.path.abspath(f)
            self.fileentry[i].set_filename(absfile)
            self.fileentry[i].prepend_history(absfile)
            self.textbuffer[i].reset_buffer(absfile)
            self.msgarea_mgr[i].clear()

        self.recompute_label()
        self.textview[len(files) >= 2].grab_focus()
        self._connect_buffer_handlers()
        self.scheduler.add_task(self._set_files_internal(files))

    def get_comparison(self):
        files = [b.data.filename for b in self.textbuffer[:self.num_panes]]
        return recent.TYPE_FILE, files

    def _load_files(self, files, textbuffers):
        self.undosequence.clear()
        yield _("[%s] Set num panes") % self.label_text
        self.set_num_panes( len(files) )
        self._disconnect_buffer_handlers()
        self.linediffer.clear()
        self.queue_draw()
        try_codecs = self.prefs.text_codecs.split() or ['utf_8', 'utf_16']
        yield _("[%s] Opening files") % self.label_text
        tasks = []

        def add_dismissable_msg(pane, icon, primary, secondary):
            msgarea = self.msgarea_mgr[pane].new_from_text_and_icon(
                            icon, primary, secondary)
            button = msgarea.add_stock_button_with_text(_("Hi_de"),
                            gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
            msgarea.connect("response",
                            lambda *args: self.msgarea_mgr[pane].clear())
            msgarea.show_all()
            return msgarea

        for pane, filename in enumerate(files):
            buf = textbuffers[pane]
            if filename:
                try:
                    handle = io.open(filename, "r", encoding=try_codecs[0])
                    task = TaskEntry(filename, handle, buf, try_codecs[:],
                                     pane, False)
                    tasks.append(task)
                except (IOError, LookupError) as e:
                    buf.delete(*buf.get_bounds())
                    add_dismissable_msg(pane, gtk.STOCK_DIALOG_ERROR,
                                        _("Could not read file"), str(e))
        yield _("[%s] Reading files") % self.label_text
        while len(tasks):
            for t in tasks[:]:
                try:
                    nextbit = t.file.read(4096)
                    if nextbit.find("\x00") != -1:
                        t.buf.delete(*t.buf.get_bounds())
                        filename = gobject.markup_escape_text(t.filename)
                        add_dismissable_msg(t.pane, gtk.STOCK_DIALOG_ERROR,
                            _("Could not read file"),
                            _("%s appears to be a binary file.") % filename)
                        tasks.remove(t)
                        continue
                except ValueError as err:
                    t.codec.pop(0)
                    if len(t.codec):
                        t.buf.delete(*t.buf.get_bounds())
                        t.file = io.open(t.filename, "r", encoding=t.codec[0])
                    else:
                        t.buf.delete(*t.buf.get_bounds())
                        filename = gobject.markup_escape_text(t.filename)
                        add_dismissable_msg(t.pane, gtk.STOCK_DIALOG_ERROR,
                                        _("Could not read file"),
                                        _("%s is not in encodings: %s") %
                                            (filename, try_codecs))
                        tasks.remove(t)
                except IOError as ioerr:
                    add_dismissable_msg(t.pane, gtk.STOCK_DIALOG_ERROR,
                                    _("Could not read file"), str(ioerr))
                    tasks.remove(t)
                else:
                    # The handling here avoids inserting split CR/LF pairs into
                    # GtkTextBuffers; this is relevant only when universal
                    # newline support is unavailable or broken.
                    if t.was_cr:
                        nextbit = "\r" + nextbit
                        t.was_cr = False
                    if len(nextbit):
                        if nextbit[-1] == "\r" and len(nextbit) > 1:
                            t.was_cr = True
                            nextbit = nextbit[0:-1]
                        t.buf.insert(t.buf.get_end_iter(), nextbit)
                    else:
                        if t.buf.data.savefile:
                            writable = os.access(t.buf.data.savefile, os.W_OK)
                        else:
                            writable = os.access(t.filename, os.W_OK)
                        self.set_buffer_writable(t.buf, writable)
                        t.buf.data.encoding = t.codec[0]
                        if hasattr(t.file, "newlines"):
                            t.buf.data.newlines = t.file.newlines
                        tasks.remove(t)
            yield 1
        for b in self.textbuffer:
            self.undosequence.checkpoint(b)

    def _diff_files(self, refresh=False):
        yield _("[%s] Computing differences") % self.label_text
        texts = self.buffer_filtered[:self.num_panes]
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
                    lambda: self.next_diff(gtk.gdk.SCROLL_DOWN, True), True)
            else:
                buf = self.textbuffer[1 if self.num_panes > 1 else 0]
                self.on_cursor_position_changed(buf, None, True)

        self.queue_draw()
        self._connect_buffer_handlers()
        self._set_merge_action_sensitivity()

        langs = []
        for i in range(self.num_panes):
            filename = self.textbuffer[i].data.filename
            if filename:
                langs.append(srcviewer.get_language_from_file(filename))
            else:
                langs.append(None)

        # If we have only one identified language then we assume that all of
        # the files are actually of that type.
        real_langs = [l for l in langs if l]
        if real_langs and real_langs.count(real_langs[0]) == len(real_langs):
            langs = (real_langs[0],) * len(langs)

        for i in range(self.num_panes):
            srcviewer.set_language(self.textbuffer[i], langs[i])
            srcviewer.set_highlight_syntax(self.textbuffer[i],
                                           self.prefs.use_syntax_highlighting)

    def _set_files_internal(self, files):
        for i in self._load_files(files, self.textbuffer):
            yield i
        for i in self._diff_files():
            yield i

    def refresh_comparison(self):
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

                def apply_highlight(bufs, tags, starts, ends, texts, matches):
                    starts = [bufs[0].get_iter_at_mark(starts[0]),
                              bufs[1].get_iter_at_mark(starts[1])]
                    ends = [bufs[0].get_iter_at_mark(ends[0]),
                            bufs[1].get_iter_at_mark(ends[1])]
                    text1 = bufs[0].get_text(starts[0], ends[0], False)
                    text1 = text_type(text1, 'utf8')
                    textn = bufs[1].get_text(starts[1], ends[1], False)
                    textn = text_type(textn, 'utf8')

                    if texts != (text1, textn):
                        return

                    # Remove equal matches of size less than 3; highlight
                    # the remainder.
                    matches = [m for m in matches if m.tag != "equal" or
                               (m.end_a - m.start_a < 3) or
                               (m.end_b - m.start_b < 3)]

                    for i in range(2):
                        start, end = starts[i].copy(), starts[i].copy()
                        offset = start.get_offset()
                        for o in matches:
                            start.set_offset(offset + o[1 + 2 * i])
                            end.set_offset(offset + o[2 + 2 * i])
                            bufs[i].apply_tag(tags[i], start, end)

                if clear:
                    bufs[0].remove_tag(tags[0], starts[0], ends[0])
                    bufs[1].remove_tag(tags[1], starts[1], ends[1])

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
                secondary_text = None
                # TODO: Currently this only checks to see whether text filters
                # are active, and may be altering the comparison. It would be
                # better if we only showed this message if the filters *did*
                # change the text in question.
                active_filters = any([f.active for f in self.text_filters])
                if active_filters:
                    secondary_text = _("Text filters are being used, and may "
                                       "be masking differences between files. "
                                       "Would you like to compare the "
                                       "unfiltered files?")

                msgarea = mgr.new_from_text_and_icon(gtk.STOCK_INFO,
                                                     _("Files are identical"),
                                                     secondary_text)
                mgr.set_msg_id(FileDiff.MSG_SAME)
                button = msgarea.add_stock_button_with_text(_("Hide"),
                                                            gtk.STOCK_CLOSE,
                                                            gtk.RESPONSE_CLOSE)
                if index == 0:
                    button.props.label = _("Hi_de")

                if active_filters:
                    msgarea.add_button(_("Show without filters"),
                                       gtk.RESPONSE_OK)

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
            if respid == gtk.RESPONSE_OK:
                self.force_highlight = True
                self.refresh_comparison()

        for index, mgr in enumerate(self.msgarea_mgr):
            msgarea = mgr.new_from_text_and_icon(
                gtk.STOCK_INFO,
                _("Change highlighting incomplete"),
                _("Some changes were not highlighted because they were too "
                  "large. You can force Meld to take longer to highlight "
                  "larger changes, though this may be slow."))
            mgr.set_msg_id(FileDiff.MSG_SLOW_HIGHLIGHT)
            button = msgarea.add_stock_button_with_text(
                _("Hide"), gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
            if index == 0:
                button.props.label = _("Hi_de")
            button = msgarea.add_button(
                _("Keep highlighting"), gtk.RESPONSE_OK)
            if index == 0:
                button.props.label = _("_Keep highlighting")
            msgarea.connect("response",
                            on_msgarea_highlighting_response)
            msgarea.show_all()

    def on_msgarea_identical_response(self, msgarea, respid):
        for mgr in self.msgarea_mgr:
            mgr.clear()
        if respid == gtk.RESPONSE_OK:
            self.text_filters = []
            self.refresh_comparison()

    def on_textview_expose_event(self, textview, event):
        if self.num_panes == 1:
            return
        if event.window != textview.get_window(gtk.TEXT_WINDOW_TEXT) \
            and event.window != textview.get_window(gtk.TEXT_WINDOW_LEFT):
            return

        # Hack to redraw the line number gutter used by post-2.10 GtkSourceView
        if event.window == textview.get_window(gtk.TEXT_WINDOW_LEFT) and \
           self.in_nested_textview_gutter_expose:
            self.in_nested_textview_gutter_expose = False
            return

        visible = textview.get_visible_rect()
        pane = self.textview.index(textview)
        textbuffer = textview.get_buffer()
        area = event.area
        x, y = textview.window_to_buffer_coords(gtk.TEXT_WINDOW_WIDGET,
                                                area.x, area.y)
        bounds = (textview.get_line_num_for_y(y),
                  textview.get_line_num_for_y(y + area.height + 1))

        width, height = textview.allocation.width, textview.allocation.height
        context = event.window.cairo_create()
        context.rectangle(area.x, area.y, area.width, area.height)
        context.clip()
        context.set_line_width(1.0)

        for change in self.linediffer.single_changes(pane, bounds):
            ypos0 = textview.get_y_for_line_num(change[1]) - visible.y
            ypos1 = textview.get_y_for_line_num(change[2]) - visible.y

            context.rectangle(-0.5, ypos0 - 0.5, width + 1, ypos1 - ypos0)
            if change[1] != change[2]:
                context.set_source_color(self.fill_colors[change[0]])
                context.fill_preserve()
                if self.linediffer.locate_chunk(pane, change[1])[0] == self.cursor.chunk:
                    h = self.fill_colors['current-chunk-highlight']
                    context.set_source_rgba(
                        h.red_float, h.green_float, h.blue_float, 0.5)
                    context.fill_preserve()

            context.set_source_color(self.line_colors[change[0]])
            context.stroke()

        if (self.prefs.highlight_current_line and textview.is_focus() and
                self.cursor.line is not None):
            it = textbuffer.get_iter_at_line(self.cursor.line)
            ypos, line_height = textview.get_line_yrange(it)
            context.save()
            context.rectangle(0, ypos - visible.y, width, line_height)
            context.clip()
            context.set_source_color(self.highlight_color)
            context.paint_with_alpha(0.25)
            context.restore()

        for syncpoint in [p[pane] for p in self.syncpoints]:
            if not syncpoint:
                continue
            syncline = textbuffer.get_iter_at_mark(syncpoint).get_line()
            if bounds[0] <= syncline <= bounds[1]:
                ypos = textview.get_y_for_line_num(syncline) - visible.y
                context.rectangle(-0.5, ypos - 0.5, width + 1, 1)
                context.set_source_color(self.syncpoint_color)
                context.stroke()

        current_time = glib.get_current_time()
        new_anim_chunks = []
        for c in self.animating_chunks[pane]:
            percent = min(1.0, (current_time - c.start_time) / c.duration)
            rgba_pairs = zip(c.start_rgba, c.end_rgba)
            rgba = [s + (e - s) * percent for s, e in rgba_pairs]

            it = textbuffer.get_iter_at_mark(c.start_mark)
            ystart, _ = textview.get_line_yrange(it)
            it = textbuffer.get_iter_at_mark(c.end_mark)
            yend, _ = textview.get_line_yrange(it)
            if ystart == yend:
                ystart -= 1

            context.set_source_rgba(*rgba)
            context.rectangle(0, ystart - visible.y, width, yend - ystart)
            context.fill()

            if current_time <= c.start_time + c.duration:
                new_anim_chunks.append(c)
            else:
                textbuffer.delete_mark(c.start_mark)
                textbuffer.delete_mark(c.end_mark)
        self.animating_chunks[pane] = new_anim_chunks

        if self.animating_chunks[pane] and self.anim_source_id[pane] is None:
            def anim_cb():
                textview.queue_draw()
                return True
            # Using timeout_add interferes with recalculation of inline
            # highlighting; this mechanism could be improved.
            self.anim_source_id[pane] = gobject.idle_add(anim_cb)
        elif not self.animating_chunks[pane] and self.anim_source_id[pane]:
            gobject.source_remove(self.anim_source_id[pane])
            self.anim_source_id[pane] = None

        if event.window == textview.get_window(gtk.TEXT_WINDOW_LEFT):
            self.in_nested_textview_gutter_expose = True
            textview.emit("expose-event", event)

    def _get_filename_for_saving(self, title ):
        dialog = gtk.FileChooserDialog(title,
            parent=self.widget.get_toplevel(),
            action=gtk.FILE_CHOOSER_ACTION_SAVE,
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK) )
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        filename = None
        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filename()
        dialog.destroy()
        if filename:
            if os.path.exists(filename):
                response = misc.run_dialog(
                    _('"%s" exists!\nOverwrite?') % os.path.basename(filename),
                    parent = self,
                    buttonstype = gtk.BUTTONS_YES_NO)
                if response == gtk.RESPONSE_NO:
                    return None
            return filename
        return None

    def _save_text_to_filename(self, filename, text):
        try:
            open(filename, "wb").write(text)
        except IOError as e:
            misc.run_dialog(
                _("Error writing to %s\n\n%s.") % (filename, e),
                self, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK)
            return False
        return True

    def save_file(self, pane, saveas=False):
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
            if filename:
                bufdata.filename = bufdata.label = os.path.abspath(filename)
                bufdata.savefile = None
                self.fileentry[pane].set_filename(bufdata.filename)
                self.fileentry[pane].prepend_history(bufdata.filename)
            else:
                return False
        start, end = buf.get_bounds()
        text = text_type(buf.get_text(start, end, False), 'utf8')
        if bufdata.newlines:
            if isinstance(bufdata.newlines, basestring):
                if bufdata.newlines != '\n':
                    text = text.replace("\n", bufdata.newlines)
            else:
                buttons = {
                    '\n': ("UNIX (LF)", 0),
                    '\r\n': ("DOS/Windows (CR-LF)", 1),
                    '\r': ("Mac OS (CR)", 2),
                }
                newline = misc.run_dialog( _("This file '%s' contains a mixture of line endings.\n\nWhich format would you like to use?") % bufdata.label,
                    self, gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_CANCEL,
                    extrabuttons=[ buttons[b] for b in bufdata.newlines ] )
                if newline < 0:
                    return
                for k,v in buttons.items():
                    if v[1] == newline:
                        bufdata.newlines = k
                        if k != '\n':
                            text = text.replace('\n', k)
                        break
        if bufdata.encoding:
            try:
                text = text.encode(bufdata.encoding)
            except UnicodeEncodeError:
                if misc.run_dialog(
                    _("'%s' contains characters not encodable with '%s'\nWould you like to save as UTF-8?") % (bufdata.label, bufdata.encoding),
                    self, gtk.MESSAGE_ERROR, gtk.BUTTONS_YES_NO) != gtk.RESPONSE_YES:
                    return False

        save_to = bufdata.savefile or bufdata.filename
        if self._save_text_to_filename(save_to, text):
            self.emit("file-changed", save_to)
            self.undosequence.checkpoint(buf)
            return True
        else:
            return False

    def make_patch(self, *extra):
        dialog = patchdialog.PatchDialog(self)
        dialog.run()

    def set_buffer_writable(self, buf, writable):
        buf.data.writable = writable
        self.recompute_label()
        index = self.textbuffer.index(buf)
        self.readonlytoggle[index].props.visible = not writable
        self.set_buffer_editable(buf, writable)

    def set_buffer_modified(self, buf, yesno):
        buf.data.modified = yesno
        self.recompute_label()

    def set_buffer_editable(self, buf, editable):
        buf.data.editable = editable
        index = self.textbuffer.index(buf)
        self.readonlytoggle[index].set_active(not editable)
        self.textview[index].set_editable(editable)
        self.on_cursor_position_changed(buf, None, True)
        for linkmap in self.linkmap:
            linkmap.queue_draw()

    def save(self):
        pane = self._get_focused_pane()
        if pane >= 0:
            self.save_file(pane)

    def save_as(self):
        pane = self._get_focused_pane()
        if pane >= 0:
            self.save_file(pane, True)

    def on_save_all_activate(self, action):
        for i in range(self.num_panes):
            if self.textbuffer[i].data.modified:
                self.save_file(i)

    def on_fileentry_activate(self, entry):
        if self.check_save_modified() != gtk.RESPONSE_CANCEL:
            entries = self.fileentry[:self.num_panes]
            paths = [e.get_full_path() for e in entries]
            paths = [p.decode('utf8') for p in paths]
            self.set_files(paths)
        return True

    def _get_focused_pane(self):
        for i in range(self.num_panes):
            if self.textview[i].is_focus():
                return i
        return -1

    def on_revert_activate(self, *extra):
        response = gtk.RESPONSE_OK
        unsaved = [b.data.label for b in self.textbuffer if b.data.modified]
        if unsaved:
            ui_path = paths.ui_dir("filediff.ui")
            dialog = gnomeglade.Component(ui_path, "revert_dialog")
            dialog.widget.set_transient_for(self.widget.get_toplevel())
            # FIXME: Should be packed into dialog.widget.get_message_area(),
            # but this is unbound on currently required PyGTK.
            filelist = "\n".join(["\t" + f for f in unsaved])
            dialog.widget.props.secondary_text += filelist
            response = dialog.widget.run()
            dialog.widget.destroy()

        if response == gtk.RESPONSE_OK:
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

    def on_lock_button_toggled(self, button):
        self.toggle_scroll_lock(not button.get_active())

    def toggle_scroll_lock(self, locked):
        icon_name = "meld-locked" if locked else "meld-unlocked"
        self.lock_button_image.props.icon_name = icon_name
        self.lock_button.set_active(not locked)
        self.actiongroup.get_action("LockScrolling").set_active(locked)
        self._scroll_lock = not locked

    def on_readonly_button_toggled(self, button):
        index = self.readonlytoggle.index(button)
        buf = self.textbuffer[index]
        self.set_buffer_editable(buf, not button.get_active())

        #
        # scrollbars
        #
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
            master_y = adjustment.value + adjustment.page_size * syncpoint
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
                val -= (adj.page_size) * syncpoint
                val += (other_line-int(other_line)) * height
                val = min(max(val, adj.lower), adj.upper - adj.page_size)
                adj.set_value( val )

                # If we just changed the central bar, make it the master
                if i == 1:
                    master, line = 1, other_line
            self._sync_vscroll_lock = False

        for lm in self.linkmap:
            if lm.window:
                lm.window.invalidate_rect(None, True)
                lm.window.process_updates(True)

    def set_num_panes(self, n):
        if n != self.num_panes and n in (1,2,3):
            self.num_panes = n
            toshow =  self.scrolledwindow[:n] + self.fileentry[:n]
            toshow += self.vbox[:n] + self.msgarea_mgr[:n]
            toshow += self.linkmap[:n-1] + self.diffmap[:n]
            toshow += self.selector_hbox[:n]
            for widget in toshow:
                widget.show()

            tohide =  self.statusimage + self.scrolledwindow[n:] + self.fileentry[n:]
            tohide += self.vbox[n:] + self.msgarea_mgr[n:]
            tohide += self.linkmap[n-1:] + self.diffmap[n:]
            tohide += self.selector_hbox[n:]
            for widget in tohide:
                widget.hide()

            right_attach = 2 * n
            if self.findbar.widget in self.table:
                self.table.remove(self.findbar.widget)
            self.table.attach(self.findbar.widget, 1, right_attach, 2, 3,
                              gtk.FILL, gtk.FILL)

            self.actiongroup.get_action("MakePatch").set_sensitive(n > 1)
            self.actiongroup.get_action("CycleDocuments").set_sensitive(n > 1)

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
                w.setup(scroll, coords_iter(i), [self.fill_colors, self.line_colors])

            for (w, i) in zip(self.linkmap, (0, self.num_panes - 2)):
                w.associate(self, self.textview[i], self.textview[i + 1])

            for i in range(self.num_panes):
                if self.textbuffer[i].data.modified:
                    self.statusimage[i].show()
            self.queue_draw()
            self.recompute_label()

    def next_diff(self, direction, centered=False):
        pane = self._get_focused_pane()
        if pane == -1:
            if len(self.textview) > 1:
                pane = 1
            else:
                pane = 0
        buf = self.textbuffer[pane]

        if direction == gtk.gdk.SCROLL_DOWN:
            target = self.cursor.next
        else: # direction == gtk.gdk.SCROLL_UP
            target = self.cursor.prev

        if target is None:
            return

        c = self.linediffer.get_chunk(target, pane)
        if c:
            # Warp the cursor to the first line of next chunk
            if self.cursor.line != c[1]:
                buf.place_cursor(buf.get_iter_at_line(c[1]))
            if centered:
                self.textview[pane].scroll_to_mark(buf.get_insert(), 0.0,
                                                   True)
            else:
                self.textview[pane].scroll_to_mark(buf.get_insert(), 0.2)

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
        else: # copy down
            dst_start = b1.get_iter_at_line_or_eof(chunk[4])
            mark0 = b1.create_mark(None, dst_start, True)
            new_end = b1.insert_at_line(chunk[4], t0)

        mark1 = b1.create_mark(None, new_end, True)
        # FIXME: If the inserted chunk ends up being an insert chunk, then
        # this animation is not visible; this happens often in three-way diffs
        rgba0 = misc.gdk_to_cairo_color(self.fill_colors['insert']) + (1.0,)
        rgba1 = misc.gdk_to_cairo_color(self.fill_colors['insert']) + (0.0,)
        anim = TextviewLineAnimation(mark0, mark1, rgba0, rgba1, 0.5)
        self.animating_chunks[dst].append(anim)

    def replace_chunk(self, src, dst, chunk):
        b0, b1 = self.textbuffer[src], self.textbuffer[dst]
        src_start = b0.get_iter_at_line_or_eof(chunk[1])
        src_end = b0.get_iter_at_line_or_eof(chunk[2])
        dst_start = b1.get_iter_at_line_or_eof(chunk[3])
        dst_end = b1.get_iter_at_line_or_eof(chunk[4])
        t0 = text_type(b0.get_text(src_start, src_end, False), 'utf8')
        mark0 = b1.create_mark(None, dst_start, True)
        self.on_textbuffer__begin_user_action()
        b1.delete(dst_start, dst_end)
        new_end = b1.insert_at_line(chunk[3], t0)
        self.on_textbuffer__end_user_action()
        mark1 = b1.create_mark(None, new_end, True)
        # FIXME: If the inserted chunk ends up being an insert chunk, then
        # this animation is not visible; this happens often in three-way diffs
        rgba0 = misc.gdk_to_cairo_color(self.fill_colors['insert']) + (1.0,)
        rgba1 = misc.gdk_to_cairo_color(self.fill_colors['insert']) + (0.0,)
        anim = TextviewLineAnimation(mark0, mark1, rgba0, rgba1, 0.5)
        self.animating_chunks[dst].append(anim)

    def delete_chunk(self, src, chunk):
        b0 = self.textbuffer[src]
        it = b0.get_iter_at_line_or_eof(chunk[1])
        if chunk[2] >= b0.get_line_count():
            it.backward_char()
        b0.delete(it, b0.get_iter_at_line_or_eof(chunk[2]))
        mark0 = b0.create_mark(None, it, True)
        mark1 = b0.create_mark(None, it, True)
        # TODO: Need a more specific colour here; conflict is wrong
        rgba0 = misc.gdk_to_cairo_color(self.fill_colors['conflict']) + (1.0,)
        rgba1 = misc.gdk_to_cairo_color(self.fill_colors['conflict']) + (0.0,)
        anim = TextviewLineAnimation(mark0, mark1, rgba0, rgba1, 0.5)
        self.animating_chunks[src].append(anim)

    def add_sync_point(self, action):
        pane = self._get_focused_pane()
        if pane == -1:
            return

        # Find a non-complete syncpoint, or create a new one
        if self.syncpoints and None in self.syncpoints[-1]:
            syncpoint = self.syncpoints.pop()
        else:
            syncpoint = [None] * self.num_panes
        cursor_it = self.textbuffer[pane].get_iter_at_mark(
            self.textbuffer[pane].get_insert())
        syncpoint[pane] = self.textbuffer[pane].create_mark(None, cursor_it)
        self.syncpoints.append(syncpoint)

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
                    gtk.STOCK_DIALOG_INFO,
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
        for mgr in self.msgarea_mgr:
            if mgr.get_msg_id() == FileDiff.MSG_SYNCPOINTS:
                mgr.clear()
        self.refresh_comparison()
