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


import logging

from gi.repository import Gio, GLib, GObject, Gtk, GtkSource

from meld import misc
from meld.conf import _
from meld.const import TEXT_FILTER_ACTION_FORMAT, ActionMode
from meld.filediff import FileDiff
from meld.melddoc import MeldDoc
from meld.recent import RecentType
from meld.settings import bind_settings, get_meld_settings

log = logging.getLogger(__name__)

# These lists contain all the actions in FileDiff, except for the actions generated for each filter.
# Those lists are verified by _verify_action_lists()

FWD_TO_ACTIVE_ACTIONS = [
    'add-sync-point',
    'remove-sync-point',
    'clear-sync-point',
    'copy',
    'copy-full-path',
    'cut',
    'file-push-left',
    'file-push-right',
    'file-pull-left',
    'file-pull-right',
    'file-copy-left-up',
    'file-copy-right-up',
    'file-copy-left-down',
    'file-copy-right-down',
    'file-delete',
    'find',
    'find-next',
    'find-previous',
    'find-replace',
    'format-as-patch',
    'go-to-line',
    'merge-all-left',
    'merge-all-right',
    'merge-all',
    'next-change',
    'next-pane',
    'open-external',
    'open-folder',
    'paste',
    'previous-change',
    'previous-pane',
    'redo',
    'undo',
]

FWD_TO_ALL_ACTIONS = [
    'refresh',
    'revert',
    'save',
    'save-all',
]

SELF_ACTIONS = [
    # There are no FileDiff conflicts in 2-pane view. We do want to use those actions
    # to find the next and previous conflict markers in the text.
    'file-previous-conflict',
    'file-next-conflict',
]

DISABLED_ACTIONS = [
    # save-as is disabled since we don't want filenames to change
    'save-as',
    # swap-2-panes is disabled since reversing all panes would require more work, and I
    # currently don't see why it should be useful.
    'swap-2-panes',
]

PROPERTY_ACTIONS = {
    'show-overview-map': 'show-overview-map',
    'lock-scrolling': 'lock_scrolling',
}

STATE_ACTIONS = {
    'text-filter': False,
}


def _get_diff_actions(diff: FileDiff) -> tuple[set[str], set[str]]:
    """Get all actions in a FileDiff, stateless and stateful"""
    all_action_names = set(diff.view_action_group.list_actions())
    stateful_action_names = set()
    stateless_action_names = set()
    for action_name in all_action_names:
        state = diff.view_action_group.get_action_state(action_name)
        if state is None:
            stateless_action_names.add(action_name)
        else:
            # Assert all stateful actions have type bool
            assert state.get_type_string() == 'b'
            stateful_action_names.add(action_name)
    return stateless_action_names, stateful_action_names


