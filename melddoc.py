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

import gobject
import task
import undo
import gtk

class MeldDoc(gobject.GObject):
    """Base class for documents in the meld application.
    """

    __gsignals__ = {
        'label-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
    }

    def __init__(self, prefs):
        self.__gobject_init__()
        self.undosequence = undo.UndoSequence()
        self.undosequence_busy = 0
        self.scheduler = task.FifoScheduler()
        self.prefs = prefs
        self.prefs.notify_add(self.on_preference_changed)
        self.num_panes = 0
        self.label_text = "untitled"

    def on_undo_activate(self):
        if self.undosequence.can_undo():
            self.undosequence_busy = 1
            try:
                self.undosequence.undo()
            finally:
                self.undosequence_busy = 0

    def on_redo_activate(self):
        if self.undosequence.can_redo():
            self.undosequence_busy = 1
            try:
                self.undosequence.redo()
            finally:
                self.undosequence_busy = 0
            self.undosequence_busy = 0

    def on_copy_activate(self, *args):
        pass
    def on_cut_activate(self, *args):
        pass
    def on_paste_activate(self, *args):
        pass

    def on_preference_changed(self, key, value):
        pass

    def label_changed(self):
        self.emit("label-changed", self.label_text)

    def _dialog(self, text, messagetype=gtk.MESSAGE_WARNING, buttonstype=gtk.BUTTONS_OK):
        d = gtk.MessageDialog(None,
                gtk.DIALOG_DESTROY_WITH_PARENT,
                messagetype,
                buttonstype,
                '<span weight="bold" size="larger">%s</span>' % text)
        d.set_has_separator(0)
        d.vbox.set_spacing(12)
        hbox = d.vbox.get_children()[0]
        hbox.set_spacing(12)
        d.image.set_alignment(0.5, 0)
        d.image.set_padding(12, 12)
        d.label.set_use_markup(1)
        d.label.set_padding(12, 12)
        ret = d.run()
        d.destroy()
        return ret

gobject.type_register(MeldDoc)
