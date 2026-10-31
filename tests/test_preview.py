import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scenepackie.core import Clip, FaceGroup
from scenepackie.cache import read_snapshot, save_characters, save_clips, clear_saved_scans
from scenepackie.preview import preview_args


class MacPreviewTests(unittest.TestCase):
    def test_quicktime_compatible_container(self):
        args = preview_args("ffmpeg", "movie.mkv", Clip(12.5, 18.5), Path("preview.mp4"))
        for setting in ("libx264", "baseline", "avc1", "yuv420p", "aac", "+faststart"):
            self.assertIn(setting, args)
        self.assertEqual(args[-2:], ["mp4", "preview.mp4"])
        self.assertIn("0:a:0?", args)

    def test_cannot_preview_empty_clip(self):
        with self.assertRaises(ValueError):
            preview_args("ffmpeg", "movie.mp4", Clip(4, 4), Path("out.mp4"))

    def test_saved_scans_survive_relaunch(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = os.environ.get("SCENEPACKIE_CACHE_DIR")
            os.environ["SCENEPACKIE_CACHE_DIR"] = str(Path(tmp) / "cache")
            try:
                movie = Path(tmp) / "movie.mp4"
                movie.write_bytes(b"movie")
                save_characters(str(movie), [FaceGroup(b"portrait", [np.ones(128, dtype=np.float32)], hits=5)])
                save_clips(str(movie), 0, [Clip(5, 10, keep=False), Clip(20, 25, keep=True)])
                # Simulate reopening the app with no in-memory data.
                faces, matches = read_snapshot(str(movie))
                self.assertEqual(len(faces), 1)
                self.assertEqual([c.keep for c in matches["0"]], [False, True])
                count, _ = clear_saved_scans()
                self.assertEqual(count, 1)
                self.assertTrue(movie.exists())
                self.assertIsNone(read_snapshot(str(movie)))
            finally:
                if original is None:
                    os.environ.pop("SCENEPACKIE_CACHE_DIR", None)
                else:
                    os.environ["SCENEPACKIE_CACHE_DIR"] = original


if __name__ == "__main__":
    unittest.main()
