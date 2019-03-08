# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009-2013 Kai Willadsen <kai.willadsen@gmail.com>
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
import sys

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import GtkSource

from meld.conf import _
from meld.settings import bind_settings, meldsettings

log = logging.getLogger(__name__)


class MeldBuffer(GtkSource.Buffer):

    __gtype_name__ = "MeldBuffer"

    __gsettings_bindings__ = (
        ('highlight-syntax', 'highlight-syntax'),
    )

    def __init__(self):
        super().__init__()
        bind_settings(self)
        self.data = MeldBufferData()
        self.undo_sequence = None
        meldsettings.connect('changed', self.on_setting_changed)
        self.set_style_scheme(meldsettings.style_scheme)

    def on_setting_changed(self, meldsettings, key):
        if key == 'style-scheme':
            self.set_style_scheme(meldsettings.style_scheme)

    def do_begin_user_action(self, *args):
        if self.undo_sequence:
            self.undo_sequence.begin_group()

    def do_end_user_action(self, *args):
        if self.undo_sequence:
            self.undo_sequence.end_group()

    def get_iter_at_line_or_eof(self, line):
        """Return a Gtk.TextIter at the given line, or the end of the buffer.

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
        linebreak before the inserted text. The last line in a Gtk.TextBuffer
        is guaranteed never to have a newline, so we need to handle this.
        """
        if line >= self.get_line_count():
            # TODO: We need to insert a linebreak here, but there is no
            # way to be certain what kind of linebreak to use.
            text = "\n" + text
        it = self.get_iter_at_line_or_eof(line)
        self.insert(it, text)
        return it


