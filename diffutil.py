## /usr/bin/env python

from __future__ import generators
import difflib

def _null_or_space(s):
    return len(s) == 0 or s.isspace()

def _chunkify_and_filter(seq, txts):
    """Merge diff blocks if they are separated by only whitespace.
    Also remove 'equal' blocks in the process"""
    if len(seq) >= 2:
        ret = []
        i = 0
        while i < len(seq):
            s = seq[i]
            if s[0] == "equal":
                if _null_or_space( "".join(txts[1][s[1]:s[2]])):
                    if i > 0:
                        r = ret[-1]
                        ret[-1] = ["replace", r[1], s[2], r[3], s[4]]
                    i += 1
                    if i < len(seq) and len(ret):
                        s = seq[i]
                        r = ret[-1]
                        ret[-1] = ["replace", r[1], s[2], r[3], s[4]]
            else:
                ret.append(s)
            i += 1
    else:
        ret = seq
    return ret

################################################################################
#
# Differ
#
################################################################################
class Differ:
    """Utility class to hold diff2 or diff3 chunks"""
    lookup = {"replace":"replace", "insert":"delete", "delete":"insert", "conflict":"conflict"}

    def __init__(self, *text):
        #print "\n\ntext0\n", text[0]
        #print "\n\ntext1\n", text[1]
        # diffs are stored from text1 -> text0 and text1 -> text2 for consistency
        textlines = map( lambda x: x.split("\n"), text)

        if len(text)==0 or len(text)==1:
            self.diffs = [[], []]
        elif len(text)==2:
            seq0 = difflib.SequenceMatcher(None, textlines[1], textlines[0]).get_opcodes()
            seq0 = filter(lambda x: x[0]!="equal", seq0)
            #seq0 = _chunkify_and_filter(seq0, textlines)
            self.diffs = [seq0, []]
        elif len(text)==3:
            seq0 = difflib.SequenceMatcher(None, textlines[1], textlines[0]).get_opcodes()
            seq0 = filter(lambda x: x[0]!="equal", seq0)
            #seq0 = _chunkify_and_filter(seq0, textlines[:-1])
            seq1 = difflib.SequenceMatcher(None, textlines[1], textlines[2]).get_opcodes()
            seq1 = filter(lambda x: x[0]!="equal", seq1)
            #seq1 = _chunkify_and_filter(seq1, textlines[1:])
            self.diffs = self._merge_diffs(seq0, seq1, textlines)
        else:
            raise "Bad number of arguments to Differ constructor (%i)" % len(text)

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
                yield self.lookup[c[0]], c[3],c[4], c[1],c[2]

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
