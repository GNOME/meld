### Copyright (C) 2002-2004 Stephen Kennedy <stevek@gnome.org>

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

import os
import gtk
import gobject
import gnome.vfs

try:
    #raise ImportError
    from gtksourceview import *
    available = 1
except ImportError:
    available = 0
    class SourceView(gtk.TextView):
        def set_show_line_numbers(self, show):
            pass
    gobject.type_register(SourceView)
    class SourceBuffer(gtk.TextBuffer):
        def set_highlight(self, show):
            pass
    gobject.type_register(SourceBuffer)
    class SourceLanguagesManager:
        def get_language_from_mime_type(self, mime):
            return None

def set_highlighting_enabled(buf, fname, enabled):
    mime_type = gnome.vfs.get_mime_type(os.path.abspath(fname))
    man = SourceLanguagesManager()
    gsl = man.get_language_from_mime_type( mime_type )
    if gsl:
        buf.set_language(gsl)
        buf.set_highlight(enabled)
    else:
        buf.set_highlight(False)

