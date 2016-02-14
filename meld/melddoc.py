# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2011-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

import logging
import pipes
import shlex
import string
import subprocess
import sys

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gio
from gi.repository import Gtk

from . import task

from meld.conf import _
from meld.settings import settings

log = logging.getLogger(__name__)


def make_custom_editor_command(path, line=0):
    custom_command = settings.get_string('custom-editor-command')
    fmt = string.Formatter()
    replacements = [tok[1] for tok in fmt.parse(custom_command)]

    if not any(replacements):
        return [custom_command, path]
    elif not all(r in (None, 'file', 'line') for r in replacements):
        log.error("Unsupported fields found", )
        return [custom_command, path]
    else:
        cmd = custom_command.format(file=pipes.quote(path), line=line)
    return shlex.split(cmd)


# TODO: Consider use-cases for states in gedit-enum-types.c
STATE_NORMAL, STATE_CLOSING, STATE_SAVING_ERROR, NUM_STATES = range(4)


class MeldDoc(GObject.GObject):
    """Base class for documents in the meld application.
    """

    __gsignals__ = {
        'label-changed':        (GObject.SignalFlags.RUN_FIRST, None,
                                 (GObject.TYPE_STRING, GObject.TYPE_STRING)),
        'file-changed':         (GObject.SignalFlags.RUN_FIRST, None,
                                 (GObject.TYPE_STRING,)),
        'create-diff':          (GObject.SignalFlags.RUN_FIRST, None,
                                 (GObject.TYPE_PYOBJECT,
                                  GObject.TYPE_PYOBJECT)),
        'status-changed':       (GObject.SignalFlags.RUN_FIRST, None,
                                 (GObject.TYPE_PYOBJECT,)),
        'current-diff-changed': (GObject.SignalFlags.RUN_FIRST, None,
                                 ()),
        'next-diff-changed':    (GObject.SignalFlags.RUN_FIRST, None,
                                 (bool, bool)),
        'close': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        'state-changed': (GObject.SignalFlags.RUN_FIRST, None, (int, int)),
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.scheduler = task.FifoScheduler()
        self.num_panes = 0
        self.label_text = _("untitled")
        self.tooltip_text = _("untitled")
        self.main_actiongroup = None
        self._state = STATE_NORMAL

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        if value == self._state:
            return
        self.emit('state-changed', self._state, value)
        self._state = value

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
        query_attrs = ",".join((Gio.FILE_ATTRIBUTE_STANDARD_TYPE,
                                Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE))

        def os_open(path, uri):
            if not path:
                return
            if sys.platform == "win32":
                subprocess.Popen(["start", path], shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                Gtk.show_uri(Gdk.Screen.get_default(), uri,
                             Gtk.get_current_event_time())

        def open_cb(source, result, *data):
            info = source.query_info_finish(result)
            file_type = info.get_file_type()
            path, uri = source.get_path(), source.get_uri()
            if file_type == Gio.FileType.DIRECTORY:
                os_open(path, uri)
            elif file_type == Gio.FileType.REGULAR:
                content_type = info.get_content_type()
                # FIXME: Content types are broken on Windows with current gio
                if Gio.content_type_is_a(content_type, "text/plain") or \
                        sys.platform == "win32":
                    if settings.get_boolean('use-system-editor'):
                        gfile = Gio.File.new_for_path(path)
                        if sys.platform == "win32":
                            handler = gfile.query_default_handler(None)
                            result = handler.launch([gfile], None)
                        else:
                            uri = gfile.get_uri()
                            Gio.AppInfo.launch_default_for_uri(
                                uri, None)
                    else:
                        editor = make_custom_editor_command(path, line)
                        if editor:
                            # TODO: If the editor is badly set up, this fails
                            # silently
                            subprocess.Popen(editor)
                        else:
                            os_open(path, uri)
                else:
                    os_open(path, uri)
            else:
                # TODO: Add some kind of 'failed to open' notification
                pass

        for f in [Gio.File.new_for_path(s) for s in selected]:
            f.query_info_async(query_attrs, 0, GLib.PRIORITY_LOW, None,
                               open_cb, None)

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
        action_groups = uimanager.get_action_groups()
        self.main_actiongroup = [
            a for a in action_groups if a.get_name() == "MainActions"][0]
        uimanager.ensure_update()
        if hasattr(self, "focus_pane") and self.focus_pane:
            self.scheduler.add_task(self.focus_pane.grab_focus)

    def on_container_switch_out_event(self, uimanager):
        """Called when the container app switches away from this tab.
        """
        uimanager.remove_action_group(self.actiongroup)
        uimanager.remove_ui(self.ui_merge_id)
        self.main_actiongroup = None
        self.popup_menu = None
        self.ui_merge_id = None

    def on_delete_event(self):
        """Called when the docs container is about to close.

        A doc normally returns Gtk.ResponseType.OK, but may instead return
        Gtk.ResponseType.CANCEL to request that the container not delete it.
        """
        return Gtk.ResponseType.OK
