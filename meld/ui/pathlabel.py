# Copyright (C) 2019 Kai Willadsen <kai.willadsen@gmail.com>
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
import pathlib

from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from meld.conf import _
from meld.melddoc import open_files_external

log = logging.getLogger(__name__)


@Gtk.Template(resource_path='/org/gnome/meld/ui/path-label.ui')
class PathLabel(Gtk.MenuButton):

    __gtype_name__ = 'PathLabel'

    MISSING_FILE_NAME: str = _('Unnamed file')

    full_path_label: Gtk.Entry = Gtk.Template.Child()

    _gfile: Gio.File
    _parent_gfile: Gio.File
    _path_label: str

    def get_file(self) -> Gio.File:
        return self._gfile

    def set_file(self, file: Gio.File) -> None:
        if file == self._gfile:
            return

        try:
            self._update_paths(self._parent_gfile, file)
        except ValueError as e:
            log.warning(f'Error setting GFile: {str(e)}')

    def get_parent_file(self) -> Gio.File:
        return self._parent_gfile

    def set_parent_file(self, parent_file: Gio.File) -> None:
        if parent_file == self._parent_gfile:
            return

        try:
            self._update_paths(parent_file, self._gfile)
        except ValueError as e:
            log.warning(f'Error setting parent GFile: {str(e)}')

    def get_path_label(self) -> str:
        return self._path_label

    gfile = GObject.Property(
        type=Gio.File,
        nick='File being displayed',
        getter=get_file,
        setter=set_file,
    )

    parent_gfile = GObject.Property(
        type=Gio.File,
        nick=(
            'Parent folder of the current file being displayed that '
            'determines where the path display will terminate'
        ),
        getter=get_parent_file,
        setter=set_parent_file,
    )

    path_label = GObject.Property(
        type=str,
        nick='Summarised path label relative to defined parent',
        getter=get_path_label,
    )

    custom_label = GObject.Property(
        type=str,
        nick='Custom label override',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._gfile = None
        self._parent_gfile = None
        self._path_label = None

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

    def do_realize(self):
        # As a workaround for pygobject#341, we delay this binding until
        # realize, at which point the child object is correct.
        self.bind_property(
            'gfile', self.full_path_label, 'text',
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE,
            self.get_display_path,
        )

        return Gtk.MenuButton.do_realize(self)

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

    def _update_paths(self, parent: Gio.File, descendant: Gio.File) -> None:
        # If either of the parent or the main gfiles are not set, the
        # relationship is fine (because it's not yet established).
        if not parent or not descendant:
            self._parent_gfile = parent
            self._gfile = descendant
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

        # When thinking about the segmentation we do here, there are
        # four path components that we care about:
        #
        #  * any path components above the non-common parent
        #  * the earliest non-common parent
        #  * any path components between the actual filename and the
        #    earliest non-common parent
        #  * the actual filename
        #
        # This is easiest to think about with an example of comparing
        # two files in a parallel repository structure (or similar).
        # Let's say that you have two copies of Meld at
        # /home/foo/checkouts/meld and /home/foo/checkouts/meld-new,
        # and you're comparing meld/filediff.py within those checkouts.
        # The components we want would then be (left to right):
        #
        #  ---------------------------------------------
        #  | /home/foo/checkouts | /home/foo/checkouts |
        #  | meld                | meld-new            |
        #  | meld                | meld                |
        #  | filediff.py         | filediff.py         |
        #  ---------------------------------------------
        #
        # Of all of these, the first (the first common parent) is the
        # *only* one that's actually guaranteed to be the same. The
        # second will *always* be different (or won't exist if e.g.,
        # you're comparing files in the same folder or similar). The
        # third component can be basically anything. The fourth
        # components will often be the same but that's not guaranteed.

        base_path_str = None
        elided_path = None

        # FIXME: move all of this (and above) path segmenting logic into a
        # unit-testable helper

        relative_path_str = parent.get_relative_path(descendant_parent)

        if relative_path_str:
            relative_path = pathlib.Path(relative_path_str)

            base_path_str = relative_path.parts[0]
            if len(relative_path.parts) == 1:
                # No directory components, so we have no elided path
                # segment
                elided_path = None
            else:
                base_path_gfile = parent.get_child(base_path_str)
                elided_path = base_path_gfile.get_relative_path(
                    descendant_parent)

        show_parent = not parent.has_parent()
        label_segments = [
            '…' if not show_parent else None,
            base_path_str,
            '…' if elided_path else None,
            descendant.get_basename(),
        ]
        label_text = parent.get_parse_name() if show_parent else ''
        label_text += GLib.build_filenamev([s for s in label_segments if s])

        self._path_label = label_text
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
