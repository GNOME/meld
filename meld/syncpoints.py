import logging
from enum import Enum

from gi.repository import Gtk, GtkSource

from meld.sourceview import SYNCPOINT_MARK_CATEGORY, SYNCPOINT_SENTINEL

log = logging.getLogger(__name__)


class SyncpointAction(Enum):
    # A dangling syncpoint can be moved to the line
    MOVE = "move-sync-point"
    # A dangling syncpoint sits can be remove from this line
    DELETE = "remove-sync-point"
    # A syncpoint can be added to this line to match existing ones
    # in other panes
    MATCH = "match-sync-point"
    # A new, dangling syncpoint can be added to this line
    ADD = "add-sync-point"
    # No syncpoint-related action can be taken on this line
    DISABLED = "disabled-sync-point"


class PaneState(Enum):
    # The state of a pane with all its syncpoints matched
    MATCHED = "matched"
    # The state of a pane waiting to be matched to existing syncpoints
    # in other panes
    SHORT = "short"
    # The state of a pane with a dangling syncpoint, not yet matched
    # across all panes
    DANGLING = "DANGLING"


class Syncpoints:
    def __init__(self, buffers: list[GtkSource.Buffer]):
        self._buffers = list(buffers)
        # Most recent calculated set of pairings (a tuple of marks being a
        # syncpoint). These are recalculated only when all panes have the
        # same number of syncpoints.
        self._cached_points: list[tuple[GtkSource.Mark, ...]] = []
        self._pane_states: list[PaneState] = [PaneState.MATCHED] * len(self._buffers)

        for buf in self._buffers:
            buf.connect("source-mark-updated", self._on_source_mark_updated)
        self._update_syncpoint_state()

    def _pane_marks(self, buf: GtkSource.Buffer) -> list[GtkSource.Mark]:
        marks: list[GtkSource.Mark] = []
        mark = buf.get_mark(SYNCPOINT_SENTINEL).next(SYNCPOINT_MARK_CATEGORY)
        while mark is not None:
            marks.append(mark)
            mark = mark.next(SYNCPOINT_MARK_CATEGORY)
        return marks

    def _update_syncpoint_state(self):
        # Walk syncpoint marks in all panes in lockstep, stopping whenever any
        # pane runs out of syncpoint marks
        syncpoint = [b.get_mark(SYNCPOINT_SENTINEL) for b in self._buffers]
        paired = []
        while True:
            next_syncpoint = [m.next(SYNCPOINT_MARK_CATEGORY) for m in syncpoint]
            if not all(next_syncpoint):
                break
            paired.append(tuple(next_syncpoint))
            syncpoint = next_syncpoint

        if all(m is None for m in next_syncpoint):
            # Every pane ran out on the same step, so we have a matched state
            # and will use the list of syncpoints we've built
            self._pane_states = [PaneState.MATCHED] * len(next_syncpoint)
            self._cached_points = paired
        else:
            # Exhausted panes are SHORT, the rest are DANGLING
            self._pane_states = [
                PaneState.SHORT if m is None else PaneState.DANGLING
                for m in next_syncpoint
            ]

    def _on_source_mark_updated(self, buf, mark):
        if mark.get_category() != SYNCPOINT_MARK_CATEGORY:
            return
        self._update_syncpoint_state()

    def _get_sync_cursor(self, buf: GtkSource.Buffer) -> Gtk.TextIter:
        cursor_it = buf.get_iter_at_mark(buf.get_insert())
        cursor_it.set_line_offset(0)
        return cursor_it

    def _mark_at_cursor(self, buf: GtkSource.Buffer) -> GtkSource.Mark | None:
        cursor = self._get_sync_cursor(buf)
        sentinel = buf.get_mark(SYNCPOINT_SENTINEL)
        for m in buf.get_source_marks_at_iter(cursor, SYNCPOINT_MARK_CATEGORY):
            if m is not sentinel:
                return m
        return None

    def add(self, buf: GtkSource.Buffer):
        cursor = self._get_sync_cursor(buf)
        buf.create_source_mark(None, SYNCPOINT_MARK_CATEGORY, cursor)

    def move(self, buf: GtkSource.Buffer):
        # Move an unmatched mark (i.e., mark not part of a valid pairing) to the cursor
        pane = self._buffers.index(buf)
        matched = {syncpoint[pane] for syncpoint in self._cached_points}
        unmatched = [mark for mark in self._pane_marks(buf) if mark not in matched]
        if not unmatched:
            log.warning("No unmatched syncpoint found to move")
            return
        buf.move_mark(unmatched[0], self._get_sync_cursor(buf))

    def remove(self, buf: GtkSource.Buffer):
        mark = self._mark_at_cursor(buf)
        if mark is None:
            log.warning("No syncpoint mark found when removing syncpoint")
            return
        buf.delete_mark(mark)

    def clear(self):
        for buf in self._buffers:
            for mark in self._pane_marks(buf):
                buf.delete_mark(mark)

    def valid_points(self):
        return list(self._cached_points)

    def action(self, buf: GtkSource.Buffer) -> SyncpointAction:
        pane = self._buffers.index(buf)
        state = self._pane_states[pane]
        mark = self._mark_at_cursor(buf)

        match state:
            case PaneState.SHORT:
                return SyncpointAction.DISABLED if mark else SyncpointAction.MATCH
            case PaneState.MATCHED:
                return SyncpointAction.DELETE if mark else SyncpointAction.ADD
            case PaneState.DANGLING:
                if mark is None:
                    return SyncpointAction.MOVE
                if mark in {sp[pane] for sp in self._cached_points}:
                    return SyncpointAction.DISABLED
                return SyncpointAction.DELETE
