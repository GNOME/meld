### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2009-2010 Kai Willadsen <kai.willadsen@gmail.com>

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

import meld.util.sourceviewer


class MeldBuffer(meld.util.sourceviewer.srcviewer.GtkTextBuffer):

    __gtype_name__ = "MeldBuffer"

    def __init__(self, filename=None):
        meld.util.sourceviewer.srcviewer.GtkTextBuffer.__init__(self)
        self.data = MeldBufferData(filename)

    def reset_buffer(self, filename):
        self.delete(*self.get_bounds())

        new_data = MeldBufferData(filename)
        if self.data.filename == filename:
            new_data.label = self.data.label
        self.data = new_data

    def get_iter_at_line_or_eof(self, line):
        if line >= self.get_line_count():
            return self.get_end_iter()
        return self.get_iter_at_line(line)

    def insert_at_line(self, line, text):
        if line >= self.get_line_count():
            # TODO: We need to insert a linebreak here, but there is no
            # way to be certain what kind of linebreak to use.
            text = "\n" + text
        it = self.get_iter_at_line_or_eof(line)
        self.insert(it, text)
        return it


class MeldBufferData(object):

    __slots__ = ("modified", "writable", "filename", "savefile", "label",
                 "encoding", "newlines")

    def __init__(self, filename=None):
        self.modified = False
        self.writable = True
        self.filename = filename
        self.savefile = None
        self.label = filename
        self.encoding = None
        self.newlines = None

