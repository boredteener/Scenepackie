import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scenepackie.cache import (
    clear_saved_scans, read_snapshot, save_characters,
    save_clips, snapshot_path,
)
from scenepackie.core import Clip, FaceGroup


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = os.environ.get("SCENEPACKIE_CACHE_DIR")
        os.environ["SCENEPACKIE_CACHE_DIR"] = str(Path(self.tmp.name) / "cache")
        self.movie = Path(self.tmp.name) / "movie.mp4"
        self.movie.write_bytes(b"video example")

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("SCENEPACKIE_CACHE_DIR", None)
        else:
            os.environ["SCENEPACKIE_CACHE_DIR"] = self.previous
        self.tmp.cleanup()

    def test_save_and_restore_clip_choices(self):
        faces = [FaceGroup(b"portrait", [np.ones(128, dtype=np.float32)], hits=7)]
        save_characters(str(self.movie), faces)
        groups, matches = read_snapshot(str(self.movie))
        self.assertEqual(len(groups), 1)
        self.assertEqual(matches, {})
        save_clips(str(self.movie), 0, [Clip(10, 15, keep=False)])
        groups, matches = read_snapshot(str(self.movie))
        self.assertEqual(groups[0].hits, 7)
        self.assertEqual(matches["0"][0].keep, False)
        self.assertEqual(matches["0"][0].end, 15)

    def test_modified_video_disables_old_cache(self):
        save_characters(str(self.movie), [])
        self.movie.write_bytes(b"changed movie")
        self.assertIsNone(read_snapshot(str(self.movie)))

    def test_broken_file_fails_safely(self):
        save_characters(str(self.movie), [])
        snapshot_path(str(self.movie)).write_text("not json", encoding="utf-8")
        self.assertIsNone(read_snapshot(str(self.movie)))

    def test_clear_never_deletes_movie_or_exports(self):
        save_characters(str(self.movie), [])
        export = Path(self.tmp.name) / "finished.mp4"
        export.write_bytes(b"export")
        count, size = clear_saved_scans()
        self.assertEqual(count, 1)
        self.assertGreater(size, 0)
        self.assertTrue(self.movie.exists())
        self.assertTrue(export.exists())
        self.assertIsNone(read_snapshot(str(self.movie)))


if __name__ == "__main__":
    unittest.main()
