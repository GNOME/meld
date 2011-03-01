### Copyright (C) 2009 Piotr Piastucki <the_leech@users.berlios.de>

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

import filediff
from gettext import gettext as _
import gtk
import merge

MASK_SHIFT, MASK_CTRL = 1, 2


class FileMerge(filediff.FileDiff):

    differ = merge.AutoMergeDiffer

    def __init__(self, prefs, num_panes):
        filediff.FileDiff.__init__(self, prefs, num_panes)
        self.hidden_textbuffer = gtk.TextBuffer()

    def _connect_buffer_handlers(self):
        filediff.FileDiff._connect_buffer_handlers(self)
        self.textview[0].set_editable(0)
        self.textview[2].set_editable(0)

    def set_files(self, files):
        if len(files) == 4:
            self.ancestor_file = files[1]
            self.merge_file = files[3]
            files[1] = files[3]
            files = files[:3]
        filediff.FileDiff.set_files(self, files)

    def _set_files_internal(self, files):
        textbuffers = self.textbuffer[:]
        textbuffers[1] = self.hidden_textbuffer
        files[1] = self.ancestor_file
        for i in self._load_files(files, textbuffers):
            yield i
        for i in self._merge_files():
            yield i
        for i in self._diff_files():
            yield i

    def _get_custom_status_text(self):
        return "   Conflicts: %i" % (self.linediffer.get_unresolved_count())

    def set_buffer_writable(self, buf, yesno):
        if buf == self.hidden_textbuffer:
            buf = self.textbuffer[1]
            yesno = True
        filediff.FileDiff.set_buffer_writable(self, buf, yesno)

    def _merge_files(self):
        yield _("[%s] Computing differences") % self.label_text
        panetext = []
        textbuffer = self.textbuffer[:]
        textbuffer[1] = self.hidden_textbuffer
        for b in textbuffer[:self.num_panes]:
            start, end = b.get_bounds()
            text = unicode(b.get_text(start, end, False), 'utf8')
            panetext.append(text)
        lines = [x.split("\n") for x in panetext]
        filteredpanetext = [self._filter_text(p) for p in panetext]
        filteredlines = [x.split("\n") for x in filteredpanetext]
        merger = merge.Merger()
        step = merger.initialize(filteredlines, lines)
        while step.next() == None:
            yield 1
        yield _("[%s] Merging files") % self.label_text
        for panetext[1] in merger.merge_3_files():
            yield 1
        self.linediffer.unresolved = merger.unresolved
        self.textbuffer[1].insert(self.textbuffer[1].get_end_iter(), panetext[1])
        self.bufferdata[1].modified = 1
        self.recompute_label()
        yield 1
