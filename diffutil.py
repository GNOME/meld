## /usr/bin/env python

from __future__ import generators
import difflib

def _null_or_space(s):
    return len(s) == 0 or s.isspace()

################################################################################
#
# Differ
#
################################################################################
class Differ:
    """Utility class to hold diff2 or diff3 chunks"""
    reverse = {
        "replace":"replace",
              "insert":"delete",
              "delete":"insert",
              "conflict":"conflict",
              "equal":"equal"}

    def __init__(self, *sequences):
        """Initialise with 1,2 or 3 sequences to compare"""
        # Internally, diffs are stored from text1 -> text0 and text1 -> text2 for consistency

        if len(sequences)==0 or len(sequences)==1:
            self.diffs = [[], []]
        elif len(sequences)==2:
            seq0 = difflib.SequenceMatcher(None, sequences[1], sequences[0]).get_opcodes()
            self.diffs = [seq0, []]
        elif len(sequences)==3:
            seq0 = difflib.SequenceMatcher(None, sequences[1], sequences[0]).get_opcodes()
            seq1 = difflib.SequenceMatcher(None, sequences[1], sequences[2]).get_opcodes()
            self.diffs = self._merge_diffs(seq0, seq1, sequences)
        else:
            raise "Bad number of arguments to Differ constructor (%i)" % len(sequences)

    def _locate_chunk(self, fromindex, toindex, line):
        """Find the index of the chunk which contains line."""
        #XXX 3way
        idx = 1 + 2*(1-fromindex)
        line_in_chunk = lambda x: x[idx] <= line and line < c[idx+1]
        i = 0
        for c in self.diffs[0]:
            if line_in_chunk(c):
                break
            else:
                i += 1
        return i

    def change_sequence(self, sequence, startidx, sizechange, getlines ):
        """gettext(sequence, lo, hi)"""
        diffs = self.diffs[0]
        lines_added = [0,0,0]
        lines_added[sequence] = sizechange
        if len(diffs) == 0:
            assert min(lines_added) >= 0
            self.diffs[0] = [("replace", 0, 1+lines_added[1], 0, 1+lines_added[0])]
            return
# clamp range!!!
        endidx = startidx + sizechange
        loidx = self._locate_chunk(sequence, 1-sequence, startidx)
        hiidx = min(self._locate_chunk(sequence, 1-sequence, endidx) + 1, len(diffs))
        while loidx > 0:
            loidx -= 1
            if diffs[loidx][0] == "equal":
                break
        while hiidx < len(diffs):
            hiidx += 1
            if diffs[hiidx-1][0] == "equal":
                break
        range0 = diffs[loidx][3], diffs[hiidx-1][4] + lines_added[0]
        assert range0[0] <= range0[1]
        range1 = diffs[loidx][1], diffs[hiidx-1][2] + lines_added[1]
        assert range1[0] <= range1[1]
        lines0 = getlines(0, range0[0], range0[1])
        lines1 = getlines(1, range1[0], range1[1])
        newdiffs = difflib.SequenceMatcher( None, lines1, lines0).get_opcodes()
        newdiffs = [ (c[0], c[1]+range1[0],c[2]+range1[0], c[3]+range0[0],c[4]+range0[0]) for c in newdiffs]
        if hiidx < len(self.diffs[0]):
            self.diffs[0][hiidx:] = [ (c[0],
                                       c[1] + lines_added[1], c[2] + lines_added[1],
                                       c[3] + lines_added[0], c[4] + lines_added[0])
                                                for c in self.diffs[0][hiidx:] ]
        self.diffs[0][loidx:hiidx] = newdiffs

    def pair_changes(self, fromindex, toindex):
        """give all changes between specified files"""
        assert(fromindex != toindex)
        assert(fromindex == 1 or toindex == 1)
        if 0 in (fromindex, toindex):
            whichdiff = 0
        else:
            whichdiff = 1
        if fromindex == 1: # always diff from file 1 to file x
            for c in self.diffs[whichdiff]:
                yield c
        else: # diff hunks are reversed
            for c in self.diffs[whichdiff]:
                yield self.reverse[c[0]], c[3],c[4], c[1],c[2]

    def single_changes(self, textindex):
        """give changes for single file only. do not return 'equal' hunks"""
        if textindex == 0 or textindex == 2:
            for c in self.diffs[textindex/2]:
                yield c[0], c[3], c[4], c[1], c[2], 1
        else:
            thread0 = self.diffs[0]
            thread1 = self.diffs[1]
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

def main():
    t0 = open("test/lao").readlines()
    tc = open("test/tzu").readlines()
    t1 = open("test/tao").readlines()

    thread0 = filter(lambda x: x[0]!="equal", difflib.SequenceMatcher(None, tc, t0).get_opcodes())
    thread1 = filter(lambda x: x[0]!="equal", difflib.SequenceMatcher(None, tc, t1).get_opcodes())

    texts = (t0,tc,t1)

if __name__=="__main__": 
    main()
