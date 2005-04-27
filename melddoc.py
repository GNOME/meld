### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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
import gtk
import os

# Use these to ensure consistent return values.
RESULT_OK, RESULT_ERROR = (0,1)

class MeldDoc(gobject.GObject):
    """Base class for documents in the meld application.
    """

    __gsignals__ = {
        'label-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        'file-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        'create-diff': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'status-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'closed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ()),
    }

    def __init__(self, prefs):
        self.__gobject_init__()
        self.scheduler = task.FifoScheduler()
        self.prefs = prefs
        self.label_text = _("untitled")

    def stop(self):
        if len(self.scheduler.tasks):
            del self.scheduler.tasks[0]

    def _edit_files(self, files):
        if len(files):
            if self.prefs.edit_command_type == "internal":
                for f in files:
                    self.emit("create-diff", (f,))
            elif self.prefs.edit_command_type == "gnome":
                cmd = self.prefs.get_gnome_editor_command(files)
                os.spawnvp(os.P_NOWAIT, cmd[0], cmd)
            elif self.prefs.edit_command_type == "custom":
                cmd = self.prefs.get_custom_editor_command(files)
                os.spawnvp(os.P_NOWAIT, cmd[0], cmd)

    def on_container_delete_event(self, app_quit=0):
        """Called when the docs container is about to close.

           A doc normally returns gtk.RESPONSE_OK but may return
           gtk.RESPONSE_CANCEL which requests the container
           to not delete it. In the special case when the
           app is about to quit, gtk.RESPONSE_CLOSE may be returned
           which instructs the container to quit without any
           more callbacks.
        """
        return gtk.RESPONSE_OK

    def on_container_quit_event(self):
        """Called when the container app is closing.

           The doc should clean up resources, but not block.
        """
        pass

    def on_container_file_changed(self, fname):
        """Called when the container app has modified a file.
        """
        pass

    def on_container_switch_in_event(self, uimanager):
        """Called when the container app switches to this tab.
        """
        pass

    def on_container_switch_out_event(self, uimanager):
        """Called when the container app switches to this tab.
        """
        pass
gobject.type_register(MeldDoc)
