
import unittest

from meld.matchers import myers


class MatchersTests(unittest.TestCase):

    def test_basic_matcher(self):
        a = list('abcbdefgabcdefg')
        b = list('gfabcdefcd')
        r = [(0, 2, 3), (4, 5, 3), (10, 8, 2), (15, 10, 0)]
        matcher = myers.MyersSequenceMatcher(None, a, b)
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def test_postprocessing_cleanup(self):
        a = list('abcfabgcd')
        b = list('afabcgabgcabcd')
        r = [(0, 2, 3), (4, 6, 3), (7, 12, 2), (9, 14, 0)]
        matcher = myers.MyersSequenceMatcher(None, a, b)
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def test_inline_matcher(self):
        a = 'red, blue, yellow, white'
        b = 'black green, hue, white'
        r = [(17, 16, 7), (24, 23, 0)]
        matcher = myers.InlineMyersSequenceMatcher(None, a, b)
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def test_sync_point_matcher0(self):
        a = list('012a3456c789')
        b = list('0a3412b5678')
        r = [(0, 0, 1), (3, 1, 3), (6, 7, 2), (9, 9, 2), (12, 11, 0)]
        matcher = myers.SyncPointMyersSequenceMatcher(None, a, b)
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def test_sync_point_matcher2(self):
        a = list('012a3456c789')
        b = list('0a3412b5678')
        r = [(0, 0, 1), (1, 4, 2), (6, 7, 2), (9, 9, 2), (12, 11, 0)]
        matcher = myers.SyncPointMyersSequenceMatcher(None, a, b, [(3, 6)])
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def test_sync_point_matcher3(self):
        a = list('012a3456c789')
        b = list('02a341b5678')
        r = [(0, 0, 1), (2, 1, 1), (3, 2, 3), (9, 9, 2), (12, 11, 0)]
        matcher = myers.SyncPointMyersSequenceMatcher(
            None, a, b, [(3, 2), (8, 6)])
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)
