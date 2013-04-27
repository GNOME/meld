### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2011 Kai Willadsen <kai.willadsen@gmail.com>

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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
### USA.


import subprocess
import sys

import gobject
import gio
import gtk

from . import task

from gettext import gettext as _


class MeldDoc(gobject.GObject):
    """Base class for documents in the meld application.
    """

    __gsignals__ = {
        'label-changed':        (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                                 (gobject.TYPE_STRING, gobject.TYPE_STRING)),
        'file-changed':         (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                                 (gobject.TYPE_STRING,)),
        'create-diff':          (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                                 (gobject.TYPE_PYOBJECT,
                                  gobject.TYPE_PYOBJECT)),
        'status-changed':       (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                                 (gobject.TYPE_PYOBJECT,)),
        'current-diff-changed': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                                 ()),
        'next-diff-changed':    (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                                 (bool, bool)),
    }

    def __init__(self, prefs):
        gobject.GObject.__init__(self)
        self.scheduler = task.FifoScheduler()
        self.prefs = prefs
        self.prefs.notify_add(self.on_preference_changed)
        self.num_panes = 0
        self.label_text = _("untitled")
        self.tooltip_text = _("untitled")
        self.status_info_labels = []

    def get_info_widgets(self):
        return self.status_info_labels

    def get_comparison(self):
        """Get the comparison type and path(s) being compared"""
        pass

    def save(self):
        pass

    def save_as(self):
        pass

    def stop(self):
        if self.scheduler.tasks_pending():
            self.scheduler.remove_task(self.scheduler.get_current_task())

    def _open_files(self, selected, line=0):
        query_attrs = ",".join((gio.FILE_ATTRIBUTE_STANDARD_TYPE,
                                gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE))

        def os_open(path):
            if not path:
                return
            if sys.platform == "win32":
                subprocess.Popen(["start", path], shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])

        def open_cb(source, result, *data):
            info = source.query_info_finish(result)
            file_type = info.get_file_type()
            if file_type == gio.FILE_TYPE_DIRECTORY:
                os_open(source.get_path())
            elif file_type == gio.FILE_TYPE_REGULAR:
                content_type = info.get_content_type()
                path = source.get_path()
                # FIXME: Content types are broken on Windows with current gio
                if gio.content_type_is_a(content_type, "text/plain") or \
                        sys.platform == "win32":
                    editor = self.prefs.get_editor_command(path, line)
                    if editor:
                        subprocess.Popen(editor)
                    else:
                        os_open(path)
                else:
                    os_open(path)
            else:
                # TODO: Add some kind of 'failed to open' notification
                pass

        for f in [gio.File(s) for s in selected]:
            f.query_info_async(query_attrs, open_cb)

    def open_external(self):
        pass

    def on_refresh_activate(self, *extra):
        pass

    def on_find_activate(self, *extra):
        pass

    def on_find_next_activate(self, *extra):
        pass

    def on_find_previous_activate(self, *extra):
        pass

    def on_replace_activate(self, *extra):
        pass

    def on_preference_changed(self, key, value):
        pass

    def on_file_changed(self, filename):
        pass

    def label_changed(self):
        self.emit("label-changed", self.label_text, self.tooltip_text)

    def set_labels(self, lst):
        pass

    def on_container_switch_in_event(self, uimanager):
        """Called when the container app switches to this tab.
        """
        self.ui_merge_id = uimanager.add_ui_from_file(self.ui_file)
        uimanager.insert_action_group(self.actiongroup, -1)
        self.popup_menu = uimanager.get_widget("/Popup")
        uimanager.ensure_update()
        if hasattr(self, "focus_pane") and self.focus_pane:
            self.scheduler.add_task(self.focus_pane.grab_focus)

    def on_container_switch_out_event(self, uimanager):
        """Called when the container app switches away from this tab.
        """
        uimanager.remove_action_group(self.actiongroup)
        uimanager.remove_ui(self.ui_merge_id)

    def on_delete_event(self, appquit=0):
        """Called when the docs container is about to close.

        A doc normally returns gtk.RESPONSE_OK, but may instead return
        gtk.RESPONSE_CANCEL to request that the container not delete it.
        """
        return gtk.RESPONSE_OK
