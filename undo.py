import gobject

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
        self.actions = []
        self.next_redo = 0
        self.busy = 0

    def can_undo(self):
        return self.next_redo > 0

    def can_redo(self):
        return self.next_redo < len(self.actions)

    def add_action(self, action):
        could_undo = self.can_undo()
        could_redo = self.can_redo()
        self.actions[self.next_redo:] = []
        self.actions.append(action)
        self.next_redo += 1
        if not could_undo:
            self.emit('can-undo', 1)
        if could_redo:
            self.emit('can-redo', 0)

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

    def start_group(self, sequence):
        pass

    def end_group(self, sequence):
        pass

    def abort_group(self, sequence):
        pass

gobject.type_register(UndoSequence)

