# Copyright (C) 2019-2024 Kai Willadsen <kai.willadsen@gmail.com>
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
from typing import Any

from gi.repository import Gio, GObject, Gtk

from meld.archivehelpers import get_mount_for_path
from meld.conf import _
from meld.iohelpers import (
    format_home_relative_path,
    format_mount_relative_path,
    format_parent_relative_path,
)

log = logging.getLogger(__name__)


@Gtk.Template(resource_path="/org/gnome/meld/ui/path-label.ui")
class PathLabel(Gtk.MenuButton):
    __gtype_name__ = "PathLabel"

    MISSING_FILE_NAME: str = _("Unnamed file")

    file_launcher: Gtk.FileLauncher = Gtk.Template.Child()
    full_path_label: Gtk.Entry = Gtk.Template.Child()
    label_widget: Gtk.Label = Gtk.Template.Child()

    _gfile: Gio.File | None
    _parent_gfile: Gio.File | None
    _path_label: str | None
    _icon_name: str | None

    def __get_file(self) -> Gio.File | None:
        return self._gfile

    def __set_file(self, file: Gio.File | None) -> None:
        if file == self._gfile:
            return

        try:
            self._update_paths(self._parent_gfile, file)
        except ValueError as e:
            log.warning(f"Error setting GFile: {e!s}")

    def __get_parent_file(self) -> Gio.File | None:
        return self._parent_gfile

    def __set_parent_file(self, parent_file: Gio.File | None) -> None:
        if parent_file == self._parent_gfile:
            return

        try:
            self._update_paths(parent_file, self._gfile)
        except ValueError as e:
            log.warning(f"Error setting parent GFile: {e!s}")

    def __get_path_label(self) -> str | None:
        return self._path_label

    gfile = GObject.Property(
        type=Gio.File,
        nick="File being displayed",
        getter=__get_file,
        setter=__set_file,
    )

    parent_gfile = GObject.Property(
        type=Gio.File,
        nick=(
            "Parent folder of the current file being displayed that "
            "determines where the path display will terminate"
        ),
        getter=__get_parent_file,
        setter=__set_parent_file,
    )

    path_label = GObject.Property(
        type=str,
        nick="Summarised path label relative to defined parent",
        getter=__get_path_label,
    )

    custom_label = GObject.Property(
        type=str,
        nick="Custom label override",
    )
    empty_label = GObject.Property(type=str, nick="Empty label placeholder")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._gfile = None
        self._parent_gfile = None
        self._path_label = None
        self._icon_name = None

        self.bind_property(
            "path_label",
            self.label_widget,
            "label",
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
            self.get_display_label,
        )
        self.bind_property(
            "custom_label",
            self.label_widget,
            "label",
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
            self.get_display_label,
        )
        self.bind_property(
            "gfile",
            self.full_path_label,
            "text",
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
            self.get_display_path,
        )
        self.bind_property(
            "gfile", self.file_launcher, "file", GObject.BindingFlags.DEFAULT
        )

        action_group = Gio.SimpleActionGroup()

        actions = (
            ("copy-full-path", self.action_copy_full_path),
            ("open-folder", self.action_open_folder),
        )
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            action_group.add_action(action)

        self.insert_action_group("widget", action_group)

    def get_display_label(self, binding, from_value) -> str:
        if self.custom_label:
            return self.custom_label
        elif self.path_label:
            return self.path_label
        elif self.props.empty_label:
            return self.props.empty_label
        else:
            return self.MISSING_FILE_NAME

    def get_display_path(self, binding, from_value):
        if from_value:
            return from_value.get_parse_name()
        return ""

    def _format_path(self) -> str | None:
        if not self._gfile:
            return None

        if mount := get_mount_for_path(self._gfile):
            return format_mount_relative_path(mount, self._gfile)

        if self._parent_gfile:
            return format_parent_relative_path(self._parent_gfile, self._gfile)

        # If we have no parent yet but have a descendant, we'll use
        # the descendant name as the better-than-nothing label.
        return format_home_relative_path(self._gfile)

    def _update_paths(
        self,
        parent: Gio.File | None,
        descendant: Gio.File | None,
    ) -> None:
        # If either of the parent or the main gfiles are not set, the
        # relationship is fine (because it's not yet established).
        if not parent or not descendant:
            self._parent_gfile = parent
            self._gfile = descendant

            self._path_label = self._format_path()
            self.notify("path_label")
            return

        descendant_parent = descendant.get_parent()
        if not descendant_parent:
            raise ValueError(f"Path {descendant.get_path()} has no parent")

        descendant_or_equal = bool(
            parent.equal(descendant_parent)
            or parent.get_relative_path(descendant_parent),
        )

        if not descendant_or_equal:
            raise ValueError(
                f"Path {descendant.get_path()} is not a descendant "
                f"of {parent.get_path()}"
            )

        self._parent_gfile = parent
        self._gfile = descendant

        self._path_label = self._format_path()
        self.notify("path_label")

    def action_copy_full_path(self, *args: Any) -> None:
        if not self.gfile:
            return

        path = self.gfile.get_path() or self.gfile.get_uri()
        self.get_clipboard().set(path)

    def action_open_folder(self, *args: Any) -> None:
        if not self.gfile:
            return

        self.file_launcher.open_containing_folder()
