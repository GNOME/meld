### Copyright (C) 2002-2003 Stephen Kennedy <steve9000@users.sf.net>

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

from __future__ import generators
import difflib
import misc

def _null_or_space(s):
    return len(s.strip()) == 0

if 0:
    def _not_equal(s):
        return filter( lambda x: x[0]!="equal", s )
else:
    def _not_equal(s):
        return s

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
        #return self.get_opcodes()

################################################################################
#
# Differ
#
################################################################################
class Differ:
    """Utility class to hold diff2 or diff3 chunks"""
    reversemap = {
        "replace":"replace",
         "insert":"delete",
         "delete":"insert",
         "conflict":"conflict",
         "equal":"equal"}

    def __init__(self, *sequences):
        """Initialise with 1,2 or 3 sequences to compare"""
        # Internally, diffs are stored from text1 -> text0 and text1 -> text2.
        self.num_sequences = len(sequences)
        self.seqlength = [0,0,0]
        for i,s in misc.enumerate(sequences):
            self.seqlength[i] = len(s)

        if len(sequences)==0 or len(sequences)==1:
            self.diffs = [[], []]
        elif len(sequences)==2:
            seq0 = IncrementalSequenceMatcher(None, sequences[1], sequences[0]).get_difference_opcodes()
            self.diffs = [seq0, []]
        elif len(sequences)==3:
            seq0 = IncrementalSequenceMatcher(None, sequences[1], sequences[0]).get_difference_opcodes()
            seq1 = IncrementalSequenceMatcher(None, sequences[1], sequences[2]).get_difference_opcodes()
            self.diffs = self._merge_diffs(seq0, seq1, sequences)
        else:
            raise "Bad number of arguments to Differ constructor (%i)" % len(sequences)

    def change_sequence(self, sequence, startidx, sizechange, getlines ):
        """getlines(sequence, lo, hi)"""
        assert sequence in (0,1,2)
        if sequence != 1: #0 or 2
            self._change_sequence(sequence/2, sequence, startidx, sizechange, getlines)
        else:# sequence==1:
            self._change_sequence(         0, sequence, startidx, sizechange, getlines)
            if self.num_sequences == 3:
                self._change_sequence(     1, sequence, startidx, sizechange, getlines)
        if self.num_sequences == 3: # conflict update
            class Lazytext:
                def __init__(self, get):
                    self.get = get
                def __getslice__(self, lo, hi):
                    return self.get(lo,hi)
            text = [Lazytext(lambda l,h:getlines(i,l,h)) for i in range(3)]
            self.diffs = self._merge_diffs(self.diffs[0], self.diffs[1], text)

    def _locate_chunk(self, whichdiffs, sequence, line):
        """Find the index of the chunk which contains line."""
        idx = 1 + 2*(sequence != 1)
        line_in_chunk = lambda x: line < c[idx+1]
        i = 0
        for c in self.diffs[whichdiffs]:
            if line_in_chunk(c):
                break
            else:
                i += 1
        return i

    def _change_sequence(self, which, sequence, startidx, sizechange, getlines ):
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
        linesx = getlines(x, rangex[0], rangex[1])
        lines1 = getlines(1, range1[0], range1[1])
        #print "<<<\n%s\n===\n%s\n>>>" % ("\n".join(linesx),"\n".join(lines1))
        newdiffs = IncrementalSequenceMatcher( None, lines1, linesx).get_difference_opcodes()
        newdiffs = [ (c[0], c[1]+range1[0],c[2]+range1[0], c[3]+rangex[0],c[4]+rangex[0]) for c in newdiffs]
        if hiidx < len(self.diffs[which]):
            self.diffs[which][hiidx:] = [ (c[0],
                                           c[1] + lines_added[1], c[2] + lines_added[1],
                                           c[3] + lines_added[x], c[4] + lines_added[x])
                                                for c in self.diffs[which][hiidx:] ]
        self.diffs[which][loidx:hiidx] = newdiffs
        self.seqlength[sequence] += sizechange

    def reverse(self, c):
        return self.reversemap[c[0]], c[3],c[4], c[1],c[2]

    def pair_changes(self, fromindex, toindex):
        """give all changes between specified files"""
        assert abs(fromindex - toindex) == 1
        assert 1 in (fromindex, toindex)
        whichdiff = 2 in (fromindex, toindex)
        if fromindex == 1:
            for c in _not_equal(self.diffs[whichdiff]):
                yield c
        else: # diff hunks are reversed
            for c in _not_equal(self.diffs[whichdiff]):
                yield self.reverse(c)

    def single_changes(self, textindex):
        """give changes for single file only. do not return 'equal' hunks"""
        if textindex in (0,2):
            for c in _not_equal(self.diffs[textindex/2]):
                yield self.reversemap[c[0]], c[3], c[4], c[1], c[2], 1
        else:
            thread0 = _not_equal(self.diffs[0])
            thread1 = _not_equal(self.diffs[1])
            i0 = 0
            i1 = 0
            while i0 < len(thread0) and i1 < len(thread1):
                if thread0[i0][1] <= thread1[i1][1]:
                    yield list(thread0[i0]) + [0]
                    i0 += 1
                else:
                    yield list(thread1[i1]) + [2]
                    i1 += 1
            while i0 < len(thread0):
                yield list(thread0[i0]) + [0]
                i0 += 1
            while i1 < len(thread1):
                yield list(thread1[i1]) + [2]
                i1 += 1

    def _merge_blocks(self, using, low_seq, high_seq, last_diff):
        LO, HI = 1,2
        lowc  = using[low_seq][0][LO]
        highc = using[high_seq][0][HI]
        low = []
        high = []
        for i in (0,1):
            if len(using[i]):
                d = using[i][0]
                low.append(  lowc  - d[LO] + d[2+LO] )
                high.append( highc - d[HI] + d[2+HI] )
            else:
                d = last_diff
                low.append(  lowc  - d[LO] + d[2+LO] )
                high.append( highc - d[HI] + d[2+HI] )
        return low[0], high[0], lowc, highc, low[1], high[1]

    def _merge_diffs(self, seq0, seq1, texts):
        seq = seq0, seq1
        out0 = []
        out1 = []
        LO, HI = 1,2
        block = [0,0,0,0,0,0]
        while len(seq0) or len(seq1):
            if len(seq0) == 0:
                base_seq = 1
            elif len(seq1) == 0:
                base_seq = 0
            else:
                base_seq = seq0[0][LO] > seq1[0][LO]

            high_seq = base_seq
            high_diff = seq[high_seq].pop(0)
            high_mark = high_diff[HI]

            using = [[], []]
            using[high_seq].append(high_diff)

            while 1:
                other_seq = high_seq ^ 1
                try:
                    other_diff = seq[other_seq][0]
                except IndexError:
                    break 
                else:
                    if high_mark < other_diff[LO]:
                        break

                using[other_seq].append(other_diff)
                seq[other_seq].pop(0)

                if high_mark < other_diff[HI]:
                    high_seq ^= 1
                    high_diff = other_diff
                    high_mark = other_diff[HI]

            block = self._merge_blocks( using, base_seq, high_seq, block)

            if len(using[0])==0:
                out1 += using[1]
            elif len(using[1])==0:
                out0 += using[0]
            else:
                l0, h0, l1, h1, l2, h2 = block
                if h0-l0 == h2-l2 and texts[0][l0:h0] == texts[2][l2:h2]:
                    out0.append( ('replace', block[2], block[3], block[0], block[1]) )
                    out1.append( ('replace', block[2], block[3], block[4], block[5]) )
                else:
                    out0.append( ('conflict', block[2], block[3], block[0], block[1]) )
                    out1.append( ('conflict', block[2], block[3], block[4], block[5]) )

        return [out0, out1]

    def set_sequences_iter(self, *sequences):
        if len(sequences)==0 or len(sequences)==1:
            diffs = [[], []]
        elif len(sequences)==2:
            matcher = IncrementalSequenceMatcher(None, sequences[1], sequences[0])
            work = matcher.initialise()
            while work.next() == None:
                yield None
            diffs = [matcher.get_difference_opcodes(), []]
        elif len(sequences)==3:
            diffs = [[], []]
            for i in range(2):
                matcher = IncrementalSequenceMatcher(None, sequences[1], sequences[i*2])
                work = matcher.initialise()
                while work.next() == None:
                    yield None
                diffs[i] = matcher.get_difference_opcodes()
            diffs = self._merge_diffs(diffs[0], diffs[1], sequences)
        else:
            raise "Bad number of arguments to Differ constructor (%i)" % len(sequences)
        self.diffs = diffs
        self.num_sequences = len(sequences)
        self.seqlength = [0] * self.num_sequences
        for i,s in misc.enumerate(sequences):
            self.seqlength[i] = len(s)
        yield 1

def main():
    t0 = open("test/lao").readlines()
    tc = open("test/tzu").readlines()
    t1 = open("test/tao").readlines()

    thread0 = IncrementalSequenceMatcher(None, tc, t0).get_difference_opcodes()
    thread1 = IncrementalSequenceMatcher(None, tc, t1).get_difference_opcodes()

    texts = (t0,tc,t1)

if __name__=="__main__": 
    main()
