### Copyright (C) 2009 Vincent Legoll <vincent.legoll@gmail.com>

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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

'''Abstraction from sourceview version API incompatibilities
'''

import os

class _srcviewer(object):
    # Module name to be imported for the sourceviewer class
    srcviewer_module = None
    # instance of the imported sourceviewer module
    gsv = None

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
    def get_language_from_file(self, filename):
        raise NotImplementedError
    def set_highlight(self, buf, enabled):
        raise NotImplementedError
    def set_tab_width(self, tab, tab_size):
        raise NotImplementedError
    def get_language_from_mime_type(self, mimetype):
        raise NotImplementedError

    def get_language_manager(self):
        if self.glm is None:
            self.glm = self.GtkLanguageManager()
        return self.glm

    def set_highlighting_enabled(self, buf, gsl, enabled):
        if enabled:
            if gsl:
                buf.set_language(gsl)
            else:
                enabled = False
        self.set_highlight(buf, enabled)

    def set_highlighting_enabled_from_mimetype(self, buf, mimetype, enabled):
        self.set_highlighting_enabled(buf, self.get_language_from_mime_type(mimetype), enabled)

    def set_highlighting_enabled_from_file(self, buf, fname, enabled):
        self.set_highlighting_enabled(buf, self.get_language_from_file(os.path.abspath(fname)), enabled)

class sourceview(_srcviewer):
    srcviewer_module = "sourceview"

    def version_check(self):
        # ImportError exceptions are caught, so we
        # won't use 'sourceview' without gnomevfs
        import gnomevfs
        self.gvfs = gnomevfs

    def overrides(self):
        self.GtkTextView = self.gsv.SourceView
        self.GtkTextBuffer = self.gsv.SourceBuffer

    def GtkLanguageManager(self):
        return self.gsv.SourceLanguagesManager()

    def set_tab_width(self, tab, tab_size):
        return tab.set_tabs_width(tab_size)

    def set_highlight(self, buf, enabled):
        return buf.set_highlight(enabled)

    def get_language_from_mime_type(self, mime_type):
        return self.get_language_manager().get_language_from_mime_type(mime_type)

    def get_language_from_file(self, filename):
        mime_type = self.gvfs.get_mime_type(
                self.gvfs.make_uri_from_input(os.path.abspath(filename)))
        return self.get_language_from_mime_type(mime_type)

class gtksourceview(sourceview):
    srcviewer_module = "gtksourceview"

class _gtksourceview2(_srcviewer):
    srcviewer_module = "gtksourceview2"

    def version_check(self):
        raise NotImplementedError

    def overrides(self):
        self.GtkTextView = self.gsv.View
        self.GtkTextBuffer = self.gsv.Buffer

    def GtkLanguageManager(self):
        return self.gsv.LanguageManager()

    def set_tab_width(self, tab, tab_size):
        return tab.set_tab_width(tab_size)

    def set_highlight(self, buf, enabled):
        return buf.set_highlight_syntax(enabled)

    def get_language_from_file(self, filename):
        raise NotImplementedError

    def get_language_from_mime_type(self, mime_type):
        for idl in self.get_language_manager().get_language_ids():
            lang = self.get_language_manager().get_language(idl)
            for mimetype in lang.get_mime_types():
                if mime_type == mimetype:
                    return lang
        return None

class gtksourceview22(_gtksourceview2):

    def version_check(self):
        if self.gsv.pygtksourceview2_version[1] > 2:
            raise ImportError

    def get_language_from_file(self, filename):
        from fnmatch import fnmatch
        for idl in self.get_language_manager().get_language_ids():
            lang = self.get_language_manager().get_language(idl)
            for aglob in lang.get_globs():
                if fnmatch(filename, aglob):
                    return lang
        return None

class gtksourceview24(_gtksourceview2):

    def version_check(self):
        if self.gsv.pygtksourceview2_version[1] < 4:
            raise ImportError

    def get_language_from_file(self, filename):
        return self.get_language_manager().guess_language(filename)

class nullsourceview(_srcviewer):
    """Implement the sourceviewer API when no real one is available
    """

    get_language_from_file = lambda *args: None
    set_highlight = lambda *args: None
    set_tab_width = lambda *args: None
    get_language_from_mime_type = lambda *args: None

    def overrides(self):
        import gobject
        import gtk

        class NullTextView(gtk.TextView):
            set_tab_width = lambda *args: None
            set_show_line_numbers = lambda *args: None
            set_insert_spaces_instead_of_tabs = lambda *args: None
        gobject.type_register(NullTextView)

        self.GtkTextView = NullTextView
        self.GtkTextBuffer = gtk.TextBuffer

    def version_check(self):
        pass

def _get_srcviewer():
    for srcv in (gtksourceview24, gtksourceview22, gtksourceview, sourceview):
        try:
            return srcv()
        except ImportError:
            pass
    return nullsourceview()

srcviewer = _get_srcviewer()

class MeldSourceView(srcviewer.GtkTextView):
    __gtype_name__ = "MeldSourceView"
