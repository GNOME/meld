# Copyright (C) 2009-2010 Piotr Piastucki <the_leech@users.berlios.de>
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

from meld.matchers import diffutil
from meld.matchers.myers import MyersSequenceMatcher

LO, HI = 1, 2


class AutoMergeDiffer(diffutil.Differ):

    _matcher = MyersSequenceMatcher
    # _matcher = PatienceSequenceMatcher

    def __init__(self):
        super().__init__()
        self.auto_merge = False
        self.unresolved = []

    def _auto_merge(self, using, texts):
        for out0, out1 in super()._auto_merge(using, texts):
            if self.auto_merge and out0[0] == 'conflict':
                # we will try to resolve more complex conflicts automatically
                # here... if possible
                l0, h0, l1, h1, l2, h2 = (
                    out0[3], out0[4], out0[1], out0[2], out1[3], out1[4])
                len0 = h0 - l0
                len1 = h1 - l1
                len2 = h2 - l2
                if (len0 > 0 and len2 > 0) and (
                        len0 == len1 or len2 == len1 or len1 == 0):
                    matcher = self._matcher(
                        None, texts[0][l0:h0], texts[2][l2:h2])
                    for chunk in matcher.get_opcodes():
                        s1 = l1
                        e1 = l1
                        if len0 == len1:
                            s1 += chunk[1]
                            e1 += chunk[2]
                        elif len2 == len1:
                            s1 += chunk[3]
                            e1 += chunk[4]
                        out0_bounds = (s1, e1, l0 + chunk[1], l0 + chunk[2])
                        out1_bounds = (s1, e1, l2 + chunk[3], l2 + chunk[4])
                        if chunk[0] == 'equal':
                            out0 = ('replace',) + out0_bounds
                            out1 = ('replace',) + out1_bounds
                            yield out0, out1
                        else:
                            out0 = ('conflict',) + out0_bounds
                            out1 = ('conflict',) + out1_bounds
                            yield out0, out1
                    return
                # elif len0 > 0 and len2 > 0:
                #     # this logic will resolve more conflicts automatically,
                #     # but unresolved conflicts may sometimes look confusing
                #     # as the line numbers in ancestor file will be
                #     # interpolated and may not reflect the actual changes
                #     matcher = self._matcher(
                #         None, texts[0][l0:h0], texts[2][l2:h2])
                #     if len0 > len2:
                #         maxindex = 1
                #         maxlen = len0
                #     else:
                #         maxindex = 3
                #         maxlen = len2
                #     for chunk in matcher.get_opcodes():
                #         new_start = l1 + len1 * chunk[maxindex] / maxlen
                #         new_end = l1 + len1 * chunk[maxindex + 1] / maxlen
                #         out0_bounds = (
                #             new_start, new_end, l0 + chunk[1], l0 + chunk[2])
                #         out1_bounds = (
                #             new_start, new_end, l2 + chunk[3], l2 + chunk[4])
                #         if chunk[0] == 'equal':
                #             out0 = ('replace',) + out0_bounds
                #             out1 = ('replace',) + out1_bounds
                #             yield out0, out1
                #         else:
                #             out0 = ('conflict',) + out0_bounds
                #             out1 = ('conflict',) + out1_bounds
                #             yield out0, out1
                #     return
                else:
                    # some tricks to resolve even more conflicts automatically
                    # unfortunately the resulting chunks cannot be used to
                    # highlight changes but hey, they are good enough to merge
                    # the resulting file :)
                    chunktype = using[0][0][0]
                    for chunkarr in using:
                        for chunk in chunkarr:
                            if chunk[0] != chunktype:
                                chunktype = None
                                break
                        if not chunktype:
                            break
                    if chunktype == 'delete':
                        # delete + delete -> split into delete/conflict
                        seq0 = seq1 = None
                        while 1:
                            if seq0 is None:
                                try:
                                    seq0 = using[0].pop(0)
                                    i0 = seq0[1]
                                    end0 = seq0[4]
                                except IndexError:
                                    break
                            if seq1 is None:
                                try:
                                    seq1 = using[1].pop(0)
                                    i1 = seq1[1]
                                    end1 = seq1[4]
                                except IndexError:
                                    break
                            highstart = max(i0, i1)
                            if i0 != i1:
                                out0 = (
                                    'conflict', i0 - highstart + i1, highstart,
                                    seq0[3] - highstart + i1, seq0[3]
                                )
                                out1 = (
                                    'conflict', i1 - highstart + i0, highstart,
                                    seq1[3] - highstart + i0, seq1[3]
                                )
                                yield out0, out1
                            lowend = min(seq0[2], seq1[2])
                            if highstart != lowend:
                                out0 = (
                                    'delete', highstart, lowend,
                                    seq0[3], seq0[4]
                                )
                                out1 = (
                                    'delete', highstart, lowend,
                                    seq1[3], seq1[4]
                                )
                                yield out0, out1
                            i0 = i1 = lowend
                            if lowend == seq0[2]:
                                seq0 = None
                            if lowend == seq1[2]:
                                seq1 = None

                        if seq0:
                            out0 = (
                                'conflict', i0, seq0[2],
                                seq0[3], seq0[4]
                            )
                            out1 = (
                                'conflict', i0, seq0[2],
                                end1, end1 + seq0[2] - i0
                            )
                            yield out0, out1
                        elif seq1:
                            out0 = (
                                'conflict', i1, seq1[2],
                                end0, end0 + seq1[2] - i1
                            )
                            out1 = (
                                'conflict', i1,
                                seq1[2], seq1[3], seq1[4]
                            )
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
                    self.unresolved[hi:] = [
                        c + sizechange for c in self.unresolved[hi:]
                    ]
                self.unresolved[lo:hi] = []

        return super().change_sequence(sequence, startidx, sizechange, texts)

    def get_unresolved_count(self):
        return len(self.unresolved)


