# Copyright (C) 2009, 2012 Piotr Piastucki <the_leech@users.berlios.de>
# Copyright (C) 2012 Kai Willadsen <kai.willadsen@gmail.com>
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

from meld.conf import _
from . import filediff
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
        self.recompute_label()
