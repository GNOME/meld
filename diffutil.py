#! /usr/bin/env python2.2

from __future__ import generators
import difflib

LOLINE = 1
HILINE = 2

class diff3_block:
    __slots__ = ["difftype", "lo", "hi"]
    def __init__(self, lo0, hi0, loC, hiC, lo1, hi1):
        self.difftype = None
        self.lo = (lo0, loC, lo1)
        self.hi = (hi0, hiC, hi1)
    def __str__(self):
        return "diff3_block (%s) %s" % (self.difftype, zip(self.lo, self.hi),)

def merge_blocks(using, low_thread, high_thread, last_diff, orig_texts):
    #print using, low_thread, high_thread
    lowc  = using[low_thread][0][LOLINE]
    highc = using[high_thread][0][HILINE]
    low = []
    high = []
    for i in (0,1):
        if len(using[i]):
            d = using[i][0]
            low.append(  lowc  - d[LOLINE] + d[2+LOLINE] )
            high.append( highc - d[HILINE] + d[2+HILINE] )
        else:
            d = last_diff
            low.append(  lowc  - d.hi[1] + d.hi[i+i] )
            high.append( highc - d.hi[1] + d.hi[i+i] )

    result = diff3_block(low[0], high[0], lowc, highc, low[1], high[1])
    if len(using[0])==0:
        result.difftype = 2
    elif len(using[1])==0:
        result.difftype = 0
    else:
        h0, l0, h2, l2 = result.hi[0], result.lo[0], result.hi[2], result.lo[2]
        if h0-l0 == h2-l2 and orig_texts[0][l0:h0] == orig_texts[2][l2:h2]:
            result.difftype = 1
        else:
            result.difftype = 3

    return result

def make_3way_diff(thread0, thread1, orig_texts):
    """Input thread0, thread1 which are diffs of common->file0 and common->file1 respectively"""

    thread = [thread0, thread1]
    last_diff = diff3_block(0,0,0,0,0,0)
    blocks = []

    while len(thread0) or len(thread1):

        # pick the lowest diff to start with
        if len(thread0)==0:
            base_water_thread = 1
        elif len(thread1)==0:
            base_water_thread = 0
        else:
            base_water_thread = (1,0)[ thread0[0][LOLINE] <= thread1[0][LOLINE] ]

        high_water_thead = base_water_thread
        high_water_diff = thread[high_water_thead].pop(0)
        high_water_mark = high_water_diff[HILINE]

        using = [[], []]
        using[high_water_thead].append(high_water_diff)

        # pick up diffs overlapping with this one
        while 1:
            other_thread = high_water_thead ^ 1
            try:
                other_diff = thread[other_thread][0]
            except IndexError:
                break 
            else:
                if high_water_mark + 1 < other_diff[LOLINE]:
                    break

            # add the overlapping diff
            using[other_thread].append(other_diff)
            thread[other_thread].pop(0)

            # keep high_water_* up to date
            if high_water_mark < other_diff[HILINE]:
                high_water_thead ^= 1
                high_water_diff = other_diff
                high_water_mark = other_diff[HILINE]

        last_diff = merge_blocks(using, base_water_thread, high_water_thead, last_diff, orig_texts)
        blocks.append(last_diff)
        print "****", last_diff
    return blocks

def pretty(blocks, texts):
    for b in blocks:
        print "====%s" % (b.difftype+1,"")[b.difftype==3]
        for i in range(3):
            if b.lo[i] + 1 >= b.hi[i]:
                print "%i:%i" % (i+1, b.lo[i]+ (b.lo[i]!=b.hi[i]))
            else:
                print "%i:%i,%i" % (i+1, b.lo[i]+1, b.hi[i])

def max2(x,y):
    if x>y: return x
    else: return y

################################################################################
#
# Differ
#
################################################################################
class Differ:
    """Utility class to hold diff2 or diff3 chunks"""
    lookup = {"replace":"replace", "insert":"delete", "delete":"insert", "conflict":"conflict"}

    def __init__(self, *text):
        # diffs are stored from text1 -> text0 and text1 -> text2 for consistency
        if len(text)==0 or len(text)==1:
            self.diffs = ([], [])
        elif len(text)==2:
            seq0 = difflib.SequenceMatcher(None, text[1].split("\n"), text[0].split("\n")).get_opcodes()
            seq0 = filter(lambda x: x[0]!="equal", seq0)
            self.diffs = (seq0, [])
        elif len(text)==3:
            seq0 = difflib.SequenceMatcher(None, text[1].split("\n"), text[0].split("\n")).get_opcodes()
            seq1 = difflib.SequenceMatcher(None, text[1].split("\n"), text[2].split("\n")).get_opcodes()
            self.diffs = self._merge(seq0, seq1)
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
                if c[0]!='equal':
                    yield self.lookup[c[0]], c[3], c[4]
        else:
            thread0 = filter(lambda x: x[0]!="equal", self.diffs[0])
            thread1 = filter(lambda x: x[0]!="equal", self.diffs[1])
            while len(thread0) or len(thread1):
                if len(thread0) == 0:
                    yield thread1.pop(0)[:3]
                elif len(thread1) == 0:
                    yield thread0.pop(0)[:3]
                else:
                    if thread0[0][1] <= thread1[0][1]:
                        yield thread0.pop(0)[:3]
                    else:
                        yield thread1.pop(0)[:3]


    def _merge(self, seq0, seq1):
        thread0 = filter(lambda x: x[0]!="equal", seq0)
        thread1 = filter(lambda x: x[0]!="equal", seq1)
        thread = thread0,thread1
        out0 = []
        out1 = []
        while len(thread0) or len(thread1):
            if len(thread0) == 0:
                base_thread = 1
            elif len(thread1) == 0:
                base_thread = 0
            else:
                base_thread = (1,0)[ thread0[0][1] <= thread1[0][1] ]

            d = thread[base_thread].pop(0)
            diff = d[:3]
            range = [None, None]
            range[base_thread] = d[3:5]

            while 1:
                other_thread = base_thread ^ 1

                try:
                    other_diff = thread[other_thread][0]
                except IndexError:
                    break 
                else:
                    if diff[2] < other_diff[1]:
                        break

                #TODO fixme
                other_diff = thread[other_thread].pop(0)
                diff = ("conflict", diff[1], max2(other_diff[2], diff[2]) )
                if range[other_thread]:
                    range[other_thread] = range[other_thread][0], other_diff[4]
                else:
                    range[other_thread] = other_diff[3], other_diff[4]
                base_thread ^= 1

            if range[0]:
                out0.append( diff + range[0] )
            if range[1]:
                out1.append( diff + range[1] )
        return out0, out1

def main():
    t0 = open("test/lao").readlines()
    tc = open("test/tzu").readlines()
    t1 = open("test/tao").readlines()

    thread0 = filter(lambda x: x[0]!="equal", difflib.SequenceMatcher(None, tc, t0).get_opcodes())
    thread1 = filter(lambda x: x[0]!="equal", difflib.SequenceMatcher(None, tc, t1).get_opcodes())

    texts = (t0,tc,t1)
    d3 = make_3way_diff(thread0, thread1, texts)
    pretty(d3, texts)

if __name__=="__main__": 
    main()
