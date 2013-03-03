### Copyright (C) 2009, 2012 Piotr Piastucki <the_leech@users.berlios.de>
### Copyright (C) 2012 Kai Willadsen <kai.willadsen@gmail.com>

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

from gettext import gettext as _

from . import filediff
from . import meldbuffer
from . import merge
from . import recent


class FileMerge(filediff.FileDiff):

    differ = merge.AutoMergeDiffer

    def _connect_buffer_handlers(self):
        filediff.FileDiff._connect_buffer_handlers(self)
        self.textview[0].set_editable(0)
        self.textview[2].set_editable(0)

    def get_comparison(self):
        comp = filediff.FileDiff.get_comparison(self)
        return recent.TYPE_MERGE, comp[1]

    def _set_files_internal(self, files):
        self.textview[1].set_buffer(meldbuffer.MeldBuffer())
        for i in self._load_files(files, self.textbuffer):
            yield i
        for i in self._merge_files():
            yield i
        self.textview[1].set_buffer(self.textbuffer[1])
        for i in self._diff_files():
            yield i

    def _merge_files(self):
        yield _("[%s] Merging files") % self.label_text
        merger = merge.Merger()
        step = merger.initialize(self.buffer_filtered, self.buffer_texts)
        while next(step) is None:
            yield 1
        for merged_text in merger.merge_3_files():
            yield 1
        self.linediffer.unresolved = merger.unresolved
        self.textbuffer[1].set_text(merged_text)
        self.textbuffer[1].data.modified = True
        self.recompute_label()
