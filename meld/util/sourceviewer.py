### Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>
### Copyright (C) 2010-2011 Kai Willadsen <kai.willadsen@gmail.com>

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

'''Abstraction from sourceview version API incompatibilities
'''

from gi.repository import Gio
from gi.repository import Gtk


class _srcviewer(object):
    # Module name to be imported for the sourceviewer class
    srcviewer_module = None
    # instance of the imported sourceviewer module
    gsv = None

    spaces_flag = 0

    def __init__(self):
        if self.srcviewer_module is not None:
            self.gsv = __import__(self.srcviewer_module)
        self.glm = None
        self.version_check()
        self.GtkTextView = None
        self.GtkTextBuffer = None
        self.overrides()

    def version_check(self):
        raise NotImplementedError

    def overrides(self):
        raise NotImplementedError

    def GtkLanguageManager(self):
        raise NotImplementedError

    def set_highlight_syntax(self, buf, enabled):
        raise NotImplementedError

    def set_tab_width(self, tab, tab_size):
        raise NotImplementedError

    def get_language_from_file(self, filename):
        raise NotImplementedError

    def get_language_from_mime_type(self, mimetype):
        raise NotImplementedError

    def get_language_manager(self):
        if self.glm is None:
            self.glm = self.GtkLanguageManager()
        return self.glm

    def set_language(self, buf, lang):
        raise NotImplementedError


class _gtksourceview2(_srcviewer):
    srcviewer_module = "gtksourceview2"

    def version_check(self):
        raise NotImplementedError

    def overrides(self):
        self.GtkTextView = self.GtkSource.View
        self.GtkTextBuffer = self.GtkSource.Buffer
        self.spaces_flag = self.GtkSource.DrawSpacesFlags.ALL

    def GtkLanguageManager(self):
        return self.GtkSource.LanguageManager()

    def set_tab_width(self, tab, tab_size):
        return tab.set_tab_width(tab_size)

    def set_highlight_syntax(self, buf, enabled):
        return buf.set_highlight_syntax(enabled)

    def get_language_from_file(self, filename):
        f = Gio.File(filename)
        try:
            info = f.query_info(Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE)
        except Gio.Error:
            return None
        content_type = info.get_content_type()
        return self.get_language_manager().guess_language(filename,
                                                          content_type)

    def get_language_from_mime_type(self, mime_type):
        content_type = Gio.content_type_from_mime_type(mime_type)
        return self.get_language_manager().guess_language(None, content_type)

    def set_language(self, buf, lang):
        buf.set_language(lang)


class gtksourceview24(_gtksourceview2):

    def version_check(self):
        if self.GtkSource.pygtksourceview2_version[1] < 4:
            raise ImportError

    def overrides(self):
        _GtkSource.overrides(self)
        viewClass = self.GtkSource.View

        class SourceView(viewClass):

            __gsignals__ = {
                'key-press-event': 'override'
            }

            def do_key_press_event(self, event):
                if event.keyval in (Gdk.KEY_KP_Up, Gdk.KEY_KP_Down,
                                    Gdk.KEY_Up, Gdk.KEY_Down) and \
                   (event.get_state() & Gdk.ModifierType.MOD1_MASK) != 0 and \
                   (event.get_state() & Gdk.ModifierType.SHIFT_MASK) == 0:
                    return True
                return viewClass.do_key_press_event(self, event)

        self.GtkTextView = SourceView


class gtksourceview210(_gtksourceview2):

    def version_check(self):
        if self.GtkSource.pygtksourceview2_version[1] < 10:
            raise ImportError

    def overrides(self):
        _GtkSource.overrides(self)
        Gtk.binding_entry_remove(self.GtkTextView, Gdk.KEY_Up,
                                 Gdk.ModifierType.MOD1_MASK)
        Gtk.binding_entry_remove(self.GtkTextView, Gdk.KEY_KP_Up,
                                 Gdk.ModifierType.MOD1_MASK)
        Gtk.binding_entry_remove(self.GtkTextView, Gdk.KEY_Down,
                                 Gdk.ModifierType.MOD1_MASK)
        Gtk.binding_entry_remove(self.GtkTextView, Gdk.KEY_KP_Down,
                                 Gdk.ModifierType.MOD1_MASK)


class nullsourceview(_srcviewer):
    """Implement the sourceviewer API when no real one is available
    """

    get_language_from_file = lambda *args: None
    set_highlight_syntax = lambda *args: None
    set_language = lambda *args: None
    set_tab_width = lambda *args: None
    get_language_from_mime_type = lambda *args: None

    def overrides(self):
        from gi.repository import GObject
        from gi.repository import Gtk

        class NullTextView(Gtk.TextView):
            set_tab_width = lambda *args: None
            set_show_line_numbers = lambda *args: None
            set_insert_spaces_instead_of_tabs = lambda *args: None
            set_draw_spaces = lambda *args: None
            set_right_margin_position = lambda *args: None
            set_show_right_margin = lambda *args: None
        GObject.type_register(NullTextView)

        self.GtkTextView = NullTextView
        self.GtkTextBuffer = Gtk.TextBuffer

    def version_check(self):
        pass


def _get_srcviewer():
    # for srcv in (gtksourceview210, gtksourceview24):
    #     try:
    #         return srcv()
    #     except ImportError:
    #         pass
    return nullsourceview()


srcviewer = _get_srcviewer()


class MeldSourceView(srcviewer.GtkTextView):
    __gtype_name__ = "MeldSourceView"

    def get_y_for_line_num(self, line):
        buf = self.get_buffer()
        it = buf.get_iter_at_line(line)
        y, h = self.get_line_yrange(it)
        if line >= buf.get_line_count():
            return y + h - 1
        return y

    def get_line_num_for_y(self, y):
        return self.get_line_at_y(y)[0].get_line()
