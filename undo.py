import gobject

################################################################################
#
# GroupAction
#
################################################################################
class GroupAction:
    def __init__(self, seq):
        self.seq = seq
    def undo(self):
        while self.seq.can_undo():
            self.seq.undo()
    def redo(self):
        while self.seq.can_redo():
            self.seq.redo()
################################################################################
#
# UndoSequence
#
################################################################################
class UndoSequence(gobject.GObject):
    __gsignals__ = {
        'can-undo': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_BOOLEAN,)),
        'can-redo': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_BOOLEAN,))
    }

    def __init__(self):
        self.__gobject_init__()
        self.clear()

    def clear(self):
        if hasattr(self, "group"):
            assert self.group == None
        self.actions = []
        self.next_redo = 0
        self.group = None

    def can_undo(self):
        return self.next_redo > 0

    def can_redo(self):
        return self.next_redo < len(self.actions)

    def add_action(self, action):
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
        assert self.next_redo > 0
        could_redo = self.can_redo()
        self.next_redo -= 1
        self.actions[self.next_redo].undo()
        if not self.can_undo():
            self.emit('can-undo', 0)
        if not could_redo:
            self.emit('can-redo', 1)

    def redo(self):
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
        if self.group:
            self.group.start_group() 
        else:
            self.group = UndoSequence()

    def end_group(self):
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
        assert self.group != None
        if self.group.group != None:
            self.group.abort_group()
        else:
            self.group = None

gobject.type_register(UndoSequence)

