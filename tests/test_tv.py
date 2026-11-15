import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np

from scenepackie.cache import clear_saved_scans
from scenepackie.core import Cancelled, Clip, FaceGroup
from scenepackie.tv import (blank_state, combine_faces, Episode, find_episodes,
                            pack_clips, read_state, save_state, scan_episodes,
                            selected_entries)
from scenepackie.tv_export import export_tv


class TVTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous = os.environ.get("SCENEPACKIE_CACHE_DIR")
        os.environ["SCENEPACKIE_CACHE_DIR"] = str(self.root / "cache")
        self.show = self.root / "Example Show"
        for season in (1, 2):
            season_dir = self.show / f"Season {season}"
            season_dir.mkdir(parents=True)
            for episode in (1, 2):
                (season_dir / f"Episode {episode:02d}.mp4").write_bytes(b"source")
        self.episodes = find_episodes(str(self.show), 2)

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("SCENEPACKIE_CACHE_DIR", None)
        else:
            os.environ["SCENEPACKIE_CACHE_DIR"] = self.previous
        self.temp.cleanup()

    def test_episode_order_and_names(self):
        self.assertEqual([episode.label for episode in self.episodes],
                         ["S01E01", "S01E02", "S02E01", "S02E02"])
        self.assertEqual(self.episodes[2].season, 2)

    def test_missing_folder_and_empty_season(self):
        with self.assertRaisesRegex(ValueError, "Season 3"):
            find_episodes(str(self.show), 3)
        for episode in (self.show / "Season 1").iterdir():
            episode.unlink()
        with self.assertRaisesRegex(ValueError, "Season 1"):
            find_episodes(str(self.show), 2)

    def test_save_restore_and_invalidate_when_episode_changes(self):
        state = blank_state()
        state["selected"] = 0
        state["clips"]["S01E01"] = pack_clips([Clip(1, 3, keep=False)])
        save_state(str(self.show), self.episodes, "live", state)
        recovered = read_state(str(self.show), self.episodes, "live")
        self.assertEqual(recovered["clips"]["S01E01"][0]["keep"], False)
        self.assertEqual(read_state(str(self.show), self.episodes, "animated"),
                         blank_state())
        (self.show / "Season 2" / "Episode 02.mp4").write_bytes(b"new episode")
        self.assertEqual(read_state(str(self.show), self.episodes, "live"),
                         blank_state())

    def test_clear_saved_scans_does_not_delete_episodes(self):
        save_state(str(self.show), self.episodes, "live", blank_state())
        count, _ = clear_saved_scans()
        self.assertEqual(count, 1)
        self.assertTrue(all(Path(e.path).is_file() for e in self.episodes))

    def test_cancelled_scan_keeps_finished_episodes(self):
        state = blank_state()
        self.episodes = self.episodes[:2]
        group = FaceGroup(b"portrait", [np.ones(128, dtype=np.float32)], hits=5)
        cancel = threading.Event()
        attempts = []

        class FakeScanner:
            def find_clips(self, path, _group, _cancel, progress):
                attempts.append(path)
                if len(attempts) == 2:
                    cancel.set()
                    raise Cancelled()
                progress("scanning", 1.0)
                return [Clip(4, 7)]

        with patch("scenepackie.tv.FaceScanner", FakeScanner):
            with self.assertRaises(Cancelled):
                scan_episodes(str(self.show), self.episodes, "live", state,
                              cancel, lambda *_: None, group=group)
        resumed = read_state(str(self.show), self.episodes, "live")
        self.assertIn("S01E01", resumed["clips"])
        self.assertNotIn("S01E02", resumed["clips"])
        cancel.clear()
        with patch("scenepackie.tv.FaceScanner", FakeScanner):
            scan_episodes(str(self.show), self.episodes, "live", resumed,
                          cancel, lambda *_: None, group=group)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(resumed["clips"]), 2)

    def test_merged_face_group(self):
        vec = np.ones(128, dtype=np.float32) / np.sqrt(128)
        existing = [FaceGroup(b"a", [vec], hits=5)]
        merged = combine_faces(existing, [FaceGroup(b"b", [vec], hits=3)])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].hits, 8)

    @unittest.skipUnless(sys.platform == "darwin", "Mac native video export check")
    def test_real_tv_export_decodes_on_mac(self):
        from scenepackie.core import binary
        ffmpeg = binary("ffmpeg")
        for episode in (self.episodes[0], self.episodes[2]):
            subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=1.6",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1.6",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", str(episode.path),
            ], check=True, capture_output=True, timeout=40)
        state = blank_state()
        state["clips"]["S01E01"] = pack_clips([Clip(0.15, 1.10)])
        state["clips"]["S02E01"] = pack_clips([Clip(0.25, 1.25)])
        root = export_tv(str(self.show), self.episodes, state, str(self.root),
                         False, threading.Event(), lambda *_: None)
        produced = list(root.rglob("*.mp4"))
        self.assertEqual(len(produced), 5)
        for path in produced:
            check = subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                "-i", str(path), "-frames:v", "1", "-f", "null", "-"
            ], capture_output=True, timeout=30)
            self.assertEqual(check.returncode, 0, f"{path.name}: {check.stderr.decode(errors='replace')}")

    def test_tv_exports_order_and_season_files(self):
        state = blank_state()
        state["clips"]["S01E01"] = pack_clips([Clip(1, 3)])
        state["clips"]["S01E02"] = pack_clips([Clip(10, 14, keep=False)])
        state["clips"]["S02E02"] = pack_clips([Clip(5, 9)])
        encoded, joins = [], []

        def fake_encode(source, start, duration, target, cancel):
            encoded.append((Path(source).name, start, duration))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"mp4")

        def fake_join(paths, target, cancel):
            joins.append((target.name, [p.name for p in paths]))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"joined")

        with patch("scenepackie.tv_export._encode", fake_encode), \
             patch("scenepackie.tv_export._join", fake_join):
            result = export_tv(str(self.show), self.episodes, state,
                               str(self.root), True, threading.Event(), lambda *_: None)
        self.assertTrue(result.is_file())
        folder = self.root / "Example Show_scenepack"
        self.assertTrue((folder / "Season 1" / "Season_1_scenepack.mp4").exists())
        self.assertTrue((folder / "Season 2" / "Season_2_scenepack.mp4").exists())
        self.assertTrue((folder / "Full_Character_Scenepack.mp4").exists())
        self.assertEqual(len(encoded), 2)
        self.assertEqual(joins[-1][0], "Full_Character_Scenepack.mp4")
        self.assertEqual(len(joins[-1][1]), 2)
        data = json.loads((folder / "clips.json").read_text())
        self.assertEqual([c["episode"] for c in data["clips"]], ["S01E01", "S02E02"])


if __name__ == "__main__":
    unittest.main()
