"""Regression checks for the preview yes/no workflow without a display server."""
import unittest
from unittest.mock import Mock

from app import Scenepackie
from scenepackie.core import Clip


class TestPreviewReview(unittest.TestCase):
    def make_app(self):
        app = object.__new__(Scenepackie)
        app.preview_dialog = None
        app.page = "clips"
        clip = Clip(5, 8, keep=False)
        app.clips = [clip]
        app.clip_checkbox_vars = {id(clip): Mock()}
        app._save_selection = Mock()
        app._update_selected = Mock()
        app.status = Mock()
        return app, clip

    def test_yes_selects_exact_clip_and_saves(self):
        app, clip = self.make_app()
        app._finish_preview_choice(True, clip)
        self.assertTrue(clip.keep)
        app.clip_checkbox_vars[id(clip)].set.assert_called_once_with(True)
        app._save_selection.assert_called_once()

    def test_no_deselects_exact_clip_and_saves(self):
        app, clip = self.make_app()
        clip.keep = True
        app._finish_preview_choice(False, clip)
        self.assertFalse(clip.keep)
        app.clip_checkbox_vars[id(clip)].set.assert_called_once_with(False)
        app._save_selection.assert_called_once()

    def test_closing_confirmation_leaves_selection_unchanged(self):
        app, clip = self.make_app()
        app._finish_preview_choice(None, clip)
        self.assertFalse(clip.keep)
        app._save_selection.assert_not_called()

    def test_a_different_episode_clip_is_not_touched(self):
        app, clip = self.make_app()
        other = Clip(5, 8, keep=False)
        app._finish_preview_choice(True, other)
        self.assertFalse(clip.keep)
        app._save_selection.assert_not_called()

    def test_preview_completion_opens_review_only_on_success(self):
        app, clip = self.make_app()
        app.preview_token = 3
        app.preview_process = Mock()
        app.preview_process.poll.return_value = 0
        app.preview_request = (3, clip, "S01E03 · Clip 004")
        app._ask_preview_choice = Mock()
        app._poll_preview()
        app._ask_preview_choice.assert_called_once_with(clip, "S01E03 · Clip 004")
        self.assertIsNone(app.preview_process)

    def test_preview_cancellation_does_not_prompt(self):
        app, clip = self.make_app()
        app.preview_token = 4
        app.preview_process = Mock()
        app.preview_process.poll.return_value = 0
        app.preview_request = (3, clip, "Clip 001")
        app._ask_preview_choice = Mock()
        app._poll_preview()
        app._ask_preview_choice.assert_not_called()

    def test_closing_preview_terminates_player(self):
        app, clip = self.make_app()
        app.preview_token = 2
        app.preview_request = (2, clip, "Clip 001")
        app.preview_process = Mock()
        app.preview_process.poll.return_value = None
        app._stop_preview()
        self.assertIsNone(app.preview_request)
        self.assertEqual(app.preview_token, 3)


if __name__ == "__main__":
    unittest.main()
