
import unittest

from meld.matchers import myers


class MatchersTests(unittest.TestCase):

    def testBasicMatcher(self):
        a = list('abcbdefgabcdefg')
        b = list('gfabcdefcd')
        r = [(0, 2, 3), (4, 5, 3), (10, 8, 2), (15, 10, 0)]
        matcher = myers.MyersSequenceMatcher(None, a, b)
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def testPostprocessingCleanup(self):
        a = list('abcfabgcd')
        b = list('afabcgabgcabcd')
        r = [(0, 2, 3), (4, 6, 3), (7, 12, 2), (9, 14, 0)]
        matcher = myers.MyersSequenceMatcher(None, a, b)
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def testInlineMatcher(self):
        a = 'red, blue, yellow, white'
        b = 'black green, hue, white'
        r = [(17, 16, 7), (24, 23, 0)]
        matcher = myers.InlineMyersSequenceMatcher(None, a, b)
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def testSyncPointMatcher0(self):
        a = list('012a3456c789')
        b = list('0a3412b5678')
        r = [(0, 0, 1), (3, 1, 3), (6, 7, 2), (9, 9, 2), (12, 11, 0)]
        matcher = myers.SyncPointMyersSequenceMatcher(None, a, b)
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def testSyncPointMatcher1(self):
        a = list('012a3456c789')
        b = list('0a3412b5678')
        r = [(0, 0, 1), (1, 4, 2), (6, 7, 2), (9, 9, 2), (12, 11, 0)]
        matcher = myers.SyncPointMyersSequenceMatcher(None, a, b, [(3, 6)])
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

    def testSyncPointMatcher2(self):
        a = list('012a3456c789')
        b = list('02a341b5678')
        r = [(0, 0, 1), (2, 1, 1), (3, 2, 3), (9, 9, 2), (12, 11, 0)]
        matcher = myers.SyncPointMyersSequenceMatcher(
            None, a, b, [(3, 2), (8, 6)])
        blocks = matcher.get_matching_blocks()
        self.assertEqual(blocks, r)

if __name__ == '__main__':
    unittest.main()
