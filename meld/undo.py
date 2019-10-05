# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2010-2011 Kai Willadsen <kai.willadsen@gmail.com>
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

"""Module to help implement undo functionality.

Usage:

t = TextWidget()
s = UndoSequence()
def on_textwidget_text_inserted():
    s.begin_group()
    if not t.is_modified():
        s.add_action( TextWidgetModifiedAction() )
    s.add_action( InsertionAction() )
    s.end_group()

def on_undo_button_pressed():
    s.undo()
"""

import logging
import weakref

from gi.repository import GObject

log = logging.getLogger(__name__)


class GroupAction:
    """A group action combines several actions into one logical action.
    """
    def __init__(self, seq):
        self.seq = seq
        # TODO: If a GroupAction affects more than one sequence, our logic
        # breaks. Currently, this isn't a problem.
        self.buffer = seq.actions[0].buffer

    def undo(self):
        actions = []
        while self.seq.can_undo():
            actions.extend(self.seq.undo())
        return actions

    def redo(self):
        actions = []
        while self.seq.can_redo():
            actions.extend(self.seq.redo())
        return actions


class UndoSequence(GObject.GObject):
    """A manager class for operations which can be undone/redone.
    """

    __gsignals__ = {
        'can-undo': (
            GObject.SignalFlags.RUN_FIRST,
            None, (GObject.TYPE_BOOLEAN,)
        ),
        'can-redo': (
            GObject.SignalFlags.RUN_FIRST,
            None, (GObject.TYPE_BOOLEAN,)
        ),
        'checkpointed': (
            GObject.SignalFlags.RUN_FIRST,
            None, (GObject.TYPE_OBJECT, GObject.TYPE_BOOLEAN,)
        ),
    }

    def __init__(self, buffers):
        """Create an empty UndoSequence

        An undo sequence is tied to a collection of GtkTextBuffers, and
        expects to maintain undo checkpoints for the same set of
        buffers for the lifetime of the UndoSequence.
        """
        super().__init__()
        self.buffer_refs = [weakref.ref(buf) for buf in buffers]
        self.clear()

    def clear(self):
        """Remove all undo and redo actions from this sequence

        If the sequence was previously able to undo and/or redo, the
        'can-undo' and 'can-redo' signals are emitted.
        """
        if self.can_undo():
            self.emit('can-undo', 0)
        if self.can_redo():
            self.emit('can-redo', 0)
        self.actions = []
        self.next_redo = 0
        self.checkpoints = {
            # Each buffer's checkpoint starts at zero and has no end
            ref(): [0, None] for ref in self.buffer_refs
        }
        self.group = None
        self.busy = False

    def can_undo(self):
        """Return whether an undo is possible."""
        return getattr(self, 'next_redo', 0) > 0

    def can_redo(self):
        """Return whether a redo is possible."""
        next_redo = getattr(self, 'next_redo', 0)
        return next_redo < len(getattr(self, 'actions', []))

    def add_action(self, action):
        """Add an action to the undo list.

        Arguments:

        action -- A class with two callable attributes: 'undo' and 'redo'
                  which are called by this sequence during an undo or redo.
        """
        if self.busy:
            return

        if self.group is None:
            if self.checkpointed(action.buffer):
                self.checkpoints[action.buffer][1] = self.next_redo
                self.emit('checkpointed', action.buffer, False)
            else:
                # If we go back in the undo stack before the checkpoint starts,
                # and then modify the buffer, we lose the checkpoint altogether
                start, end = self.checkpoints.get(action.buffer, (None, None))
                if start is not None and start > self.next_redo:
                    self.checkpoints[action.buffer] = (None, None)
            could_undo = self.can_undo()
            could_redo = self.can_redo()
            self.actions[self.next_redo:] = []
            self.actions.append(action)
            self.next_redo += 1
            if not could_undo:
                self.emit('can-undo', 1)
            if could_redo:
                self.emit('can-redo', 0)
        else:
            self.group.add_action(action)

    def undo(self):
        """Undo an action.

        Raises an AssertionError if the sequence is not undoable.
        """
        assert self.next_redo > 0
        self.busy = True
        buf = self.actions[self.next_redo - 1].buffer
        if self.checkpointed(buf):
            self.emit('checkpointed', buf, False)
        could_redo = self.can_redo()
        self.next_redo -= 1
        actions = self.actions[self.next_redo].undo()
        self.busy = False
        if not self.can_undo():
            self.emit('can-undo', 0)
        if not could_redo:
            self.emit('can-redo', 1)
        if self.checkpointed(buf):
            self.emit('checkpointed', buf, True)
        return actions

    def redo(self):
        """Redo an action.

        Raises and AssertionError if the sequence is not undoable.
        """
        assert self.next_redo < len(self.actions)
        self.busy = True
        buf = self.actions[self.next_redo].buffer
        if self.checkpointed(buf):
            self.emit('checkpointed', buf, False)
        could_undo = self.can_undo()
        a = self.actions[self.next_redo]
        self.next_redo += 1
        actions = a.redo()
        self.busy = False
        if not could_undo:
            self.emit('can-undo', 1)
        if not self.can_redo():
            self.emit('can-redo', 0)
        if self.checkpointed(buf):
            self.emit('checkpointed', buf, True)
        return actions

    def checkpoint(self, buf):
        start = self.next_redo
        while start > 0 and self.actions[start - 1].buffer != buf:
            start -= 1
        end = self.next_redo
        while (end < len(self.actions) - 1 and
               self.actions[end + 1].buffer != buf):
            end += 1
        if end == len(self.actions):
            end = None
        self.checkpoints[buf] = [start, end]
        self.emit('checkpointed', buf, True)

    def checkpointed(self, buf):
        # While the main undo sequence should always have checkpoints
        # recorded, grouped subsequences won't.
        start, end = self.checkpoints.get(buf, (None, None))
        if start is None:
            return False
        if end is None:
            end = len(self.actions)
        return start <= self.next_redo <= end

    def begin_group(self):
        """Group several actions into a single logical action.

        When you wrap several calls to add_action() inside begin_group()
        and end_group(), all the intervening actions are considered
        one logical action. For instance a 'replace' action may be
        implemented as a pair of 'delete' and 'create' actions, but
        undoing should undo both of them.
        """
        if self.busy:
            return

        if self.group:
            self.group.begin_group()
        else:
            buffers = [ref() for ref in self.buffer_refs]
            self.group = UndoSequence(buffers)

    def end_group(self):
        """End a logical group action

        This must always be paired with a begin_group() call. However,
        we don't complain if this is not the case because we rely on
        external libraries (i.e., GTK+ and GtkSourceView) also pairing
        these correctly.

        See also begin_group().
        """
        if self.busy:
            return

        if self.group is None:
            log.warning('Tried to end a non-existent group')
            return

        if self.group.group is not None:
            self.group.end_group()
        else:
            group = self.group
            self.group = None
            # Collapse single action groups
            if len(group.actions) == 1:
                self.add_action(group.actions[0])
            elif len(group.actions) > 1:
                self.add_action(GroupAction(group))

    def abort_group(self):
        """Clear the currently grouped actions

        This discards all actions since the last begin_group() was
        called. Note that it does not actually undo the actions
        themselves.
        """
        if self.busy:
            return

        if self.group is None:
            log.warning('Tried to abort a non-existent group')
            return

        if self.group.group is not None:
            self.group.abort_group()
        else:
            self.group = None

    def in_grouped_action(self):
        return self.group is not None
