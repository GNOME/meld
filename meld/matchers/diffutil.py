# Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>
# Copyright (C) 2009, 2012-2013 Kai Willadsen <kai.willadsen@gmail.com>
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

from gi.repository import GObject

from meld.matchers.myers import (
    DiffChunk,
    MyersSequenceMatcher,
    SyncPointMyersSequenceMatcher,
)

LO, HI = 1, 2

opcode_reverse = {
    "replace": "replace",
    "insert": "delete",
    "delete": "insert",
    "conflict": "conflict",
    "equal": "equal"
}


def merged_chunk_order(merged_chunk):
    if not merged_chunk:
        return 0
    chunk = merged_chunk[0] or merged_chunk[1]
    return chunk.start_a


def reverse_chunk(chunk):
    tag = opcode_reverse[chunk[0]]
    return DiffChunk._make((tag, chunk[3], chunk[4], chunk[1], chunk[2]))


def consume_blank_lines(chunk, texts, pane1, pane2):
    if chunk is None:
        return None

    def _find_blank_lines(txt, lo, hi):
        while lo < hi and not txt[lo]:
            lo += 1
        while lo < hi and not txt[hi - 1]:
            hi -= 1
        return lo, hi

    tag = chunk.tag
    c1, c2 = _find_blank_lines(texts[pane1], chunk[1], chunk[2])
    c3, c4 = _find_blank_lines(texts[pane2], chunk[3], chunk[4])

    if c1 == c2 and c3 == c4:
        return None
    if c1 == c2 and tag == "replace":
        tag = "insert"
    elif c3 == c4 and tag == "replace":
        tag = "delete"
    return DiffChunk._make((tag, c1, c2, c3, c4))


