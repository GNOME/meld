import logging
from enum import Enum

from gi.repository import GtkSource

from meld.sourceview import SYNCPOINT_MARK_CATEGORY

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
    # Each syncpoint is a list of length num_panes, holding one mark per
    # pane (or None for a pane that hasn't contributed a matching mark yet).
    SyncPoint = list[GtkSource.Mark | None]

    def __init__(self, num_panes: int):
        self._num_panes = num_panes
        self._points: list[Syncpoints.SyncPoint] = []

    def get_mark_line(self, mark):
        return mark.get_buffer().get_iter_at_mark(mark).get_line()

    def add(self, pane_idx: int, buf: GtkSource.Buffer):
        pane_state = self._pane_state(pane_idx)

        # Create a new source mark at the start of the cursor line
        current_line = buf.get_iter_at_mark(buf.get_insert())
        current_line.set_line_offset(0)
        mark = buf.create_source_mark(None, SYNCPOINT_MARK_CATEGORY, current_line)

        if pane_state == PaneState.DANGLING:
            # TODO: This is a move action; we should make it a real move action
            # by moving the mark instead of leaving orphan marks around
            self._clear_dangling_slot(pane_idx)

        for sp in self._points:
            if sp[pane_idx] is None:
                sp[pane_idx] = mark
                break
        else:
            new_sp: Syncpoints.SyncPoint = [None] * self._num_panes
            new_sp[pane_idx] = mark
            self._points.append(new_sp)

        if all(None not in sp for sp in self._points):
            self._resort()

    def remove(self, pane_idx: int, buf: GtkSource.Buffer):
        current_line = buf.get_iter_at_mark(buf.get_insert())
        current_line.set_line_offset(0)
        sync_marks = buf.get_source_marks_at_iter(current_line, SYNCPOINT_MARK_CATEGORY)
        if not sync_marks:
            log.warning("No syncpoint mark found when removing syncpoint")
            return

        target_sp = None
        for sp in self._points:
            if sp[pane_idx] == sync_marks[0]:
                target_sp = sp
                break

        assert target_sp is not None

        pane_state = self._pane_state(pane_idx)

        assert pane_state != PaneState.SHORT

        if pane_state == PaneState.MATCHED:
            self._points.remove(target_sp)
        elif pane_state == PaneState.DANGLING:
            self._clear_dangling_slot(pane_idx)

        # TODO: This should also delete the marks

    def clear(self):
        self._points = []

    def valid_points(self):
        return [tuple(sp) for sp in self._points if None not in sp]

    def _pane_count(self, pane_idx: int) -> int:
        return sum(1 for sp in self._points if sp[pane_idx] is not None)

    def _pane_state(self, pane_idx: int):
        counts = [self._pane_count(i) for i in range(self._num_panes)]
        lengths = set(counts)

        if len(lengths) == 1:
            return PaneState.MATCHED

        if counts[pane_idx] == min(lengths):
            return PaneState.SHORT
        else:
            return PaneState.DANGLING

    def _clear_dangling_slot(self, pane_idx: int):
        for sp in self._points:
            if sp[pane_idx] is not None and None in sp:
                sp[pane_idx] = None
                if all(m is None for m in sp):
                    self._points.remove(sp)
                return

    def _resort(self):
        per_pane = [
            sorted(
                (sp[i] for sp in self._points if sp[i] is not None),
                key=self.get_mark_line,
            )
            for i in range(self._num_panes)
        ]
        n = len(per_pane[0]) if per_pane else 0
        self._points = [
            [per_pane[i][j] for i in range(self._num_panes)]
            for j in range(n)
        ]

    def action(self, pane_idx: int, get_mark):
        state = self._pane_state(pane_idx)
        target = self.get_mark_line(get_mark())

        marks = [sp[pane_idx] for sp in self._points if sp[pane_idx] is not None]
        is_syncpoint = any(
            self.get_mark_line(mark) == target for mark in marks
        )

        match state:
            case PaneState.SHORT:
                return SyncpointAction.MATCH
            case PaneState.MATCHED:
                return SyncpointAction.DELETE if is_syncpoint else SyncpointAction.ADD
            case PaneState.DANGLING:
                if target == self.get_mark_line(marks[-1]):
                    return SyncpointAction.DELETE
                return (
                    SyncpointAction.DISABLED if is_syncpoint else SyncpointAction.MOVE
                )
