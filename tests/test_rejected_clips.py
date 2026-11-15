"""Explicit-No reminders are separate from ordinary unchecked selections."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
import cv2

from app import Scenepackie
from scenepackie.core import Clip, FaceGroup
from scenepackie.cache import read_snapshot, save_characters, save_clips
from scenepackie.animation import encode_reference
from scenepackie.animation_cache import read_animation, save_animation
from scenepackie.tv import Episode, blank_state, pack_clips, read_state, save_state, selected_entries


class TestRejectedPreview(unittest.TestCase):
    def app(self, clip=None):
        app = object.__new__(Scenepackie)
        app.preview_dialog = None
        app.preview_fallback_dialog = None
        app.page = "clips"
        app.source = "movie.mp4"
        app.preview_token = 0
        app.preview_process = None
        app.preview_request = None
        clip = clip or Clip(5.0, 8.0)
        app.clips = [clip]
        app.clip_checkbox_vars = {id(clip): Mock()}
        app._save_selection = Mock()
        app._update_selected = Mock()
        app.status = Mock()
        return app, clip

    def test_no_sets_rejected_and_unchecks(self):
        app, clip = self.app()
        app._finish_preview_choice(False, clip)
        self.assertFalse(clip.keep)
        self.assertTrue(clip.rejected)
        app.clip_checkbox_vars[id(clip)].set.assert_called_with(False)
        app._save_selection.assert_called_once()

    def test_normal_unchecked_clip_has_no_rejection_warning(self):
        app, clip = self.app(Clip(5, 8, keep=False))
        self.assertFalse(clip.rejected)
        with patch("app.sys.platform", "win32"), patch("app.messagebox.showinfo") as info:
            app._launch_preview = Mock()
            app.preview_clip(clip, "movie.mp4", "Clip 003")
        info.assert_not_called()
        app._launch_preview.assert_called_once()

    def test_replaying_declined_clip_warns_but_can_still_play(self):
        app, clip = self.app(Clip(5, 8, keep=False, rejected=True))
        app._launch_preview = Mock()
        with patch("app.sys.platform", "win32"), patch("app.messagebox.showinfo") as info:
            app.preview_clip(clip, "movie.mp4", "Clip 003")
        info.assert_called_once()
        self.assertIn("you said no to this clip", str(info.call_args))
        app._launch_preview.assert_called_once()

    def test_rejected_clip_cannot_be_readded_by_yes(self):
        app, clip = self.app(Clip(5, 8, keep=False, rejected=True))
        app._finish_preview_choice(True, clip)
        self.assertFalse(clip.keep)
        self.assertTrue(clip.rejected)
        app._save_selection.assert_not_called()

    def test_rejected_clip_does_not_reopen_yes_no_after_playback(self):
        app, clip = self.app(Clip(5, 8, keep=False, rejected=True))
        app.preview_token = 2
        app.preview_process = Mock()
        app.preview_process.poll.return_value = 0
        app.preview_request = (2, clip, "Clip 003")
        app._ask_preview_choice = Mock()
        app._poll_preview()
        app._ask_preview_choice.assert_not_called()

    def test_manual_checkbox_reselect_clears_warning(self):
        app, clip = self.app(Clip(5, 8, keep=False, rejected=True))
        app._manual_clip_selection(clip, True)
        self.assertTrue(clip.keep)
        self.assertFalse(clip.rejected)
        app._save_selection.assert_called_once()
        app._launch_preview = Mock()
        with patch("app.messagebox.showinfo") as info:
            app.preview_clip(clip, "movie.mp4", "Clip 003")
        info.assert_not_called()

    def test_select_all_reverses_explicit_no(self):
        app, clip = self.app(Clip(5, 8, keep=False, rejected=True))
        app.tv_active = False
        app.clip_vars = [Mock()]
        app.set_all_clips(True)
        self.assertTrue(clip.keep)
        self.assertFalse(clip.rejected)
        app.clip_vars[0].set.assert_called_once_with(True)

    def test_unchecking_without_no_does_not_mark_rejected(self):
        app, clip = self.app(Clip(5, 8, keep=True))
        app._manual_clip_selection(clip, False)
        self.assertFalse(clip.keep)
        self.assertFalse(clip.rejected)

    def test_macos_replay_of_rejected_clip_skips_review_window(self):
        app, clip = self.app(Clip(5, 8, keep=False, rejected=True))
        with patch("app.subprocess.Popen") as player, patch("app.tk.Toplevel") as dialog:
            app._open_quicktime_preview(0, clip, "Clip 003", "/tmp/example.mp4")
        player.assert_called_once()
        dialog.assert_not_called()


class TestRejectedClipPersistence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous = os.environ.get("SCENEPACKIE_CACHE_DIR")
        os.environ["SCENEPACKIE_CACHE_DIR"] = str(self.root / "cache")
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"video")

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("SCENEPACKIE_CACHE_DIR", None)
        else:
            os.environ["SCENEPACKIE_CACHE_DIR"] = self.previous
        self.temp.cleanup()

    def test_live_action_rejection_survives_reload(self):
        faces = [FaceGroup(b"portrait", [np.ones(128, dtype=np.float32)])]
        save_characters(str(self.source), faces)
        save_clips(str(self.source), 0, [Clip(1, 2, keep=False, rejected=True),
                                        Clip(3, 4, keep=False)])
        _, matches = read_snapshot(str(self.source))
        self.assertEqual([(x.keep, x.rejected) for x in matches["0"]],
                         [(False, True), (False, False)])

    def test_animated_rejection_survives_reload(self):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.circle(image, (50, 50), 20, (90, 120, 220), -1)
        ref = encode_reference(image)
        save_animation(str(self.source), [ref], [Clip(1, 2, keep=False, rejected=True),
                                                 Clip(3, 4, keep=True)])
        _, clips = read_animation(str(self.source))
        self.assertTrue(clips[0].rejected)
        self.assertFalse(clips[1].rejected)

    def test_tv_rejection_survives_reload(self):
        show = self.root / "Show"
        season = show / "Season 1"
        season.mkdir(parents=True)
        episode = season / "Episode 01.mp4"
        episode.write_bytes(b"first")
        eps = [Episode(1, 1, str(episode))]
        state = blank_state()
        state["clips"]["S01E01"] = pack_clips([
            Clip(1, 2, keep=False, rejected=True), Clip(3, 4, keep=False)])
        save_state(str(show), eps, "animated", state)
        loaded = read_state(str(show), eps, "animated")
        clips = selected_entries(eps, loaded)
        self.assertEqual([c.rejected for _, c in clips], [True, False])

    def test_selected_clip_never_remains_rejected(self):
        face = [FaceGroup(b"portrait", [np.ones(128, dtype=np.float32)])]
        save_characters(str(self.source), face)
        save_clips(str(self.source), 0, [Clip(1, 2, keep=True, rejected=True)])
        _, matches = read_snapshot(str(self.source))
        self.assertFalse(matches["0"][0].rejected)


if __name__ == "__main__":
    unittest.main()
