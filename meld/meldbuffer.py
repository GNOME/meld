### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
### Copyright (C) 2009-2011 Kai Willadsen <kai.willadsen@gmail.com>

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

from __future__ import unicode_literals

import sys
from gettext import gettext as _

from .util import sourceviewer

from .util.compat import text_type


class MeldBuffer(sourceviewer.srcviewer.GtkTextBuffer):

    __gtype_name__ = "MeldBuffer"

    def __init__(self, filename=None):
        sourceviewer.srcviewer.GtkTextBuffer.__init__(self)
        self.data = MeldBufferData(filename)

    def reset_buffer(self, filename):
        """Clear the contents of the buffer and reset its metadata"""
        self.delete(*self.get_bounds())

        new_data = MeldBufferData(filename)
        if self.data.filename == filename:
            new_data.label = self.data.label
        self.data = new_data

    def get_iter_at_line_or_eof(self, line):
        """Return a gtk.TextIter at the given line, or the end of the buffer.

        This method is like get_iter_at_line, but if asked for a position past
        the end of the buffer, this returns the end of the buffer; the
        get_iter_at_line behaviour is to return the start of the last line in
        the buffer.
        """
        if line >= self.get_line_count():
            return self.get_end_iter()
        return self.get_iter_at_line(line)

    def insert_at_line(self, line, text):
        """Insert text at the given line, or the end of the buffer.

        This method is like insert, but if asked to insert something past the
        last line in the buffer, this will insert at the end, and will add a
        linebreak before the inserted text. The last line in a gtk.TextBuffer
        is guaranteed never to have a newline, so we need to handle this.
        """
        if line >= self.get_line_count():
            # TODO: We need to insert a linebreak here, but there is no
            # way to be certain what kind of linebreak to use.
            text = "\n" + text
        it = self.get_iter_at_line_or_eof(line)
        self.insert(it, text)
        return it


class MeldBufferData(object):

    def __init__(self, filename=None):
        self.modified = False
        self.writable = True
        self.editable = True
        self.filename = filename
        self.savefile = None
        self._label = filename
        self.encoding = None
        self.newlines = None

    def get_label(self):
        #TRANSLATORS: This is the label of a new, currently-unnamed file.
        return self._label or _("<unnamed>")

    def set_label(self, value):
        self._label = value

    label = property(get_label, set_label)


class BufferLines(object):
    """gtk.TextBuffer shim with line-based access and optional filtering

    This class allows a gtk.TextBuffer to be treated as a list of lines of
    possibly-filtered text. If no filter is given, the raw output from the
    gtk.TextBuffer is used.

    The logic here (and in places in FileDiff) requires that Python's
    unicode splitlines() implementation and gtk.TextBuffer agree on where
    linebreaks occur. Happily, this is usually the case.
    """

    def __init__(self, buf, textfilter=None):
        self.buf = buf
        if textfilter is not None:
            self.textfilter = textfilter
        else:
            self.textfilter = lambda x: x

    def __getitem__(self, key):
        if isinstance(key, slice):
            lo, hi, _ = key.indices(self.buf.get_line_count())

            # FIXME: If we ask for arbitrary slices past the end of the buffer,
            # this will return the last line.
            start = self.buf.get_iter_at_line_or_eof(lo)
            end = self.buf.get_iter_at_line_or_eof(hi)
            txt = text_type(self.buf.get_text(start, end, False), 'utf8')

            filter_txt = self.textfilter(txt)
            lines = filter_txt.splitlines()
            ends = filter_txt.splitlines(True)

            # The last line in a gtk.TextBuffer is guaranteed never to end in a
            # newline. As splitlines() discards an empty line at the end, we
            # need to artificially add a line if the requested slice is past
            # the end of the buffer, and the last line in the slice ended in a
            # newline.
            if hi >= self.buf.get_line_count() and \
               lo < self.buf.get_line_count() and \
               (len(lines) == 0 or len(lines[-1]) != len(ends[-1])):
                lines.append("")
                ends.append("")

            hi = self.buf.get_line_count() if hi == sys.maxsize else hi
            if hi - lo != len(lines):
                # These codepoints are considered line breaks by Python, but
                # not by GtkTextStore.
                additional_breaks = set(('\x0c', '\x85'))
                i = 0
                while i < len(ends):
                    line, end = lines[i], ends[i]
                    # It's possible that the last line in a file would end in a
                    # line break character, which requires no joining.
                    if end and end[-1] in additional_breaks and \
                       (not line or line[-1] not in additional_breaks):
                        assert len(ends) >= i + 1
                        lines[i:i + 2] = [line + end[-1] + lines[i + 1]]
                        ends[i:i + 2] = [end + ends[i + 1]]
                    i += 1

            return lines

        elif isinstance(key, int):
            if key >= len(self):
                raise IndexError
            line_start = self.buf.get_iter_at_line_or_eof(key)
            line_end = line_start.copy()
            if not line_end.ends_line():
                line_end.forward_to_line_end()
            txt = self.buf.get_text(line_start, line_end, False)
            return text_type(self.textfilter(txt), 'utf8')

    def __len__(self):
        return self.buf.get_line_count()


class BufferAction(object):
    """A helper to undo/redo text insertion/deletion into/from a text buffer"""

    def __init__(self, buf, offset, text):
        self.buffer = buf
        self.offset = offset
        self.text = text

    def delete(self):
        start = self.buffer.get_iter_at_offset(self.offset)
        end = self.buffer.get_iter_at_offset(self.offset + len(self.text))
        self.buffer.delete(start, end)

    def insert(self):
        start = self.buffer.get_iter_at_offset(self.offset)
        self.buffer.insert(start, self.text)


class BufferInsertionAction(BufferAction):
    undo = BufferAction.delete
    redo = BufferAction.insert


class BufferDeletionAction(BufferAction):
    undo = BufferAction.insert
    redo = BufferAction.delete
