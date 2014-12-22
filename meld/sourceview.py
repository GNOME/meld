# Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>
# Copyright (C) 2010-2011, 2013-2014 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import GtkSource

from meld.settings import bind_settings, settings


class LanguageManager(object):

    manager = GtkSource.LanguageManager()

    @classmethod
    def get_language_from_file(cls, filename):
        f = Gio.File.new_for_path(filename)
        try:
            info = f.query_info(Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
                                0, None)
        except GLib.GError:
            return None
        content_type = info.get_content_type()
        return cls.manager.guess_language(filename, content_type)

    @classmethod
    def get_language_from_mime_type(cls, mime_type):
        content_type = Gio.content_type_from_mime_type(mime_type)
        return cls.manager.guess_language(None, content_type)


class MeldSourceView(GtkSource.View):

    __gtype_name__ = "MeldSourceView"

    __gsettings_bindings__ = (
        ('indent-width', 'tab-width'),
        ('insert-spaces-instead-of-tabs', 'insert-spaces-instead-of-tabs'),
        ('draw-spaces', 'draw-spaces'),
        ('wrap-mode', 'wrap-mode'),
    )

    replaced_entries = (
        # We replace the default GtkSourceView undo mechanism
        (Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK),
        (Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK |
            Gdk.ModifierType.SHIFT_MASK),

        # We replace the default line movement behaviour of Alt+Up/Down
        (Gdk.KEY_Up, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Up, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_Down, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Down, Gdk.ModifierType.MOD1_MASK),
        # ...and Alt+Left/Right
        (Gdk.KEY_Left, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Left, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_Right, Gdk.ModifierType.MOD1_MASK),
        (Gdk.KEY_KP_Right, Gdk.ModifierType.MOD1_MASK),
    )

    def __init__(self, *args, **kwargs):
        super(MeldSourceView, self).__init__(*args, **kwargs)
        bind_settings(self)

        binding_set = Gtk.binding_set_find('GtkSourceView')
        for key, modifiers in self.replaced_entries:
            Gtk.binding_entry_remove(binding_set, key, modifiers)

    def late_bind(self):
        settings.bind(
            'show-line-numbers', self, 'show-line-numbers',
            Gio.SettingsBindFlags.DEFAULT)

    def get_y_for_line_num(self, line):
        buf = self.get_buffer()
        it = buf.get_iter_at_line(line)
        y, h = self.get_line_yrange(it)
        if line >= buf.get_line_count():
            return y + h - 1
        return y

    def get_line_num_for_y(self, y):
        return self.get_line_at_y(y)[0].get_line()


class CommitMessageSourceView(GtkSource.View):

    __gtype_name__ = "CommitMessageSourceView"

    __gsettings_bindings__ = (
        ('indent-width', 'tab-width'),
        ('insert-spaces-instead-of-tabs', 'insert-spaces-instead-of-tabs'),
        ('draw-spaces', 'draw-spaces'),
    )