def _verify_action_lists(diff: FileDiff):
    """Assert that the action lists cover all the actions in the FileDiff."""
    stateless_names, stateful_names = _get_diff_actions(diff)
    expected_stateless_names = FWD_TO_ACTIVE_ACTIONS + FWD_TO_ALL_ACTIONS + SELF_ACTIONS + DISABLED_ACTIONS
    assert set(expected_stateless_names) == stateless_names
    # In addition to the listed actions, the FileDiff creates
    # stateful actions for each text filter. We expect those as well.
    n_text_filters = len(get_meld_settings().text_filters)
    text_filter_action_names = [TEXT_FILTER_ACTION_FORMAT.format(i) for i in range(n_text_filters)]
    expected_stateful_names = list(PROPERTY_ACTIONS) + list(STATE_ACTIONS) + text_filter_action_names
    assert set(expected_stateful_names) == stateful_names


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
        self.grid0.attach(self.diff0, left=0, top=0, width=2, height=1)

        self.diff1 = FileDiff(2)
        self.scheduler.add_scheduler(self.diff1.scheduler)
        # The labels are used to fill the empty spaces in the grid
        self.label0 = Gtk.Label()
        self.label1 = Gtk.Label()
        self.grid1.attach(self.label0, left=0, top=0, width=1, height=1)
        self.grid1.attach(self.diff1, left=1, top=0, width=2, height=1)
        self.grid1.attach(self.label1, left=3, top=0, width=1, height=1)

        self.diff2 = FileDiff(2)
        self.scheduler.add_scheduler(self.diff2.scheduler)
        self.undosequence = self.diff2.undosequence
        self.grid0.attach(self.diff2, left=2, top=0, width=2, height=1)

        self.diffs = [self.diff0, self.diff1, self.diff2]

        # We always have an active FileDiff, which is self.diffs[self.active_diff_i].
        # When Showing 1 FileDiff, it is the active diff. When showing 2 FileDiffs, it's the one which last
        # received focus.
        self.active_diff_i = 2
        self.active_diff = self.diffs[self.active_diff_i]
        self.is_showing_2_diffs = True
        self.active_diff_i_when_showing_2_diffs = 2

        # We use a SearchContext to search for conflict markers in the right pane
        self.search_settings = GtkSource.SearchSettings()
        self.search_settings.props.search_text = "<<<<<<<"
        self.search_settings.set_wrap_around(False)
        self.search_context = GtkSource.SearchContext.new(self.diff2.textbuffer[1], self.search_settings)
        self.search_context.set_highlight(False)

        for diff_i in [0, 2]:
            for tv in self.diffs[diff_i].textview:
                tv.connect('focus-in-event', self.on_textview_focus_in_event, diff_i)

        for diff in self.diffs:
            diff.connect('label-changed', self.on_diff_label_changed)

        self._init_actions()

        self.label0.show()
        self.label1.show()
        self.grid0.show()
        self.grid1.show()
        self.show()

        self.files = None

        self.connect_scrolledwindows()

    def _init_actions(self):
        """
        Create actions to forward to the FileDiffs.
        Most actions are forwarded to the active FileDiff, some are forwarded to all.
        """
        for diff in self.diffs:
            _verify_action_lists(diff)

        my_actions = [
            ('toggle-fourdiff-view', self.action_toggle_view),
            ('file-previous-conflict', self.action_previous_conflict),
            ('file-next-conflict', self.action_next_conflict),
        ]
        for name, callback in my_actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.view_action_group.add_action(action)

        for name in FWD_TO_ACTIVE_ACTIONS:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', self.on_fwd_to_active_action_activate)
            self.view_action_group.add_action(action)

        for name in FWD_TO_ALL_ACTIONS:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', self.on_fwd_to_all_action_activate)
            self.view_action_group.add_action(action)

        for action_name, prop_name in PROPERTY_ACTIONS.items():
            action = Gio.PropertyAction.new(action_name, self, prop_name)
            action.connect('notify::state', self.on_property_action_change_state)
            self.view_action_group.add_action(action)

        for action_name, state in STATE_ACTIONS.items():
            action = Gio.SimpleAction.new_stateful(name, None, GLib.Variant.new_boolean(state))
            action.connect('activate', self.on_fwd_to_all_action_activate)
            action.connect('change-state', self.on_action_change_state)
            self.view_action_group.add_action(action)

        for diff_i, diff in enumerate(self.diffs):
            diff.view_action_group.connect('action-enabled-changed', self.on_diff_action_enabled_changed, diff_i)

    def on_fwd_to_active_action_activate(self, action, user_data):
        self.active_diff.view_action_group.activate_action(action.get_name(), user_data)

    def on_fwd_to_all_action_activate(self, action, user_data):
        for diff in self.diffs:
            diff.view_action_group.activate_action(action.get_name(), user_data)

    def on_diff_action_enabled_changed(self, _action_group, name, enabled, diff_i):
        if diff_i == self.active_diff_i:
            self.view_action_group.lookup(name).set_enabled(enabled)

    def on_property_action_change_state(self, paction, _param_spec):
        for diff in self.diffs:
            diff.view_action_group.change_action_state(paction.props.name, paction.props.state)

    def on_action_change_state(self, action, state):
        for diff in self.diffs:
            diff.view_action_group.change_action_state(action.get_name(), state)

    def _update_active_diff(self):
        """
        Update self.active_diff_i based on self.active_diff_i_when_showing_2_diffs and self.is_showing_2_diffs.
        If changed, send signals and update actions accordingly.
        """
        active_diff_i = self.active_diff_i_when_showing_2_diffs if self.is_showing_2_diffs else 1
        if active_diff_i != self.active_diff_i:
            self.active_diff_i = active_diff_i
            self.active_diff = self.diffs[active_diff_i]

            diff_view_action_group = self.active_diff.view_action_group
            for name in FWD_TO_ACTIVE_ACTIONS:
                self.view_action_group.lookup(name).set_enabled(diff_view_action_group.lookup(name).get_enabled())

    def on_textview_focus_in_event(self, _textbuffer, _event, diff_i):
        self.active_diff_i_when_showing_2_diffs = diff_i
        self._update_active_diff()

    @staticmethod
    def _set_read_only(diff, panes):
        # A helper function for set_files()
        for pane in panes:
            buf = diff.textbuffer[pane]
            buf.data.force_read_only = True
            diff.update_buffer_writable(buf)

    def set_files(self, files):
        """Load the given files

        If an element is None, the text of a pane is left as is.
        """
        assert len(files) == 4
        self.files = files
        self.diff0.set_files(files[:2])
        self._set_read_only(self.diff0, [1])
        self.diff1.set_files(files[1:3])
        self._set_read_only(self.diff1, [0, 1])
        self.diff2.set_files(files[2:])
        self._set_read_only(self.diff2, [0])

        self.recompute_label()

    def recompute_label(self):
        buffers = self.diff0.textbuffer[:2] + self.diff2.textbuffer[:2]
        filenames = [b.data.label for b in buffers]
        shortnames = misc.shorten_names(*filenames)

        for i, buf in enumerate(buffers):
            if buf.get_modified():
                shortnames[i] += "*"

        label_text = " — ".join(shortnames)
        tooltip_names = filenames
        tooltip_text = "\n".join((_("File comparison:"), *tooltip_names))
        self.label_changed.emit(label_text, tooltip_text)

    def on_diff_label_changed(self, _diff, _label_text, _tooltip_text):
        self.recompute_label()

    @staticmethod
    def _on_adj_changed(me, other):
        # A helper function for connect_scrolledwindows()
        v = me.get_value()
        if other.get_value() != v:
            other.set_value(v)

    def connect_scrolledwindows(self):
        sws = [self.diff0.scrolledwindow[1], self.diff1.scrolledwindow[0],
               self.diff1.scrolledwindow[1], self.diff2.scrolledwindow[0]]
        vadjs = [sw.get_vadjustment() for sw in sws]
        hadjs = [sw.get_hadjustment() for sw in sws]

        def connect(adj0, adj1):
            adj0.connect("value-changed", self._on_adj_changed, adj1)
            adj1.connect("value-changed", self._on_adj_changed, adj0)
        connect(vadjs[0], vadjs[1])
        connect(hadjs[0], hadjs[1])
        connect(vadjs[2], vadjs[3])
        connect(hadjs[2], hadjs[3])

    def action_toggle_view(self, *args):
        self.is_showing_2_diffs = not self.is_showing_2_diffs
        self.set_visible_child_name('grid0' if self.is_showing_2_diffs else 'grid1')
        self._update_active_diff()

    def get_conflict_visibility(self) -> bool:
        return True

    def _find_conflict(self, backwards: bool):
        # Based on FindBar._find_text
        buf = self.diff2.textbuffer[1]
        insert = buf.get_iter_at_mark(buf.get_insert())
        if backwards:
            match, start, end, wrapped = self.search_context.backward(insert)
        else:
            insert.forward_chars(1)
            match, start, end, wrapped = self.search_context.forward(insert)
        if match:
            buf.place_cursor(start)
            self.diff2.textview[1].scroll_to_mark(
                buf.get_insert(), 0.25, True, 0.5, 0.5)

    def action_previous_conflict(self, _action, _value):
        self._find_conflict(backwards=True)

    def action_next_conflict(self, _action, _value):
        self._find_conflict(backwards=False)

    def on_delete_event(self):
        # TODO: check if there are still conflict markers
        self.emit('close', 0)
        return Gtk.ResponseType.OK

    def get_comparison(self):
        # TODO
        return RecentType.Merge, []
        # uris = [b.data.gfile for b in self.textbuffer[:self.num_panes]]

        # if self.comparison_mode == FileComparisonMode.AutoMerge:
        #     comparison_type = RecentType.Merge
        # else:
        #     comparison_type = RecentType.File

        # return comparison_type, uris