class Differ(GObject.GObject):
    """Utility class to hold diff2 or diff3 chunks"""

    __gsignals__ = {
        'diffs-changed': (GObject.SignalFlags.RUN_FIRST, None,
                          (object,)),
    }

    _matcher = MyersSequenceMatcher
    _sync_matcher = SyncPointMyersSequenceMatcher

    def __init__(self):
        # Internally, diffs are stored from text1 -> text0 and text1 -> text2.
        super().__init__()
        self.num_sequences = 0
        self.seqlength = [0, 0, 0]
        self.diffs = [[], []]
        self.syncpoints = []
        self.conflicts = []
        self._old_merge_cache = set()
        self._changed_chunks = tuple()
        self._merge_cache = []
        self._line_cache = [[], [], []]
        self.ignore_blanks = False
        self._initialised = False
        self._has_mergeable_changes = (False, False, False, False)

    def _update_merge_cache(self, texts):
        if self.num_sequences == 3:
            self._merge_cache = [c for c in self._merge_diffs(self.diffs[0],
                                                              self.diffs[1],
                                                              texts)]
        else:
            self._merge_cache = [(c, None) for c in self.diffs[0]]

        if self.ignore_blanks:
            # We don't handle altering the chunk-type of conflicts in three-way
            # comparisons where e.g., pane 1 and 3 differ in blank lines
            for i, c in enumerate(self._merge_cache):
                self._merge_cache[i] = (consume_blank_lines(c[0], texts, 1, 0),
                                        consume_blank_lines(c[1], texts, 1, 2))
            self._merge_cache = [x for x in self._merge_cache if any(x)]

        # Calculate chunks that were added (in the new but not the old merge
        # cache), removed (in the old but not the new merge cache) and changed
        # (where the edit actually occurred, *and* the chunk is still around).
        # This information is used by the inline highlighting mechanism to
        # avoid re-highlighting existing chunks.
        removed_chunks = self._old_merge_cache - set(self._merge_cache)
        added_chunks = set(self._merge_cache) - self._old_merge_cache
        modified_chunks = self._changed_chunks
        if modified_chunks in removed_chunks:
            modified_chunks = tuple()
        chunk_changes = (removed_chunks, added_chunks, modified_chunks)

        mergeable0, mergeable1 = False, False
        for (c0, c1) in self._merge_cache:
            mergeable0 = mergeable0 or (c0 is not None and c0[0] != 'conflict')
            mergeable1 = mergeable1 or (c1 is not None and c1[0] != 'conflict')
            if mergeable0 and mergeable1:
                break
        self._has_mergeable_changes = (False, mergeable0, mergeable1, False)

        # Conflicts can only occur when there are three panes, and will always
        # involve the middle pane.
        self.conflicts = []
        for i, (c1, c2) in enumerate(self._merge_cache):
            if (c1 is not None and c1[0] == 'conflict') or \
               (c2 is not None and c2[0] == 'conflict'):
                self.conflicts.append(i)

        self._update_line_cache()
        self.emit("diffs-changed", chunk_changes)

    def _update_line_cache(self):
        """Cache a mapping from line index to per-pane chunk indices

        This cache exists so that the UI can quickly query for current,
        next and previous chunks when the current cursor line changes,
        enabling better action sensitivity feedback.
        """
        for i, length in enumerate(self.seqlength):
            # seqlength + 1 for after-last-line requests, which we do
            self._line_cache[i] = [(None, None, None)] * (length + 1)

        last_chunk = len(self._merge_cache)

        def find_next(diff, seq, current):
            next_chunk = None
            if seq == 1 and current + 1 < last_chunk:
                next_chunk = current + 1
            else:
                for j in range(current + 1, last_chunk):
                    if self._merge_cache[j][diff] is not None:
                        next_chunk = j
                        break
            return next_chunk

        prev = [None, None, None]
        next = [find_next(0, 0, -1), find_next(0, 1, -1), find_next(1, 2, -1)]
        old_end = [0, 0, 0]

        for i, c in enumerate(self._merge_cache):
            seq_params = ((0, 0, 3, 4), (0, 1, 1, 2), (1, 2, 3, 4))
            for (diff, seq, lo, hi) in seq_params:
                if c[diff] is None:
                    if seq == 1:
                        diff = 1
                    else:
                        continue

                start, end, last = c[diff][lo], c[diff][hi], old_end[seq]
                if (start > last):
                    chunk_ids = [(None, prev[seq], next[seq])] * (start - last)
                    self._line_cache[seq][last:start] = chunk_ids

                # For insert chunks, claim the subsequent line.
                if start == end:
                    end += 1

                next[seq] = find_next(diff, seq, i)
                chunk_ids = [(i, prev[seq], next[seq])] * (end - start)
                self._line_cache[seq][start:end] = chunk_ids
                prev[seq], old_end[seq] = i, end

        for seq in range(3):
            last, end = old_end[seq], len(self._line_cache[seq])
            if (last < end):
                chunk_ids = [(None, prev[seq], next[seq])] * (end - last)
                self._line_cache[seq][last:end] = chunk_ids

    def change_sequence(self, sequence, startidx, sizechange, texts):
        assert sequence in (0, 1, 2)
        if sequence == 0 or sequence == 1:
            self._change_sequence(0, sequence, startidx, sizechange, texts)
        if sequence == 2 or (sequence == 1 and self.num_sequences == 3):
            self._change_sequence(1, sequence, startidx, sizechange, texts)
        self.seqlength[sequence] += sizechange

        def offset(c, start, o1, o2):
            """Offset a chunk by o1/o2 if it's after the inserted lines"""
            if c is None:
                return None
            start_a = c.start_a + (o1 if c.start_a > start else 0)
            end_a = c.end_a + (o1 if c.end_a > start else 0)
            start_b = c.start_b + (o2 if c.start_b > start else 0)
            end_b = c.end_b + (o2 if c.end_b > start else 0)
            return DiffChunk._make((c.tag, start_a, end_a, start_b, end_b))

        # Calculate the expected differences in the chunk set if no cascading
        # changes occur, making sure to not include the changed chunk itself
        self._old_merge_cache = set()
        self._changed_chunks = tuple()
        chunk_changed = False
        for (c1, c2) in self._merge_cache:
            if sequence == 0:
                if c1 and c1.start_b <= startidx < c1.end_b:
                    chunk_changed = True
                c1 = offset(c1, startidx, 0, sizechange)
            elif sequence == 2:
                if c2 and c2.start_b <= startidx < c2.end_b:
                    chunk_changed = True
                c2 = offset(c2, startidx, 0, sizechange)
            else:
                # Middle sequence changes alter both chunks
                if c1 and c1.start_a <= startidx < c1.end_a:
                    chunk_changed = True
                c1 = offset(c1, startidx, sizechange, 0)
                if self.num_sequences == 3:
                    c2 = offset(c2, startidx, sizechange, 0)
            if chunk_changed:
                assert not self._changed_chunks
                self._changed_chunks = (c1, c2)
                chunk_changed = False
            self._old_merge_cache.add((c1, c2))

        self._update_merge_cache(texts)

    def _locate_chunk(self, whichdiffs, sequence, line):
        """Find the index of the chunk which contains line."""
        high_index = 2 + 2 * int(sequence != 1)
        for i, c in enumerate(self.diffs[whichdiffs]):
            if line < c[high_index]:
                return i
        return len(self.diffs[whichdiffs])

    def has_chunk(self, to_pane, chunk):
        """Return whether the pane/chunk exists in the current Differ"""
        sequence = 1 if to_pane == 2 else 0
        chunk_index, _, _ = self.locate_chunk(1, chunk.start_a)
        if chunk_index is None:
            return False
        return self._merge_cache[chunk_index][sequence] == chunk

    def get_chunk(self, index, from_pane, to_pane=None):
        """Return the index-th change in from_pane

        If to_pane is provided, then only changes between from_pane and to_pane
        are considered, otherwise all changes starting at from_pane are used.
        """
        sequence = int(from_pane == 2 or to_pane == 2)
        chunk = self._merge_cache[index][sequence]
        if from_pane in (0, 2):
            if chunk is None:
                return None
            return reverse_chunk(chunk)
        else:
            if to_pane is None and chunk is None:
                chunk = self._merge_cache[index][1]
            return chunk

    def get_chunk_starts(self, index):
        """Return the starting lines of all chunks at an index"""
        chunks = self._merge_cache[index]
        chunk_starts = [
            chunks[0].start_b if chunks[0] else None,
            chunks[0].start_a if chunks[0] else None,
            chunks[1].start_b if chunks[1] else None,
        ]
        return chunk_starts

    def locate_chunk(self, pane, line):
        """Find the index of the chunk which contains line

        Returns a tuple containing the current, previous and next chunk
        indices in that order. If the line has no associated chunk,
        None will be returned as the first element. If there are no
        previous/next chunks then None will be returned as the
        second/third elements.
        """
        try:
            return self._line_cache[pane][line]
        except IndexError:
            return (None, None, None)

    def diff_count(self):
        return len(self._merge_cache)

    def has_mergeable_changes(self, which):
        return self._has_mergeable_changes[which:which + 2]

    def _change_sequence(self, which, sequence, startidx, sizechange, texts):
        diffs = self.diffs[which]
        lines_added = [0, 0, 0]
        lines_added[sequence] = sizechange
        loidx = self._locate_chunk(which, sequence, startidx)
        if sizechange < 0:
            hiidx = self._locate_chunk(which, sequence, startidx - sizechange)
        else:
            hiidx = loidx
        if loidx > 0:
            loidx -= 1
            lorange = diffs[loidx][3], diffs[loidx][1]
        else:
            lorange = (0, 0)
        x = which * 2
        if hiidx < len(diffs):
            hiidx += 1
            hirange = diffs[hiidx - 1][4], diffs[hiidx - 1][2]
        else:
            hirange = self.seqlength[x], self.seqlength[1]
        rangex = lorange[0], hirange[0] + lines_added[x]
        range1 = lorange[1], hirange[1] + lines_added[1]
        assert rangex[0] <= rangex[1] and range1[0] <= range1[1]
        linesx = texts[x][rangex[0]:rangex[1]]
        lines1 = texts[1][range1[0]:range1[1]]

        def offset(c, o1, o2):
            return DiffChunk._make((c[0], c[1] + o1, c[2] + o1,
                                    c[3] + o2, c[4] + o2))

        newdiffs = self._matcher(None, lines1, linesx).get_difference_opcodes()
        newdiffs = [offset(c, range1[0], rangex[0]) for c in newdiffs]

        if hiidx < len(self.diffs[which]):
            offset_diffs = [offset(c, lines_added[1], lines_added[x])
                            for c in self.diffs[which][hiidx:]]
            self.diffs[which][hiidx:] = offset_diffs
        self.diffs[which][loidx:hiidx] = newdiffs

    def _range_from_lines(self, textindex, lines):
        lo_line, hi_line = lines
        top_chunk = self.locate_chunk(textindex, lo_line)
        start = top_chunk[0]
        if start is None:
            start = top_chunk[2]
        bottom_chunk = self.locate_chunk(textindex, hi_line)
        end = bottom_chunk[0]
        if end is None:
            end = bottom_chunk[1]
        return start, end

    def all_changes(self):
        return iter(self._merge_cache)

    def pair_changes(self, fromindex, toindex, lines=(None, None, None, None)):
        """Give all changes between file1 and either file0 or file2.
        """
        if None not in lines:
            start1, end1 = self._range_from_lines(fromindex, lines[0:2])
            start2, end2 = self._range_from_lines(toindex, lines[2:4])
            if (start1 is None or end1 is None) and \
               (start2 is None or end2 is None):
                return
            start = min([x for x in (start1, start2) if x is not None])
            end = max([x for x in (end1, end2) if x is not None])
            merge_cache = self._merge_cache[start:end + 1]
        else:
            merge_cache = self._merge_cache

        if fromindex == 1:
            seq = toindex // 2
            for c in merge_cache:
                if c[seq]:
                    yield c[seq]
        else:
            seq = fromindex // 2
            for c in merge_cache:
                if c[seq]:
                    yield reverse_chunk(c[seq])

    # FIXME: This is gratuitous copy-n-paste at this point
    def paired_all_single_changes(self, fromindex, toindex):
        if fromindex == 1:
            seq = toindex // 2
            for c in self._merge_cache:
                if c[seq]:
                    yield c[seq]
        else:
            seq = fromindex // 2
            for c in self._merge_cache:
                if c[seq]:
                    yield reverse_chunk(c[seq])

    def single_changes(self, textindex, lines=(None, None)):
        """Give changes for single file only. do not return 'equal' hunks.
        """
        if None not in lines:
            start, end = self._range_from_lines(textindex, lines)
            if start is None or end is None:
                return
            merge_cache = self._merge_cache[start:end + 1]
        else:
            merge_cache = self._merge_cache
        if textindex in (0, 2):
            seq = textindex // 2
            for cs in merge_cache:
                if cs[seq]:
                    yield reverse_chunk(cs[seq])
        else:
            for cs in merge_cache:
                yield cs[0] or cs[1]

    def sequences_identical(self):
        # check so that we don't call an uninitialised comparison 'identical'
        return self.diffs == [[], []] and self._initialised

    def _merge_blocks(self, using):
        lowc = min(using[0][0][LO], using[1][0][LO])
        highc = max(using[0][-1][HI], using[1][-1][HI])
        low = []
        high = []
        for i in (0, 1):
            d = using[i][0]
            low.append(lowc - d[LO] + d[2 + LO])
            d = using[i][-1]
            high.append(highc - d[HI] + d[2 + HI])
        return low[0], high[0], lowc, highc, low[1], high[1]

    def _auto_merge(self, using, texts):
        """Automatically merge two sequences of change blocks"""
        l0, h0, l1, h1, l2, h2 = self._merge_blocks(using)
        if h0 - l0 == h2 - l2 and texts[0][l0:h0] == texts[2][l2:h2]:
            if l1 != h1 and l0 == h0:
                tag = "delete"
            elif l1 != h1:
                tag = "replace"
            else:
                tag = "insert"
        else:
            tag = "conflict"
        out0 = DiffChunk._make((tag, l1, h1, l0, h0))
        out1 = DiffChunk._make((tag, l1, h1, l2, h2))
        yield out0, out1

    def _merge_diffs(self, seq0, seq1, texts):
        seq0, seq1 = seq0[:], seq1[:]
        seq = seq0, seq1
        while len(seq0) or len(seq1):
            if not seq0:
                high_seq = 1
            elif not seq1:
                high_seq = 0
            else:
                high_seq = int(seq0[0].start_a > seq1[0].start_a)
                if seq0[0].start_a == seq1[0].start_a:
                    if seq0[0].tag == "insert":
                        high_seq = 0
                    elif seq1[0].tag == "insert":
                        high_seq = 1

            high_diff = seq[high_seq].pop(0)
            high_mark = high_diff.end_a
            other_seq = 0 if high_seq == 1 else 1

            using = [[], []]
            using[high_seq].append(high_diff)

            while seq[other_seq]:
                other_diff = seq[other_seq][0]
                if high_mark < other_diff.start_a:
                    break
                if high_mark == other_diff.start_a and \
                   not (high_diff.tag == other_diff.tag == "insert"):
                    break

                using[other_seq].append(other_diff)
                seq[other_seq].pop(0)

                if high_mark < other_diff.end_a:
                    high_seq, other_seq = other_seq, high_seq
                    high_mark = other_diff.end_a

            if len(using[0]) == 0:
                assert len(using[1]) == 1
                yield None, using[1][0]
            elif len(using[1]) == 0:
                assert len(using[0]) == 1
                yield using[0][0], None
            else:
                for c in self._auto_merge(using, texts):
                    yield c

    def set_sequences_iter(self, sequences):
        assert 0 <= len(sequences) <= 3
        self.diffs = [[], []]
        self.num_sequences = len(sequences)
        self.seqlength = [len(s) for s in sequences]

        for i in range(self.num_sequences - 1):
            if self.syncpoints:
                syncpoints = [(s[i][0](), s[i][1]()) for s in self.syncpoints]
                matcher = self._sync_matcher(None,
                                             sequences[1], sequences[i * 2],
                                             syncpoints=syncpoints)
            else:
                matcher = self._matcher(None, sequences[1], sequences[i * 2])
            work = matcher.initialise()
            while next(work) is None:
                yield None
            self.diffs[i] = matcher.get_difference_opcodes()
        self._initialised = True
        self._update_merge_cache(sequences)
        yield 1

    def clear(self):
        self.diffs = [[], []]
        self.seqlength = [0] * self.num_sequences
        self._initialised = False
        self._old_merge_cache = set()
        self._update_merge_cache([""] * self.num_sequences)
