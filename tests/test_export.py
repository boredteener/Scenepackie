import unittest
from pathlib import Path
from scenepackie.core import concat_manifest, Clip


class ExportTests(unittest.TestCase):
    def test_manifest_in_order(self):
        manifest = concat_manifest([Path("first.mp4"), Path("second.mp4")])
        self.assertEqual(len(manifest.splitlines()), 2)
        self.assertIn("first.mp4", manifest.splitlines()[0])
        self.assertIn("second.mp4", manifest.splitlines()[1])

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            concat_manifest([])

    def test_selection(self):
        clips = [Clip(0, 3), Clip(10, 12, keep=False)]
        self.assertEqual(len([c for c in clips if c.keep]), 1)


if __name__ == "__main__":
    unittest.main()