class MeldBufferData(GObject.GObject):

    __gsignals__ = {
        str('file-changed'): (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    encoding = GObject.Property(
        type=GtkSource.Encoding,
        nick="The file encoding of the linked GtkSourceFile",
        default=None,
    )

    def __init__(self):
        super().__init__()
        self._gfile = None
        self._label = None
        self._monitor = None
        self._sourcefile = None
        self.reset(gfile=None)

    def reset(self, gfile):
        same_file = gfile and self._gfile and gfile.equal(self._gfile)
        self.gfile = gfile
        if same_file:
            self.label = self._label
        else:
            self.label = gfile.get_parse_name() if gfile else None
        self.loaded = False
        self.savefile = None

    def __del__(self):
        self.disconnect_monitor()

    @property
    def label(self):
        # TRANSLATORS: This is the label of a new, currently-unnamed file.
        return self._label or _("<unnamed>")

    @label.setter
    def label(self, value):
        if not value:
            return
        if not isinstance(value, str):
            log.warning('Invalid label ignored "%r"', value)
            return
        self._label = value

    def connect_monitor(self):
        if not self._gfile:
            return
        monitor = self._gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
        handler_id = monitor.connect('changed', self._handle_file_change)
        self._monitor = monitor, handler_id

    def disconnect_monitor(self):
        if not self._monitor:
            return
        monitor, handler_id = self._monitor
        monitor.disconnect(handler_id)
        monitor.cancel()
        self._monitor = None

    def _query_mtime(self, gfile):
        try:
            time_query = ",".join((Gio.FILE_ATTRIBUTE_TIME_MODIFIED,
                                   Gio.FILE_ATTRIBUTE_TIME_MODIFIED_USEC))
            info = gfile.query_info(time_query, 0, None)
        except GLib.GError:
            return None
        mtime = info.get_modification_time()
        return (mtime.tv_sec, mtime.tv_usec)

    def _handle_file_change(self, monitor, f, other_file, event_type):
        mtime = self._query_mtime(f)
        if self._disk_mtime and mtime and mtime > self._disk_mtime:
            self.emit('file-changed')
        self._disk_mtime = mtime or self._disk_mtime

    @property
    def gfile(self):
        return self._gfile

    @gfile.setter
    def gfile(self, value):
        self.disconnect_monitor()
        self._gfile = value
        self._sourcefile = GtkSource.File()
        self._sourcefile.set_location(value)
        self._sourcefile.bind_property(
            'encoding', self, 'encoding', GObject.BindingFlags.DEFAULT)

        self.update_mtime()
        self.connect_monitor()

    @property
    def sourcefile(self):
        return self._sourcefile

    @property
    def gfiletarget(self):
        return self.savefile or self.gfile

    @property
    def is_special(self):
        try:
            info = self._gfile.query_info(
                Gio.FILE_ATTRIBUTE_STANDARD_TYPE, 0, None)
            return info.get_file_type() == Gio.FileType.SPECIAL
        except (AttributeError, GLib.GError):
            return False

    @property
    def writable(self):
        try:
            info = self.gfiletarget.query_info(
                Gio.FILE_ATTRIBUTE_ACCESS_CAN_WRITE, 0, None)
        except GLib.GError as err:
            if err.code == Gio.IOErrorEnum.NOT_FOUND:
                return True
            return False
        except AttributeError:
            return False
        return info.get_attribute_boolean(Gio.FILE_ATTRIBUTE_ACCESS_CAN_WRITE)

    def update_mtime(self):
        if self._gfile:
            self._disk_mtime = self._query_mtime(self._gfile)
            self._mtime = self._disk_mtime

    def current_on_disk(self):
        return self._mtime == self._disk_mtime


class BufferLines:
    """Gtk.TextBuffer shim with line-based access and optional filtering

    This class allows a Gtk.TextBuffer to be treated as a list of lines of
    possibly-filtered text. If no filter is given, the raw output from the
    Gtk.TextBuffer is used.

    The logic here (and in places in FileDiff) requires that Python's
    unicode splitlines() implementation and Gtk.TextBuffer agree on where
    linebreaks occur. Happily, this is usually the case.
    """

    def __init__(self, buf, textfilter=None):
        self.buf = buf
        if textfilter is not None:
            self.textfilter = textfilter
        else:
            self.textfilter = lambda x, buf, start_iter, end_iter: x

    def __getitem__(self, key):
        if isinstance(key, slice):
            lo, hi, _ = key.indices(self.buf.get_line_count())

            # FIXME: If we ask for arbitrary slices past the end of the buffer,
            # this will return the last line.
            start = self.buf.get_iter_at_line_or_eof(lo)
            end = self.buf.get_iter_at_line_or_eof(hi)
            txt = self.buf.get_text(start, end, False)

            filter_txt = self.textfilter(txt, self.buf, start, end)
            lines = filter_txt.splitlines()
            ends = filter_txt.splitlines(True)

            # The last line in a Gtk.TextBuffer is guaranteed never to end in a
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
                additional_breaks = set(('\x0b', '\x0c', '\x85', '\u2028'))
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
                    else:
                        # We only increment if we don't correct a line, to
                        # handle the case of a single line having multiple
                        # additional_breaks characters that need correcting.
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
            return self.textfilter(txt, self.buf, line_start, line_end)

    def __len__(self):
        return self.buf.get_line_count()


class BufferAction:
    """A helper to undo/redo text insertion/deletion into/from a text buffer"""

    def __init__(self, buf, offset, text):
        self.buffer = buf
        self.offset = offset
        self.text = text

    def delete(self):
        start = self.buffer.get_iter_at_offset(self.offset)
        end = self.buffer.get_iter_at_offset(self.offset + len(self.text))
        self.buffer.delete(start, end)
        self.buffer.place_cursor(end)
        return [self]

    def insert(self):
        start = self.buffer.get_iter_at_offset(self.offset)
        self.buffer.place_cursor(start)
        self.buffer.insert(start, self.text)
        return [self]


class BufferInsertionAction(BufferAction):
    undo = BufferAction.delete
    redo = BufferAction.insert


class BufferDeletionAction(BufferAction):
    undo = BufferAction.insert
    redo = BufferAction.delete
