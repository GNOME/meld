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


from gi.repository import Gdk, Gio, GObject, Gtk

from meld.conf import _
from meld.melddoc import open_files_external


@Gtk.Template(resource_path='/org/gnome/meld/ui/path-label.ui')
class PathLabel(Gtk.MenuButton):

    __gtype_name__ = 'PathLabel'

    full_path_label = Gtk.Template.Child()

    custom_label = GObject.Property(type=str, nick='Custom label override')
    gfile = GObject.Property(type=Gio.File, nick='GFile being displayed')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.bind_property(
            'gfile', self, 'label',
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
        elif self.gfile:
            # TODO: Ideally we'd do some cross-filename summarisation here
            # instead of just showing the basename.
            return self.gfile.get_basename()
        else:
            return _('Unnamed file')

    def get_display_path(self, binding, from_value):
        if from_value:
            return from_value.get_parse_name()
        return ''

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
