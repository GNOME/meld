### Copyright (C) 2002-2003 Stephen Kennedy <steve9000@users.sf.net>

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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

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

import gobject

class GroupAction(object):
    """A group action combines several actions into one logical action.
    """
    def __init__(self, seq):
        self.seq = seq
    def undo(self):
        while self.seq.can_undo():
            self.seq.undo()
    def redo(self):
        while self.seq.can_redo():
            self.seq.redo()

class UndoSequence(gobject.GObject):
    """A manager class for operations which can be undone/redone.
    """

    __gsignals__ = {
        'can-undo': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_BOOLEAN,)),
        'can-redo': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_BOOLEAN,))
    }

    def __init__(self):
        """Create an empty UndoSequence.
        """
        self.__gobject_init__()
        self.actions = []
        self.next_redo = 0
        self.group = None

    def clear(self):
        """Remove all undo and redo actions from this sequence

        If the sequence was previously able to undo and/or redo, the
        'can-undo' and 'can-redo' signals are emitted.

        Raises an AssertionError if a group is in progress.
        """

        if hasattr(self, "group"):
            assert self.group == None
        if self.can_undo():
            self.emit('can-undo', 0)
        if self.can_redo():
            self.emit('can-redo', 0)
        self.actions = []
        self.next_redo = 0
        self.group = None

    def can_undo(self):
        """Return if an undo is possible.
        """
        return self.next_redo > 0

    def can_redo(self):
        """Return if a redo is possible.
        """
        return self.next_redo < len(self.actions)

    def add_action(self, action):
        """Add an action to the undo list.

        Arguments:

        action -- A class with two callable attributes: 'undo' and 'redo'
                  which are called by this sequence during an undo or redo.
        """
        if self.group == None:
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
        could_redo = self.can_redo()
        self.next_redo -= 1
        self.actions[self.next_redo].undo()
        if not self.can_undo():
            self.emit('can-undo', 0)
        if not could_redo:
            self.emit('can-redo', 1)

    def redo(self):
        """Redo an action.
        
        Raises and AssertionError if the sequence is not undoable.
        """
        assert self.next_redo < len(self.actions)
        could_undo = self.can_undo()
        a = self.actions[self.next_redo]
        self.next_redo += 1
        a.redo()
        if not could_undo:
            self.emit('can-undo', 1)
        if not self.can_redo():
            self.emit('can-redo', 0)

    def begin_group(self):
        """Group several actions into a single logical action.

        Whey you Wrap several calls to add_action() inside begin_group()
        and end_group(), all the intervening actions are considered
        one logical action. For instance a 'replace' action may be
        implemented as a pair of 'delete' and 'create' actions, but
        undoing should undo both of them.
        """
        if self.group:
            self.group.begin_group() 
        else:
            self.group = UndoSequence()

    def end_group(self):
        """End a logical group action. See also begin_group().
        
        Raises an AssertionError if there was not a matching call to
        begin_group().
        """
        assert self.group != None
        if self.group.group != None:
            self.group.end_group()
        else:
            group = self.group
            self.group = None
            if len(group.actions) == 1: # collapse 
                self.add_action( group.actions[0] )
            elif len(group.actions) > 1:
                self.add_action( GroupAction(group) )

    def abort_group(self):
        """Revert the sequence to the state before begin_group() was called.
        
        Raises an AssertionError if there was no a matching call to begin_group().
        """
        assert self.group != None
        if self.group.group != None:
            self.group.abort_group()
        else:
            self.group = None

gobject.type_register(UndoSequence)

