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

from __future__ import unicode_literals

import sys

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import GtkSource

from meld.conf import _
from meld.misc import fallback_decode
from meld.settings import bind_settings, meldsettings
from meld.util.compat import text_type


class MeldBuffer(GtkSource.Buffer):

    __gtype_name__ = "MeldBuffer"

    __gsettings_bindings__ = (
        ('highlight-syntax', 'highlight-syntax'),
    )

    def __init__(self):
        GtkSource.Buffer.__init__(self)
        bind_settings(self)
        self.data = MeldBufferData()
        self.user_action_count = 0
        self.undo_sequence = None
        meldsettings.connect('changed', self.on_setting_changed)
        self.set_style_scheme(meldsettings.style_scheme)

    def on_setting_changed(self, meldsettings, key):
        if key == 'style-scheme':
            self.set_style_scheme(meldsettings.style_scheme)

    def do_begin_user_action(self, *args):
        self.user_action_count += 1
        if self.undo_sequence:
            self.undo_sequence.begin_group()

    def do_end_user_action(self, *args):
        if self.undo_sequence:
            self.undo_sequence.end_group()
        self.user_action_count -= 1

    def do_apply_tag(self, tag, start, end):
        # Filthy, evil, horrible hack. What we're doing here is trying to
        # figure out if a tag apply has come from a paste action, in which
        # case GtkTextBuffer will 'helpfully' apply the existing tags in the
        # copied selection. There appears to be no way to override this
        # behaviour, or to hook in to the necessary paste mechanics to just
        # request that we only get plain text or something. We're abusing the
        # user_action notion here, because we only apply the tags we actually
        # want in a callback.
        if tag.props.name == 'inline' and self.user_action_count > 0:
            return
        return GtkSource.Buffer.do_apply_tag(self, tag, start, end)

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

    def __init__(self):
        GObject.GObject.__init__(self)
        self._gfile = None
        self._label = None
        self._monitor = None
        self._sourcefile = None
        self.reset(gfile=None)

    def reset(self, gfile):
        same_file = gfile and self._gfile and gfile.equal(self._gfile)
        self.gfile = gfile
        self.label = self._label if same_file else self.filename
        self.loaded = False
        self.savefile = None

    def __del__(self):
        self._disconnect_monitor()

    @property
    def label(self):
        # TRANSLATORS: This is the label of a new, currently-unnamed file.
        return self._label or _(u"<unnamed>")

    @label.setter
    def label(self, value):
        if not value:
            return
        encodings = (sys.getfilesystemencoding(), 'utf8')
        self._label = fallback_decode(value, encodings, lossy=True)

    def _connect_monitor(self):
        if not self._gfile:
            return
        monitor = self._gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
        handler_id = monitor.connect('changed', self._handle_file_change)
        self._monitor = monitor, handler_id

    def _disconnect_monitor(self):
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
        if self._disk_mtime and mtime > self._disk_mtime:
            self.emit('file-changed')
        self._disk_mtime = mtime

    @property
    def gfile(self):
        return self._gfile

    @gfile.setter
    def gfile(self, value):
        self._disconnect_monitor()
        self._gfile = value
        self._sourcefile = GtkSource.File()
        self._sourcefile.set_location(value)

        # This is aiming to maintain existing behaviour for filename. The
        # behaviour is however wrong and should be fixed.
        self.filename = value.get_path().decode('utf8') if value else None
        self.update_mtime()
        self._connect_monitor()

    @property
    def sourcefile(self):
        return self._sourcefile

    @property
    def gfiletarget(self):
        if self.savefile:
            return Gio.File.new_for_path(self.savefile)
        return self.gfile

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
        except (AttributeError, GLib.GError):
            return False
        return info.get_attribute_boolean(Gio.FILE_ATTRIBUTE_ACCESS_CAN_WRITE)

    def update_mtime(self):
        if self._gfile:
            self._disk_mtime = self._query_mtime(self._gfile)
            self._mtime = self._disk_mtime

    def current_on_disk(self):
        return self._mtime == self._disk_mtime


class BufferLines(object):
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
            txt = text_type(self.buf.get_text(start, end, False), 'utf8')

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
                additional_breaks = set(('\x0c', '\x85', u'\u2028'))
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
            txt_filtered = self.textfilter(txt, self.buf, line_start, line_end)
            return text_type(txt_filtered, 'utf8')

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
