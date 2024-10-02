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
from meld.filediff import FileDiff
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


class FourDiff(Gtk.Stack, MeldDoc):
    """Four way comparison of text files"""

    __gtype_name__ = "FourDiff"

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

    def __init__(self):
        super().__init__()
        # FIXME:
        # See FileDiff.__init__, which calls this an "unimaginable hack".
        # I don't really understand the issue. It mentions Gtk.Template, which we
        # don't inherit from, so perhaps this could be fixed here.
        MeldDoc.__init__(self)
        bind_settings(self)

        # Manually handle GAction additions
        actions = (
            # ('add-sync-point', self.add_sync_point),
            # ('remove-sync-point', self.remove_sync_point),
            # ('clear-sync-point', self.clear_sync_points),
            # ('copy', self.action_copy),
            # ('copy-full-path', self.action_copy_full_path),
            # ('cut', self.action_cut),
            # ('file-previous-conflict', self.action_previous_conflict),
            # ('file-next-conflict', self.action_next_conflict),
            # ('file-push-left', self.action_push_change_left),
            # ('file-push-right', self.action_push_change_right),
            # ('file-pull-left', self.action_pull_change_left),
            # ('file-pull-right', self.action_pull_change_right),
            # ('file-copy-left-up', self.action_copy_change_left_up),
            # ('file-copy-right-up', self.action_copy_change_right_up),
            # ('file-copy-left-down', self.action_copy_change_left_down),
            # ('file-copy-right-down', self.action_copy_change_right_down),
            # ('file-delete', self.action_delete_change),
            # ('find', self.action_find),
            # ('find-next', self.action_find_next),
            # ('find-previous', self.action_find_previous),
            # ('find-replace', self.action_find_replace),
            # ('format-as-patch', self.action_format_as_patch),
            # ('go-to-line', self.action_go_to_line),
            # ('merge-all-left', self.action_pull_all_changes_left),
            # ('merge-all-right', self.action_pull_all_changes_right),
            # ('merge-all', self.action_merge_all_changes),
            # ('next-change', self.action_next_change),
            # ('next-pane', self.action_next_pane),
            # ('open-external', self.action_open_external),
            # ('open-folder', self.action_open_folder),
            # ('paste', self.action_paste),
            # ('previous-change', self.action_previous_change),
            # ('previous-pane', self.action_prev_pane),
            # ('redo', self.action_redo),
            # ('refresh', self.action_refresh),
            # ('revert', self.action_revert),
            # ('save', self.action_save),
            # ('save-all', self.action_save_all),
            # ('save-as', self.action_save_as),
            # ('undo', self.action_undo),
            # ('swap-2-panes', self.action_swap),
            ('toggle-fourdiff-view', self.action_toggle_view),
        )
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.view_action_group.add_action(action)

        self.grid0 = Gtk.Grid()
        self.grid0.set_row_homogeneous(True)
        self.grid0.set_column_homogeneous(True)
        self.add_named(self.grid0, "grid0")
        self.grid1 = Gtk.Grid()
        self.grid1.set_row_homogeneous(True)
        self.grid1.set_column_homogeneous(True)
        self.add_named(self.grid1, "grid1")
        
        self.diff0 = FileDiff(2)
        self.scheduler.add_scheduler(self.diff0.scheduler)
        # TODO: self.diff0.force_readonly = [True, True]
        self.grid0.attach(self.diff0, left=0, top=0, width=2, height=1)

        self.diff1 = FileDiff(2)
        self.scheduler.add_scheduler(self.diff1.scheduler)
        # TODO: self.diff1.force_readonly = [True, True]
        # The labels are used to fill the empty spaces in the grid
        self.label0 = Gtk.Label()
        self.label1 = Gtk.Label()
        self.grid1.attach(self.label0, left=0, top=0, width=1, height=1)
        self.grid1.attach(self.diff1, left=1, top=0, width=2, height=1)
        self.grid1.attach(self.label1, left=3, top=0, width=1, height=1)

        self.diff2 = FileDiff(2)
        self.scheduler.add_scheduler(self.diff2.scheduler)
        # TODO: self.diff2.force_readonly = [True, False]
        self.undosequence = self.diff2.undosequence
        # TODO: self.actiongroup = self.diff2.actiongroup
        self.grid0.attach(self.diff2, left=2, top=0, width=2, height=1)

        self.diffs = [self.diff0, self.diff1, self.diff2]
        # self.have_next_diffs = [(False, False) for _ in self.diffs]
        # for diff in self.diffs:
        #     diff.connect("next-diff-changed", self.on_have_next_diff_changed)

        # self.grid0.connect("set-focus-child", self.on_grid0_set_focus_child)

        self.label0.show()
        self.label1.show()
        self.grid0.show()
        self.grid1.show()
        self.show()

        self.files = None

        self._keep = []
        self.connect_scrolledwindows()

    def set_files(self, files):
        """Load the given files

        If an element is None, the text of a pane is left as is.
        """
        assert len(files) == 4
        self.files = files
        self.diff0.set_files(files[:2])
        self.diff1.set_files(files[1:3])
        self.diff2.set_files(files[2:])

    def connect_scrolledwindows(self):
        sws = [self.diff0.scrolledwindow[1], self.diff1.scrolledwindow[0],
               self.diff1.scrolledwindow[1], self.diff2.scrolledwindow[0]]
        vadjs = [sw.get_vadjustment() for sw in sws]
        hadjs = [sw.get_hadjustment() for sw in sws]
        # We keep the references because otherwise we get uninitialized
        # references in the callbacks
        self._keep.extend([vadjs, hadjs])

        def connect(adj0, adj1):
            adj0.connect("value-changed", self.on_adj_changed, adj1)
            adj1.connect("value-changed", self.on_adj_changed, adj0)
        connect(vadjs[0], vadjs[1])
        connect(hadjs[0], hadjs[1])
        connect(vadjs[2], vadjs[3])
        connect(hadjs[2], hadjs[3])

    def action_toggle_view(self, *args):
        if self.get_visible_child_name() == 'grid1':
            self.set_visible_child_name('grid0')
        else:
            self.set_visible_child_name('grid1')
        # self.on_active_diff_changed()
    
    @staticmethod
    def on_adj_changed(me, other):
        v = me.get_value()
        if other.get_value() != v:
            other.set_value(v)

    def on_delete_event(self):
        self.emit('close', 0)
        return Gtk.ResponseType.OK

    def get_comparison(self):
        # TODO
        return RecentType.Merge, []
        uris = [b.data.gfile for b in self.textbuffer[:self.num_panes]]

        if self.comparison_mode == FileComparisonMode.AutoMerge:
            comparison_type = RecentType.Merge
        else:
            comparison_type = RecentType.File

        return comparison_type, uris

