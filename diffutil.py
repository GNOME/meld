### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>

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

import difflib

################################################################################
#
# Differ
#
################################################################################
class IncrementalSequenceMatcher(difflib.SequenceMatcher):
    def __init__(self, isjunk=None, a="", b=""):
        difflib.SequenceMatcher.__init__(self, isjunk, a, b)

    def initialise(self):
        la, lb = len(self.a), len(self.b)
        todo = [(0, la, 0, lb)]
        done = []
        while len(todo):
            alo, ahi, blo, bhi = todo.pop(0)
            i, j, k = x = self.find_longest_match(alo, ahi, blo, bhi)
            if k:
                yield None
                done.append( (i,x) )
                if alo < i and blo < j:
                    todo.append( (alo, i, blo, j) )
                if i+k < ahi and j+k < bhi:
                    todo.append( (i+k, ahi, j+k, bhi) )
        done.append( (la, (la, lb, 0)) )
        done.sort()
        self.matching_blocks = [x[1] for x in done]
        yield 1

    def get_difference_opcodes(self):
        return filter(lambda x: x[0]!="equal", self.get_opcodes())

################################################################################
#
# Differ
#
################################################################################
class Differ(object):
    """Utility class to hold diff2 or diff3 chunks"""
    reversemap = {
        "replace":"replace",
         "insert":"delete",
         "delete":"insert",
         "conflict":"conflict",
         "equal":"equal"}

    def __init__(self):
        # Internally, diffs are stored from text1 -> text0 and text1 -> text2.
        self.num_sequences = 0
        self.seqlength = [0, 0, 0]
        self.diffs = [[], []]

    def change_sequence(self, sequence, startidx, sizechange, texts):
        assert sequence in (0,1,2)
        if sequence != 1: #0 or 2
            which = sequence / 2
            self._change_sequence(which, sequence, startidx, sizechange, texts)
        else: # sequence==1:
            self._change_sequence(0, sequence, startidx, sizechange, texts)
            if self.num_sequences == 3:
                self._change_sequence(1, sequence, startidx, sizechange, texts)
        self.seqlength[sequence] += sizechange

    def _locate_chunk(self, whichdiffs, sequence, line):
        """Find the index of the chunk which contains line."""
        high_index = 2 + 2 * int(sequence != 1)
        for i, c in enumerate(self.diffs[whichdiffs]):
            if line < c[high_index]:
                return i
        return len(self.diffs[whichdiffs])

    def _change_sequence(self, which, sequence, startidx, sizechange, texts):
        diffs = self.diffs[which]
        lines_added = [0,0,0]
        lines_added[sequence] = sizechange
        loidx = self._locate_chunk(which, sequence, startidx)
        if sizechange < 0:
            hiidx = self._locate_chunk(which, sequence, startidx-sizechange)
        else:
            hiidx = loidx
        if loidx > 0:
            loidx -= 1
            lorange = diffs[loidx][3], diffs[loidx][1]
        else:
            lorange = (0,0)
        x = which*2
        if hiidx < len(diffs):
            hiidx += 1
            hirange = diffs[hiidx-1][4], diffs[hiidx-1][2]
        else:
            hirange = self.seqlength[x], self.seqlength[1]
        #print "diffs", loidx, hiidx, len(diffs), lorange, hirange #diffs[loidx], diffs[hiidx-1]
        rangex = lorange[0], hirange[0] + lines_added[x]
        range1 = lorange[1], hirange[1] + lines_added[1]
        #print "^^^^^", rangex, range1
        assert rangex[0] <= rangex[1] and range1[0] <= range1[1]
        linesx = texts[x][rangex[0]:rangex[1]]
        lines1 = texts[1][range1[0]:range1[1]]
        #print "<<<\n%s\n===\n%s\n>>>" % ("\n".join(linesx),"\n".join(lines1))
        newdiffs = IncrementalSequenceMatcher( None, lines1, linesx).get_difference_opcodes()
        newdiffs = [ (c[0], c[1]+range1[0],c[2]+range1[0], c[3]+rangex[0],c[4]+rangex[0]) for c in newdiffs]
        if hiidx < len(self.diffs[which]):
            self.diffs[which][hiidx:] = [ (c[0],
                                           c[1] + lines_added[1], c[2] + lines_added[1],
                                           c[3] + lines_added[x], c[4] + lines_added[x])
                                                for c in self.diffs[which][hiidx:] ]
        self.diffs[which][loidx:hiidx] = newdiffs

    def reverse(self, c):
        return self.reversemap[c[0]], c[3],c[4], c[1],c[2]

    def all_changes(self, texts):
        for c in self._merge_diffs(self.diffs[0], self.diffs[1], texts):
            yield c

    def pair_changes(self, fromindex, toindex, texts):
        """Give all changes between file1 and either file0 or file2.
        """
        if fromindex == 1:
            seq = toindex/2
            for c in self.all_changes( texts ):
                if c[seq]:
                    yield c[seq]
        else:
            seq = fromindex/2
            for c in self.all_changes( texts ):
                if c[seq]:
                    yield self.reverse(c[seq])

    def single_changes(self, textindex, texts):
        """Give changes for single file only. do not return 'equal' hunks.
        """
        if textindex in (0,2):
            seq = textindex/2
            for cs in self.all_changes( texts ):
                c = cs[seq]
                if c:
                    yield self.reversemap[c[0]], c[3], c[4], c[1], c[2], 1
        else:
            for cs in self.all_changes( texts ):
                if cs[0]:
                    c = cs[0]
                    yield c[0], c[1], c[2], c[3], c[4], 0
                elif cs[1]:
                    c = cs[1]
                    yield c[0], c[1], c[2], c[3], c[4], 2

    def _merge_blocks(self, using):
        LO, HI = 1,2
        lowc  =  min(using[0][ 0][LO], using[1][ 0][LO])
        highc =  max(using[0][-1][HI], using[1][-1][HI])
        low = []
        high = []
        for i in (0,1):
            d = using[i][0]
            low.append(lowc - d[LO] + d[2+LO])
            d = using[i][-1]
            high.append(highc - d[HI] + d[2+HI])
        return low[0], high[0], lowc, highc, low[1], high[1]

    def _merge_diffs(self, seq0, seq1, texts):
        seq0, seq1 = seq0[:], seq1[:]
        seq = seq0, seq1
        LO, HI = 1,2
        while len(seq0) or len(seq1):
            if len(seq0) == 0:
                high_seq = 1
            elif len(seq1) == 0:
                high_seq = 0
            else:
                high_seq = int(seq0[0][LO] > seq1[0][LO])

            high_diff = seq[high_seq].pop(0)
            high_mark = high_diff[HI]
            other_seq = high_seq ^ 1

            using = [[], []]
            using[high_seq].append(high_diff)

            while seq[other_seq]:
                other_diff = seq[other_seq][0]
                if high_mark < other_diff[LO]:
                    break

                using[other_seq].append(other_diff)
                seq[other_seq].pop(0)

                if high_mark < other_diff[HI]:
                    (high_seq, other_seq) = (other_seq, high_seq)
                    high_mark = other_diff[HI]

            if len(using[0])==0:
                assert len(using[1])==1
                yield None, using[1][0]
            elif len(using[1])==0:
                assert len(using[0])==1
                yield using[0][0], None
            else:
                l0, h0, l1, h1, l2, h2 = self._merge_blocks(using)
                if h0-l0 == h2-l2 and texts[0][l0:h0] == texts[2][l2:h2]:
                    if l1 != h1:
                        tag = "replace"
                    else:
                        tag = "insert"
                else:
                    tag = "conflict"
                out0 = (tag, l1, h1, l0, h0)
                out1 = (tag, l1, h1, l2, h2)
                yield out0, out1

    def set_sequences_iter(self, *sequences):
        assert 0 <= len(sequences) <= 3
        self.diffs = [[], []]
        self.num_sequences = len(sequences)
        self.seqlength = [len(s) for s in sequences]

        for i in range(self.num_sequences - 1):
            matcher = IncrementalSequenceMatcher(None, sequences[1], sequences[i*2])
            work = matcher.initialise()
            while work.next() == None:
                yield None
            self.diffs[i] = matcher.get_difference_opcodes()
        yield 1

