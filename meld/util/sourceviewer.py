# Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>
# Copyright (C) 2010-2011, 2013 Kai Willadsen <kai.willadsen@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.

# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GtkSource


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

    # TODO: Figure out what bindings we need to add and remove for 3

        # Some sourceviews bind their own undo mechanism, which we replace
        # Gtk.binding_entry_remove(GtkSource.View, Gdk.KEY_z,
        #                          Gdk.ModifierType.CONTROL_MASK)
        # Gtk.binding_entry_remove(GtkSource.View, Gdk.KEY_z,
        #                          Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)

        # Gtk.binding_entry_remove(GtkSource.View, Gdk.KEY_Up,
        #                          Gdk.ModifierType.MOD1_MASK)
        # Gtk.binding_entry_remove(GtkSource.View, Gdk.KEY_KP_Up,
        #                          Gdk.ModifierType.MOD1_MASK)
        # Gtk.binding_entry_remove(GtkSource.View, Gdk.KEY_Down,
        #                          Gdk.ModifierType.MOD1_MASK)
        # Gtk.binding_entry_remove(GtkSource.View, Gdk.KEY_KP_Down,
        #                          Gdk.ModifierType.MOD1_MASK)

    def get_y_for_line_num(self, line):
        buf = self.get_buffer()
        it = buf.get_iter_at_line(line)
        y, h = self.get_line_yrange(it)
        if line >= buf.get_line_count():
            return y + h - 1
        return y

    def get_line_num_for_y(self, y):
        return self.get_line_at_y(y)[0].get_line()

    def set_draw_spaces(self, draw):
        spaces_flag = GtkSource.DrawSpacesFlags.ALL if draw else 0
        super(MeldSourceView, self).set_draw_spaces(spaces_flag)
