### Copyright (C) 2002-2005 Stephen Kennedy <stevek@gnome.org>

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
        "equal":"equal" }

    def __init__(self):
        # text0 text1 text2
        # Internally, diffs are stored from text0 -> text1 and text2 -> text1.
        self.numlines = [0,0,0]
        self.diffs = [[], []]

    def set_sequences_iter(self, *sequences):
        assert len(sequences) in (1,2,3)
        diffs = [[], []]
        if len(sequences) >= 2:
            matcher = IncrementalSequenceMatcher(None, sequences[0], sequences[1])
            work = matcher.initialise()
            while work.next() == None:
                yield None
            diffs[0] = [op + (0,) for op in matcher.get_difference_opcodes()]
            if len(sequences) == 3:
                matcher.set_seq1( sequences[2] )
                work = matcher.initialise()
                while work.next() == None:
                    yield None
                diffs[1] = [op + (1,) for op in matcher.get_difference_opcodes()]
        self.diffs = diffs
        self.numlines = [len(s) for s in sequences]
        yield 1

    def single_changes(self, textindex, reversed=False):
        """Give changes for single file only.
           Do not return 'equal' hunks.
           Do not find conflicts.
        """
        identity= lambda c : c
        reverse = lambda c,m=self.reversemap : (m[c[0]], c[3], c[4], c[1], c[2], c[5])
        if textindex in (0,2):
            proc = (identity, reverse)[reversed]
            for c in self.diffs[textindex/2]:
                yield proc(c)
        elif len(self.numlines) == 2: # textindex == 1
            proc = (reverse, identity)[reversed]
            for c in self.diffs[0]:
                yield proc(c)
        else: # textindex == 1 and panes == 3
            proc = (reverse, identity)[reversed]
            ix0, ix1 = 0,0
            while ix0 < len(self.diffs[0]) and ix1 < len(self.diffs[1]):
                c0, c1 = self.diffs[0][ix0], self.diffs[1][ix1]
                if c0[3] < c1[3]:
                    c = c0
                    ix0 += 1
                else:
                    c = c1
                    ix1 += 1
                yield proc(c)
            for c in self.diffs[0][ix0:]:
                yield proc(c)
            for c in self.diffs[1][ix1:]:
                yield proc(c)

    def _locate_chunk(self, whichdiffs, sequence, line):
        """Find the index of the chunk which contains line."""
        idx = 1 + 2*(sequence == 1)
        for i,c in enumerate(self.diffs[whichdiffs]):
            if line < c[idx+1]:
                if line >= c[idx]:
                    return i
                assert 0#return i-1
        return 0

    def change_sequence(self, sequence, startidx, sizechange, texts):
        assert sequence in (0,1,2)
        changes = [[0,0],[0,0]]
        if sequence != 1: #0 or 2
            which = sequence / 2
            changes[which] = self._change_sequence(which, sequence, startidx, sizechange, texts)
        else: # sequence==1:
            changes[0] = self._change_sequence(         0, sequence, startidx, sizechange, texts)
            if len(self.numlines) == 3:
                changes[1] = self._change_sequence(     1, sequence, startidx, sizechange, texts)
        return changes

    def _change_sequence(self, which, sequence, startidx, sizechange, texts):
        #print "_change_sequence(", self, which, sequence, startidx, sizechange, texts
        lines_added = [0,0,0]
        lines_added[sequence] = sizechange
        if sizechange < 0:
            idx = 1 + 2*(sequence == 1)
            odx = 1 + 2*(sequence != 1)
            diffs = self.diffs[which]
            print "***1***", diffs
            for i,c in enumerate(diffs):
                if startidx < c[idx+1]:
                    if startidx < c[idx]:
                        d = [None] + [startidx]*4 + [which]
                        d[  odx] = c[idx]-startidx
                        d[1+odx] = d[odx]-sizechange
                        diffs.insert(i, tuple(d))
                    break
            endline = startidx-sizechange
            print "***2***", diffs, i
            diffs[i] = list(diffs[i])
            diffs[i][1+idx] = startidx
            for j in range(i+1, len(diffs)):
                print "M", j, diffs[j]
                if endline < diffs[j][idx]:
                    diffs[i][2], diffs[i][4] = diffs[j-1][2], diffs[j-1][4]
                    del diffs[i+1:j-1]
                    for k in range(j, len(diffs)):
                        d = list(diffs[k])
                        d[  idx] += sizechange
                        d[1+idx] += sizechange
                        diffs[k] = tuple(d)
                    break
            if diffs[i][idx] == diffs[i][1+idx]:
                if diffs[i][odx] == diffs[i][1+odx]:
                    del diffs[i]
                    return
                diffs[i][0] = ("delete","insert")[which]
            else:
                diffs[i][0] = "replace"
            diffs[i] = tuple(diffs[i])
            #return diffs[i][idx], diffs[i][1+idx]
            return
        else:
            return
            hiidx = loidx
        if loidx > 0:
            loidx -= 1
            lorange = diffs[loidx][1], diffs[loidx][3]
        else:
            lorange = (0,0)
        x = which*2
        if hiidx < len(diffs):
            hiidx += 1
            hirange = diffs[hiidx-1][2], diffs[hiidx-1][4]
        else:
            hirange = self.numlines[x], self.numlines[1]
        #print "diffs", loidx, hiidx, len(diffs), lorange, hirange #diffs[loidx], diffs[hiidx-1]
        rangex = lorange[0], hirange[0] + lines_added[x]
        range1 = lorange[1], hirange[1] + lines_added[1]
        #print "^^^^^", rangex, range1
        assert rangex[0] <= rangex[1] and range1[0] <= range1[1]
        linesx = texts[x][rangex[0]:rangex[1]]
        lines1 = texts[1][range1[0]:range1[1]]
        #print "<<<\n%s\n===\n%s\n>>>" % ("\n".join(linesx),"\n".join(lines1))
        newdiffs = IncrementalSequenceMatcher( None, lines1, linesx).get_difference_opcodes()
        newdiffs = [ (c[0], c[1]+rangex[0],c[2]+rangex[0], c[3]+range1[0],c[4]+range1[0]) for c in newdiffs]
        if hiidx < len(self.diffs[which]):
            self.diffs[which][hiidx:] = [ (c[0],
                                           c[1] + lines_added[x], c[2] + lines_added[x],
                                           c[3] + lines_added[1], c[4] + lines_added[1])
                                                for c in self.diffs[which][hiidx:] ]
        self.diffs[which][loidx:hiidx] = newdiffs
        self.numlines[sequence] += sizechange
        return loidx,hiidx

    def reverse(self, c):
        return self.reversemap[c[0]], c[3],c[4], c[1],c[2]

    def all_changes(self, texts):
        for c in self._merge_diffs(self.diffs[0], self.diffs[1], texts):
            yield c

    def all_changes_in_range(self, texts, l0, h0, l1, h1):
        for c in self._merge_diffs(self.diffs[0][l0:h0], self.diffs[1][l0:h0], texts):
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

    def _merge_blocks(self, using, low_seq, high_seq, last_diff):
        LO, HI = 3,4
        lowc  = using[low_seq][0][LO]
        highc = using[high_seq][0][HI]
        low = []
        high = []
        for i in (0,1):
            if len(using[i]):
                d = using[i][0]
                low.append(  lowc  - d[LO] + d[LO-2] )
                high.append( highc - d[HI] + d[HI-2] )
            else:
                d = last_diff
                low.append(  lowc  - d[LO] + d[LO-2] )
                high.append( highc - d[HI] + d[HI-2] )
        return low[0], high[0], lowc, highc, low[1], high[1]

    def _merge_diffs(self, seq0, seq1, texts):
        seq0, seq1 = seq0[:], seq1[:]
        seq = seq0, seq1
        LO, HI = 3,4
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
                assert len(using[1])==1
                yield None, using[1][0]
            elif len(using[1])==0:
                assert len(using[0])==1
                yield using[0][0], None
            else:
                l0, h0, l1, h1, l2, h2 = block
                if h0-l0 == h2-l2 and texts[0][l0:h0] == texts[2][l2:h2]:
                    if l1 != h1:
                        out0 = ('replace', block[2], block[3], block[0], block[1])
                        out1 = ('replace', block[2], block[3], block[4], block[5])
                    else:
                        out0 = ('insert', block[2], block[3], block[0], block[1])
                        out1 = ('insert', block[2], block[3], block[4], block[5])
                else:
                    out0 = ('conflict', block[2], block[3], block[0], block[1])
                    out1 = ('conflict', block[2], block[3], block[4], block[5])
                yield out0, out1

def main():
    t0 = open("test/lao").readlines()
    tc = open("test/tzu").readlines()
    t1 = open("test/tao").readlines()

    thread0 = IncrementalSequenceMatcher(None, tc, t0).get_difference_opcodes()
    thread1 = IncrementalSequenceMatcher(None, tc, t1).get_difference_opcodes()

    texts = (t0,tc,t1)

if __name__=="__main__":
    main()
