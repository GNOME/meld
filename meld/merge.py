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

import diffutil
import matchers
#from _patiencediff_py import PatienceSequenceMatcher_py as PatienceSequenceMatcher


class Merger(diffutil.Differ):

    _matcher = matchers.MyersSequenceMatcher
   # _matcher = PatienceSequenceMatcher

    def __init__(self):
        diffutil.Differ.__init__(self)
        self.auto_merge = False
        self.unresolved = []

    def _auto_merge(self, using, texts):
        l0, h0, l1, h1, l2, h2 = self._merge_blocks(using)

        if h0 - l0 == h2 - l2 and texts[0][l0:h0] == texts[2][l2:h2]:
            # handle simple conflicts here (exact match)
            if l1 != h1 and l0 == h0:
                tag = "delete"
            elif l1 != h1:
                tag = "replace"
            else:
                tag = "insert"
            out0 = (tag, l1, h1, l0, h0)
            out1 = (tag, l1, h1, l2, h2)
        else:
            # here we will try to resolve more complex conflicts automatically... if possible
            out0 = ('conflict', l1, h1, l0, h0)
            out1 = ('conflict', l1, h1, l2, h2)
            if self.auto_merge:
                len0 = h0 - l0
                len1 = h1 - l1
                len2 = h2 - l2
                if (len0 > 0 and len2 > 0) and (len0 == len1 or len2 == len1 or len1 == 0):
                    matcher = self._matcher(None, texts[0][l0:h0], texts[2][l2:h2])
                    for chunk in matcher.get_opcodes():
                        s1 = l1
                        e1 = l1
                        if len0 == len1:
                            s1 += chunk[1]
                            e1 += chunk[2]
                        elif len2 == len1:
                            s1 += chunk[3]
                            e1 += chunk[4]
                        if chunk[0] == 'equal':
                            out0 = ('replace', s1, e1, l0 + chunk[1], l0 + chunk[2])
                            out1 = ('replace', s1, e1, l2 + chunk[3], l2 + chunk[4])
                            yield out0, out1
                        else:
                            out0 = ('conflict', s1, e1, l0 + chunk[1], l0 + chunk[2])
                            out1 = ('conflict', s1, e1, l2 + chunk[3], l2 + chunk[4])
                            yield out0, out1
                    return
#                elif len0 > 0 and len2 > 0:
                    # this logic will resolve more conflicts automatically, but unresolved conflicts may sometimes look confusing
                    # as the line numbers in ancestor file will be interpolated and may not reflect the actual changes
