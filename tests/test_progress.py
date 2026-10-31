import unittest

from scenepackie.progress import estimate_remaining


class ProgressTests(unittest.TestCase):
    def test_estimate_halfway(self):
        self.assertEqual(estimate_remaining(30, 0.5), 30)

    def test_estimate_nearly_done(self):
        self.assertEqual(estimate_remaining(100, 0.9), 11)

    def test_no_early_guess(self):
        self.assertIsNone(estimate_remaining(1, 0.5))
        self.assertIsNone(estimate_remaining(8, 0.01))

    def test_no_estimate_once_finished_or_invalid(self):
        for fraction in (1, 2, float('nan'), float('inf')):
            self.assertIsNone(estimate_remaining(10, fraction))
        self.assertIsNone(estimate_remaining(float('nan'), 0.5))


if __name__ == '__main__':
    unittest.main()
