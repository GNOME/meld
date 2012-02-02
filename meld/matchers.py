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

import difflib


def find_common_prefix(a, b):
    if not a or not b:
        return 0
    if a[0] == b[0]:
        pointermax = min(len(a), len(b))
        pointermid = pointermax
        pointermin = 0
        while pointermin < pointermid:
            if a[pointermin:pointermid] == b[pointermin:pointermid]:
                pointermin = pointermid
            else:
                pointermax = pointermid
            pointermid = int((pointermax - pointermin) / 2 + pointermin)
        return pointermid
    return 0


def find_common_suffix(a, b):
    if not a or not b:
        return 0
    if a[-1] == b[-1]:
        pointermax = min(len(a), len(b))
        pointermid = pointermax
        pointermin = 0
        while pointermin < pointermid:
            if (a[-pointermid:len(a) - pointermin] == b[-pointermid:len(b) - pointermin]):
                pointermin = pointermid
            else:
                pointermax = pointermid
            pointermid = int((pointermax - pointermin) / 2 + pointermin)
        return pointermid
    return 0


class MyersSequenceMatcher(difflib.SequenceMatcher):

    def __init__(self, isjunk=None, a="", b=""):
        if isjunk is not None:
            raise NotImplementedError('isjunk is not supported yet')
        self.a = a
        self.b = b
        self.matching_blocks = self.opcodes = None
        #fields needed by preprocessor so that preprocessing may shared by more than 1 LCS algorithm
        self.aindex = {}
        self.bindex = {}
        self.common_prefix = self.common_suffix = 0
        self.lines_discarded = False

    def get_matching_blocks(self):
        if self.matching_blocks is None:
            for i in self.initialise():
                pass
        return self.matching_blocks

    def get_difference_opcodes(self):
        return filter(lambda x: x[0] != "equal", self.get_opcodes())

    def preprocess(self):
        """
        Pre-processing optimizations:
        1) remove common prefix and common suffix
        2) remove lines that do not match
        """
        a = self.a
        b = self.b
        aindex = self.aindex = {}
        bindex = self.bindex = {}
        n = len(a)
        m = len(b)
        # remove common prefix and common suffix
        self.common_prefix = self.common_suffix = 0
        self.common_prefix = find_common_prefix(a, b)
        if self.common_prefix > 0:
            a = a[self.common_prefix:]
            b = b[self.common_prefix:]
            n -= self.common_prefix
            m -= self.common_prefix

        if n > 0 and m > 0:
            self.common_suffix = find_common_suffix(a, b)
            if self.common_suffix > 0:
                a = a[:n - self.common_suffix]
                b = b[:m - self.common_suffix]
                n -= self.common_suffix
                m -= self.common_suffix

        # discard lines that do not match any line from the other file
        if n > 0 and m > 0:
            aset = frozenset(a)
            bset = frozenset(b)
            a2 = []
            b2 = []
            j = 0
            for i, newline in enumerate(b):
                if newline in aset:
                    b2.append(newline)
                    bindex[j] = i
                    j += 1
            k = 0
            for i, origline in enumerate(a):
                if origline in bset:
                    a2.append(a[i])
                    aindex[k] = i
                    k += 1
            # We only use the optimised result if it's worthwhile. The constant
            # represents a heuristic of how many lines constitute 'worthwhile'.
            self.lines_discarded = m - j > 10 or n - k > 10
            if self.lines_discarded:
                a = a2
                b = b2
        return (a, b)

    def postprocess(self):
        mb = [self.matching_blocks[-1]]
        i = len(self.matching_blocks) - 2
        while i >= 0:
            cur_a, cur_b, cur_len = self.matching_blocks[i]
            i -= 1
            while i >= 0:
                prev_a, prev_b, prev_len = self.matching_blocks[i]
                if prev_b + prev_len == cur_b or prev_a + prev_len == cur_a:
                    prev_slice_a = self.a[cur_a - prev_len:cur_a]
                    prev_slice_b = self.b[cur_b - prev_len:cur_b]
                    if prev_slice_a == prev_slice_b:
                        cur_b -= prev_len
                        cur_a -= prev_len
                        cur_len += prev_len
                        i -= 1
                        continue
                break
            mb.append((cur_a, cur_b, cur_len))
        mb.reverse()
        self.matching_blocks = mb

    def build_matching_blocks(self, lastsnake, snakes):
        """
        Build list of matching blocks based on snakes taking into consideration all preprocessing
        optimizations:
        1) add separate blocks for common prefix and common suffix
        2) shift positions and split blocks based on the list of discarded non-matching lines
        """
        self.matching_blocks = matching_blocks = []

        common_prefix = self.common_prefix
        common_suffix = self.common_suffix
        aindex = self.aindex
        bindex = self.bindex
        while lastsnake != None:
            lastsnake, x, y, snake = snakes[lastsnake]
            if self.lines_discarded:
                # split snakes if needed because of discarded lines
                x += snake - 1
                y += snake - 1
                xprev = aindex[x] + common_prefix
                yprev = bindex[y] + common_prefix
                if snake > 1:
                    newsnake = 1
                    for i in range(1, snake):
                        x -= 1
                        y -= 1
                        xnext = aindex[x] + common_prefix
                        ynext = bindex[y] + common_prefix
                        if (xprev - xnext != 1) or (yprev - ynext != 1):
                            matching_blocks.insert(0, (xprev, yprev, newsnake))
                            newsnake = 0
                        xprev = xnext
                        yprev = ynext
                        newsnake += 1
                    matching_blocks.insert(0, (xprev, yprev, newsnake))
                else:
                    matching_blocks.insert(0, (xprev, yprev, snake))
            else:
                matching_blocks.insert(0, (x + common_prefix, y + common_prefix, snake))
        if common_prefix:
            matching_blocks.insert(0, (0, 0, common_prefix))
        if common_suffix:
            matching_blocks.append((len(self.a) - common_suffix, len(self.b) - common_suffix, common_suffix))
        matching_blocks.append((len(self.a), len(self.b), 0))
        # clean-up to free memory
        self.aindex = self.bindex = None

    def initialise(self):
        """
        Optimized implementation of the O(NP) algorithm described by Sun Wu,
        Udi Manber, Gene Myers, Webb Miller
        ("An O(NP) Sequence Comparison Algorithm", 1989)
        http://research.janelia.org/myers/Papers/np_diff.pdf
        """

        a, b = self.preprocess()
        m = len(a)
        n = len(b)
        middle = m + 1
        lastsnake = None
        delta = n - m + middle
        dmin = min(middle, delta)
        dmax = max(middle, delta)
        snakes = []
        if n > 0 and m > 0:
            size = n + m + 2
            fp = [(-1, None)] * size
            p = -1
            while True:
                p += 1
                if not p % 100:
                    yield None
                # move along vertical edge
                yv = -1
                node = None
                for km in range(dmin - p, delta, 1):
                    t = fp[km + 1]
                    if yv < t[0]:
                        yv, node = t
                    else:
                        yv += 1
                    x = yv - km + middle
                    if x < m and yv < n and a[x] == b[yv]:
                        snake = x
                        x += 1
                        yv += 1
                        while x < m and yv < n and a[x] == b[yv]:
                            x += 1
                            yv += 1
                        snake = x - snake
                        snakes.append((node, x - snake, yv - snake, snake))
                        node = len(snakes) - 1
                    fp[km] = (yv, node)
                # move along horizontal edge
                yh = -1
                node = None
                for km in range(dmax + p, delta, -1):
                    t = fp[km - 1]
                    if yh <= t[0]:
                        yh, node = t
                        yh += 1
                    x = yh - km + middle
                    if x < m and yh < n and a[x] == b[yh]:
                        snake = x
                        x += 1
                        yh += 1
                        while x < m and yh < n and a[x] == b[yh]:
                            x += 1
                            yh += 1
                        snake = x - snake
                        snakes.append((node, x - snake, yh - snake, snake))
                        node = len(snakes) - 1
                    fp[km] = (yh, node)
                # point on the diagonal that leads to the sink
                if yv < yh:
                    y, node = fp[delta + 1]
                else:
                    y, node = fp[delta - 1]
                    y += 1
                x = y - delta + middle
                if x < m and y < n and a[x] == b[y]:
                    snake = x
                    x += 1
                    y += 1
                    while x < m and y < n and a[x] == b[y]:
                        x += 1
                        y += 1
                    snake = x - snake
                    snakes.append((node, x - snake, y - snake, snake))
                    node = len(snakes) - 1
                fp[delta] = (y, node)
                if y >= n:
                    lastsnake = node
                    break
        self.build_matching_blocks(lastsnake, snakes)
        self.postprocess()
        yield 1