#                    matcher = self._matcher(None, texts[0][l0:h0], texts[2][l2:h2])
#                    if len0 > len2:
#                        maxindex = 1
#                        maxlen = len0
#                    else:
#                        maxindex = 3
#                        maxlen = len2
#                    for chunk in matcher.get_opcodes():
#                        if chunk[0] == 'equal':
#                            out0 = ('replace', l1 + len1 * chunk[maxindex] / maxlen, l1 + len1 * chunk[maxindex + 1] / maxlen, l0 + chunk[1], l0 + chunk[2])
#                            out1 = ('replace', l1 + len1 * chunk[maxindex] / maxlen, l1 + len1 * chunk[maxindex + 1] / maxlen, l2 + chunk[3], l2 + chunk[4])
#                            yield out0, out1
#                        else:
#                            out0 = ('conflict', l1 + len1 * chunk[maxindex] / maxlen, l1 + len1 * chunk[maxindex + 1] / maxlen, l0 + chunk[1], l0 + chunk[2])
#                            out1 = ('conflict', l1 + len1 * chunk[maxindex] / maxlen, l1 + len1 * chunk[maxindex + 1] / maxlen, l2 + chunk[3], l2 + chunk[4])
#                            yield out0, out1
#                    return
                else:
                    # some tricks to resolve even more conflicts automatically
                    # unfortunately the resulting chunks cannot be used to highlight changes
                    # but hey, they are good enough to merge the resulting file :)
                    chunktype = using[0][0][0]
                    for chunkarr in using:
                        for chunk in chunkarr:
                            if chunk[0] != chunktype:
                                chunktype = None
                                break
                        if not chunktype:
                            break
                    if chunktype == 'delete':
                        # delete + delete (any length) -> split into delete/conflict
                        seq0 = seq1 = None
                        while 1:
                            if seq0 == None:
                                try:
                                    seq0 = using[0].pop(0)
                                    i0 = seq0[1]
                                    end0 = seq0[4]
                                except IndexError:
                                    break
                            if seq1 == None:
                                try:
                                    seq1 = using[1].pop(0)
                                    i1 = seq1[1]
                                    end1 = seq1[4]
                                except IndexError:
                                    break
                            highstart = max(i0, i1)
                            if i0 != i1:
                                out0 = ('conflict', i0 - highstart + i1, highstart, seq0[3] - highstart + i1, seq0[3])
                                out1 = ('conflict', i1 - highstart + i0, highstart, seq1[3] - highstart + i0, seq1[3])
                                yield out0, out1
                            lowend = min(seq0[2], seq1[2])
                            if highstart != lowend:
                                out0 = ('delete', highstart, lowend, seq0[3], seq0[4])
                                out1 = ('delete', highstart, lowend, seq1[3], seq1[4])
                                yield out0, out1
                            i0 = i1 = lowend
                            if lowend == seq0[2]:
                                seq0 = None
                            if lowend == seq1[2]:
                                seq1 = None

                        if seq0:
                            out0 = ('conflict', i0, seq0[2], seq0[3], seq0[4])
                            out1 = ('conflict', i1, i1 + seq0[2] - i0, end1, end1 + seq0[2] - i0)
                            yield out0, out1
                        elif seq1:
                            out0 = ('conflict', i0, i0 + seq1[2] - i1, end0, end0 + seq2[2] - i1)
                            out1 = ('conflict', i1, seq1[2], seq1[3], seq1[4])
                            yield out0, out1
                        return
        yield out0, out1

    def change_sequence(self, sequence, startidx, sizechange, texts):
        if sequence == 1:
            lo = 0
            for c in self.unresolved:
                if startidx <= c:
                    break
                lo += 1
            if lo < len(self.unresolved):
                hi = lo
                if sizechange < 0:
                    for c in self.unresolved[lo:]:
                        if startidx - sizechange <= c:
                            break
                        hi += 1
                elif sizechange == 0 and startidx == self.unresolved[lo]:
                    hi += 1

                if hi < len(self.unresolved):
                    self.unresolved[hi:] = [c + sizechange for c in self.unresolved[hi:]]
                self.unresolved[lo:hi] = []

        return diffutil.Differ.change_sequence(self, sequence, startidx, sizechange, texts)

    def get_unresolved_count(self):
        return len(self.unresolved)

    def _apply_change(self, text, change, mergedtext):
        LO, HI = 1, 2
        if change[0] == 'insert':
            for i in range(change[LO + 2], change[HI + 2]):
                mergedtext.append(text[i])
            return 0
        elif change[0] == 'replace':
            for i in range(change[LO + 2], change[HI + 2]):
                mergedtext.append(text[i])
            return change[HI] - change[LO]
        else:
            return change[HI] - change[LO]

    def merge_file(self, filteredtexts, texts):
        LO, HI = 1, 2
        self.auto_merge = True
        self.unresolved = unresolved = []
        diffs = self.diffs
        lastline = 0
        mergedline = 0
        mergedtext = []
        for change in self._merge_diffs(diffs[0], diffs[1], filteredtexts):
            yield None
            low_mark = lastline
            if change[0] != None:
                low_mark = change[0][LO]
            if change[1] != None:
                if change[1][LO] > low_mark:
                    low_mark = change[1][LO]
            for i in range(lastline, low_mark, 1):
                mergedtext.append(texts[1][i])
            mergedline += low_mark - lastline
            lastline = low_mark
            if change[0] != None and change[1] != None and change[0][0] == 'conflict':
                high_mark = max(change[0][HI], change[1][HI])
                if low_mark < high_mark:
                    for i in range(low_mark, high_mark):
                        mergedtext.append("(??)" + texts[1][i])
                        unresolved.append(mergedline)
                        mergedline += 1
                else:
                    #conflictsize = min(1, max(change[0][HI + 2] - change[0][LO + 2], change[1][HI + 2] - change[1][LO + 2]))
                    #for i in range(conflictsize):
                    mergedtext.append("(??)")
                    unresolved.append(mergedline)
                    mergedline += 1
                lastline = high_mark
            elif change[0] != None:
                lastline += self._apply_change(texts[0], change[0], mergedtext)
                mergedline += change[0][HI + 2] - change[0][LO + 2]
            else:
                lastline += self._apply_change(texts[2], change[1], mergedtext)
                mergedline += change[1][HI + 2] - change[1][LO + 2]
        baselen = len(texts[1])
        for i in range(lastline, baselen, 1):
            mergedtext.append(texts[1][i])

        self.auto_merge = False
        yield "\n".join(mergedtext)
