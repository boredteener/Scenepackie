import unittest
import numpy as np
from scenepackie.core import group_matches, normalize, similarity, clock

class CoreTests(unittest.TestCase):
    def test_adjacent_times_merge(self):
        clips = group_matches([10, 10.8, 11.6, 40], 100, padding=1, max_gap=2)
        self.assertEqual(len(clips), 2)
        self.assertAlmostEqual(clips[0].start, 9)
        self.assertAlmostEqual(clips[0].end, 12.6)
    def test_empty(self):
        self.assertEqual(group_matches([], 60), [])
    def test_clamps(self):
        clips = group_matches([0, 59.5], 60)
        self.assertEqual(clips[0].start, 0)
        self.assertEqual(clips[-1].end, 60)
    def test_clock(self):
        self.assertEqual(clock(3661), '01:01:01')
    def test_features_normalized(self):
        x = normalize(np.array([3,4], dtype=np.float32))
        self.assertAlmostEqual(similarity(x,x), 1)

if __name__ == '__main__':
    unittest.main()
