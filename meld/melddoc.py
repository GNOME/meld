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

import enum
import logging
import os
import pipes
import shlex
import string
import subprocess
import sys
from typing import List, Optional, Sequence

from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from meld.conf import _
from meld.recent import RecentType
from meld.settings import settings
from meld.task import FifoScheduler

log = logging.getLogger(__name__)


def make_custom_editor_command(path: str, line: int = 0) -> Sequence[str]:
    custom_command = settings.get_string('custom-editor-command')
    fmt = string.Formatter()
    replacements = [tok[1] for tok in fmt.parse(custom_command)]

    if not any(replacements):
        return [custom_command, path]
    elif not all(r in (None, 'file', 'line') for r in replacements):
        log.error("Unsupported fields found")
        return [custom_command, path]
    else:
        cmd = custom_command.format(file=pipes.quote(path), line=line)
    return shlex.split(cmd)


def open_files_external(
        paths: Optional[List[str]] = None, *,
        gfiles: Optional[List[Gio.File]] = None,
        line: int = 0) -> None:

    def os_open(path: str, uri: str):
        if not path:
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            Gtk.show_uri(
                Gdk.Screen.get_default(), uri, Gtk.get_current_event_time())

    def open_cb(source, result, *data):
        info = source.query_info_finish(result)
        file_type = info.get_file_type()
        path, uri = source.get_path(), source.get_uri()
        if file_type == Gio.FileType.DIRECTORY:
            os_open(path, uri)
        elif file_type == Gio.FileType.REGULAR:
            content_type = info.get_content_type()
            # FIXME: Content types are broken on Windows with current gio
            # If we can't access a content type, assume it's text.
            if not content_type or Gio.content_type_is_a(
                    content_type, "text/plain"):
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

    query_attrs = ",".join((Gio.FILE_ATTRIBUTE_STANDARD_TYPE,
                            Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE))

    if not gfiles:
        gfiles = [Gio.File.new_for_path(s) for s in paths]

    for f in gfiles:
        f.query_info_async(
            query_attrs, Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_LOW,
            None, open_cb, None)


class ComparisonState(enum.IntEnum):
    # TODO: Consider use-cases for states in gedit-enum-types.c
    Normal = 0
    Closing = 1
    SavingError = 2


class LabeledObjectMixin(GObject.GObject):

    label_text = _("untitled")
    tooltip_text = None

    @GObject.Signal
    def label_changed(self, label_text: str, tooltip_text: str) -> None:
        ...


class MeldDoc(LabeledObjectMixin, GObject.GObject):
    """Base class for documents in the meld application.
    """

    @GObject.Signal(name='close')
    def close_signal(self, exit_code: int) -> None:
        ...

    @GObject.Signal(name='create-diff')
    def create_diff_signal(
            self, gfiles: object, options: object) -> None:
        ...

    @GObject.Signal('file-changed')
    def file_changed_signal(self, path: str) -> None:
        ...

    @GObject.Signal
    def tab_state_changed(self, old_state: int, new_state: int) -> None:
        ...

    @GObject.Signal(
        name='move-diff',
        flags=GObject.SignalFlags.RUN_FIRST | GObject.SignalFlags.ACTION,
    )
    def move_diff(self, direction: int) -> None:
        self.next_diff(direction)

    def __init__(self) -> None:
        super().__init__()
        self.scheduler = FifoScheduler()
        self.num_panes = 0
        self.view_action_group = Gio.SimpleActionGroup()
        self._state = ComparisonState.Normal

    @property
    def state(self) -> ComparisonState:
        return self._state

    @state.setter
    def state(self, value: ComparisonState) -> None:
        if value == self._state:
            return
        self.tab_state_changed.emit(self._state, value)
        self._state = value

    def get_comparison(self) -> RecentType:
        """Get the comparison type and URI(s) being compared"""
        pass

    def action_stop(self, *args) -> None:
        if self.scheduler.tasks_pending():
            self.scheduler.remove_task(self.scheduler.get_current_task())

    def on_file_changed(self, filename: str):
        pass

    def set_labels(self, lst: Sequence[str]) -> None:
        pass

    def get_action_state(self, action_name: str):
        action = self.view_action_group.lookup_action(action_name)
        if not action:
            log.error(f'No action {action_name!r} found')
            return
        return action.get_state().unpack()

    def set_action_state(self, action_name: str, state) -> None:
        # TODO: Try to do GLib.Variant things here instead of in callers
        action = self.view_action_group.lookup_action(action_name)
        if not action:
            log.error(f'No action {action_name!r} found')
            return
        action.set_state(state)

    def set_action_enabled(self, action_name: str, enabled: bool) -> None:
        action = self.view_action_group.lookup_action(action_name)
        if not action:
            log.error(f'No action {action_name!r} found')
            return
        action.set_enabled(enabled)

    def on_container_switch_in_event(self, window):
        """Called when the container app switches to this tab"""

        window.insert_action_group(
            'view', getattr(self, 'view_action_group', None))

        if hasattr(self, "get_filter_visibility"):
            text, folder, vc = self.get_filter_visibility()
        else:
            text, folder, vc = False, False, False

        if hasattr(self, "get_conflict_visibility"):
            show_conflict_actions = self.get_conflict_visibility()
        else:
            show_conflict_actions = False

        window.text_filter_button.set_visible(text)
        window.folder_filter_button.set_visible(folder)
        window.vc_filter_button.set_visible(vc)

        window.next_conflict_button.set_visible(show_conflict_actions)
        window.previous_conflict_button.set_visible(show_conflict_actions)

        if hasattr(self, "focus_pane") and self.focus_pane:
            self.scheduler.add_task(self.focus_pane.grab_focus)

    def on_container_switch_out_event(self, window):
        """Called when the container app switches away from this tab"""

        window.insert_action_group('view', None)

    # FIXME: Here and in subclasses, on_delete_event are not real GTK+
    # event handlers, and should be renamed.
    def on_delete_event(self) -> Gtk.ResponseType:
        """Called when the docs container is about to close.

        A doc normally returns Gtk.ResponseType.OK, but may instead return
        Gtk.ResponseType.CANCEL to request that the container not delete it.
        """
        return Gtk.ResponseType.OK
