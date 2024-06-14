# Copyright (C) 2019-2021 Kai Willadsen <kai.willadsen@gmail.com>
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
from typing import Optional

from gi.repository import Gdk, Gio, GObject, Gtk, Pango

from meld.conf import _
from meld.externalhelpers import open_files_external
from meld.iohelpers import (
    format_home_relative_path,
    format_parent_relative_path,
)

log = logging.getLogger(__name__)


@Gtk.Template(resource_path='/org/gnome/meld/ui/path-label.ui')
class PathLabel(Gtk.MenuButton):

    __gtype_name__ = 'PathLabel'

    MISSING_FILE_NAME: str = _('Unnamed file')

    full_path_label: Gtk.Entry = Gtk.Template.Child()

    _gfile: Optional[Gio.File]
    _parent_gfile: Optional[Gio.File]
    _path_label: Optional[str]
    _icon_name: Optional[str]

    def __get_file(self) -> Optional[Gio.File]:
        return self._gfile

    def __set_file(self, file: Optional[Gio.File]) -> None:
        if file == self._gfile:
            return

        try:
            self._update_paths(self._parent_gfile, file)
        except ValueError as e:
            log.warning(f'Error setting GFile: {str(e)}')

    def __get_parent_file(self) -> Optional[Gio.File]:
        return self._parent_gfile

    def __set_parent_file(self, parent_file: Optional[Gio.File]) -> None:
        if parent_file == self._parent_gfile:
            return

        try:
            self._update_paths(parent_file, self._gfile)
        except ValueError as e:
            log.warning(f'Error setting parent GFile: {str(e)}')

    def __get_path_label(self) -> Optional[str]:
        return self._path_label

    def __get_icon_name(self) -> Optional[str]:
        return self._icon_name

    def __set_icon_name(self, icon_name: Optional[str]) -> None:
        if icon_name == self._icon_name:
            return

        if icon_name:
            image = Gtk.Image.new_from_icon_name(
                icon_name, Gtk.IconSize.BUTTON)
            self.set_image(image)
            self.props.always_show_image = True
        else:
            self.set_image(None)
            self.props.always_show_image = False

    gfile = GObject.Property(
        type=Gio.File,
        nick='File being displayed',
        getter=__get_file,
        setter=__set_file,
    )

    parent_gfile = GObject.Property(
        type=Gio.File,
        nick=(
            'Parent folder of the current file being displayed that '
            'determines where the path display will terminate'
        ),
        getter=__get_parent_file,
        setter=__set_parent_file,
    )

    path_label = GObject.Property(
        type=str,
        nick='Summarised path label relative to defined parent',
        getter=__get_path_label,
    )

    icon_name = GObject.Property(
        type=str,
        nick='The name of the icon to display',
        getter=__get_icon_name,
        setter=__set_icon_name,
    )

    custom_label = GObject.Property(
        type=str,
        nick='Custom label override',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.drag_dest_set(
            Gtk.DestDefaults.MOTION | Gtk.DestDefaults.HIGHLIGHT |
            Gtk.DestDefaults.DROP,
            None,
            Gdk.DragAction.COPY,
        )
        self.drag_dest_add_uri_targets()

        self._gfile = None
        self._parent_gfile = None
        self._path_label = None
        self._icon_name = None

        self.bind_property(
            'path_label', self, 'label',
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
            self.get_display_label,
        )
        self.bind_property(
            'custom_label', self, 'label',
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
            self.get_display_label,
        )
        self.bind_property(
            'gfile', self.full_path_label, 'text',
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
            self.get_display_path,
        )

        action_group = Gio.SimpleActionGroup()

        actions = (
            ('copy-full-path', self.action_copy_full_path),
            ('open-folder', self.action_open_folder),
        )
        for (name, callback) in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            action_group.add_action(action)

        self.insert_action_group('widget', action_group)

        # GtkButton recreates its GtkLabel child whenever the label
        # prop changes, so we need this notify callback.
        self.connect('notify::label', self.label_changed_cb)

    def label_changed_cb(self, *args):
        # Our label needs ellipsization to avoid forcing minimum window
        # sizes for long filenames. This child iteration hack is
        # required as GtkButton has no label access.
        for child in self.get_children():
            if isinstance(child, Gtk.Label):
                child.set_ellipsize(Pango.EllipsizeMode.MIDDLE)

    def get_display_label(self, binding, from_value) -> str:
        if self.custom_label:
            return self.custom_label
        elif self.path_label:
            return self.path_label
        else:
            return self.MISSING_FILE_NAME

    def get_display_path(self, binding, from_value):
        if from_value:
            return from_value.get_parse_name()
        return ''

    def _update_paths(
        self,
        parent: Optional[Gio.File],
        descendant: Optional[Gio.File],
    ) -> None:
        # If either of the parent or the main gfiles are not set, the
        # relationship is fine (because it's not yet established).
        if not parent or not descendant:
            self._parent_gfile = parent
            self._gfile = descendant

            # If we have no parent yet but have a descendant, we'll use
            # the descendant name as the better-than-nothing label.
            if descendant:
                self._path_label = format_home_relative_path(descendant)
                self.notify('path_label')
            return

        descendant_parent = descendant.get_parent()
        if not descendant_parent:
            raise ValueError(
                f'Path {descendant.get_path()} has no parent')

        descendant_or_equal = bool(
            parent.equal(descendant_parent) or
            parent.get_relative_path(descendant_parent),
        )

        if not descendant_or_equal:
            raise ValueError(
                f'Path {descendant.get_path()} is not a descendant '
                f'of {parent.get_path()}')

        self._parent_gfile = parent
        self._gfile = descendant

        self._path_label = format_parent_relative_path(parent, descendant)
        self.notify('path_label')

    def action_copy_full_path(self, *args):
        if not self.gfile:
            return

        path = self.gfile.get_path() or self.gfile.get_uri()
        clip = Gtk.Clipboard.get_default(Gdk.Display.get_default())
        clip.set_text(path, -1)
        clip.store()

    def action_open_folder(self, *args):
        if not self.gfile:
            return

        parent = self.gfile.get_parent()
        if parent:
            open_files_external(gfiles=[parent])