class Merger(diffutil.Differ):

    def __init__(self, ):
        self.differ = AutoMergeDiffer()
        self.differ.auto_merge = True
        self.differ.unresolved = []
        self.texts = []

    def initialize(self, sequences, texts):
        step = self.differ.set_sequences_iter(sequences)
        while next(step) is None:
            yield None
        self.texts = texts
        yield 1

    def _apply_change(self, text, change, mergedtext):
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

    def merge_3_files(self, mark_conflicts=True):
        self.unresolved = []
        lastline = 0
        mergedline = 0
        mergedtext = []
        for change in self.differ.all_changes():
            yield None
            low_mark = lastline
            if change[0] is not None:
                low_mark = change[0][LO]
            if change[1] is not None:
                if change[1][LO] > low_mark:
                    low_mark = change[1][LO]
            for i in range(lastline, low_mark, 1):
                mergedtext.append(self.texts[1][i])
            mergedline += low_mark - lastline
            lastline = low_mark
            if (change[0] is not None and change[1] is not None and
                    change[0][0] == 'conflict'):
                high_mark = max(change[0][HI], change[1][HI])
                if mark_conflicts:
                    if low_mark < high_mark:
                        for i in range(low_mark, high_mark):
                            mergedtext.append("(??)" + self.texts[1][i])
                            self.unresolved.append(mergedline)
                            mergedline += 1
                    else:
                        mergedtext.append("(??)")
                        self.unresolved.append(mergedline)
                        mergedline += 1
                    lastline = high_mark
            elif change[0] is not None:
                lastline += self._apply_change(
                    self.texts[0], change[0], mergedtext)
                mergedline += change[0][HI + 2] - change[0][LO + 2]
            else:
                lastline += self._apply_change(
                    self.texts[2], change[1], mergedtext)
                mergedline += change[1][HI + 2] - change[1][LO + 2]
        baselen = len(self.texts[1])
        for i in range(lastline, baselen, 1):
            mergedtext.append(self.texts[1][i])

        # FIXME: We need to obtain the original line endings from the lines
        # that were merged and use those here instead of assuming '\n'.
        yield "\n".join(mergedtext)

    def merge_2_files(self, fromindex, toindex):
        self.unresolved = []
        lastline = 0
        mergedtext = []
        for change in self.differ.pair_changes(toindex, fromindex):
            yield None
            if change[0] == 'conflict':
                low_mark = change[HI]
            else:
                low_mark = change[LO]
            for i in range(lastline, low_mark):
                mergedtext.append(self.texts[toindex][i])
            lastline = low_mark
            if change[0] != 'conflict':
                lastline += self._apply_change(
                    self.texts[fromindex], change, mergedtext)
        baselen = len(self.texts[toindex])
        for i in range(lastline, baselen):
            mergedtext.append(self.texts[toindex][i])

        # FIXME: We need to obtain the original line endings from the lines
        # that were merged and use those here instead of assuming '\n'.
        yield "\n".join(mergedtext)
