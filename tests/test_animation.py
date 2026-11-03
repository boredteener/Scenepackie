import os
import tempfile
import threading
import unittest
from pathlib import Path

import cv2
import numpy as np

from scenepackie.animation import AnimationMatcher, encode_reference, decode_reference
from scenepackie.animation_cache import read_animation, save_animation
from scenepackie.cache import clear_saved_scans
from scenepackie.core import Clip


def cartoon(present=True, shift=0):
    image = np.zeros((360, 640, 3), dtype=np.uint8)
    image[:] = (165, 188, 208)
    cv2.rectangle(image, (0, 295), (640, 360), (105, 145, 75), -1)
    cv2.rectangle(image, (350, 40), (540, 130), (75, 115, 130), -1)
    if present:
        x = 112 + shift
        cv2.rectangle(image, (x, 169), (x + 90, 278), (70, 85, 220), -1)
        cv2.circle(image, (x + 45, 127), 51, (85, 205, 240), -1)
        cv2.circle(image, (x + 29, 115), 11, (245, 245, 245), -1)
        cv2.circle(image, (x + 64, 115), 11, (245, 245, 245), -1)
        cv2.circle(image, (x + 29, 115), 4, (20, 20, 20), -1)
        cv2.circle(image, (x + 64, 115), 4, (20, 20, 20), -1)
        cv2.ellipse(image, (x + 47, 148), (21, 8), 0, 0, 180, (25, 25, 30), 3)
    return image


class AnimationDetectionTests(unittest.TestCase):
    def test_character_moves_without_matching_empty_frames(self):
        sample = cartoon()[72:280, 108:206]
        match = AnimationMatcher([encode_reference(sample)])
        self.assertTrue(match.matches_frame(cartoon(True)))
        self.assertTrue(match.matches_frame(cartoon(True, shift=90)))
        self.assertFalse(match.matches_frame(cartoon(False)))

    def test_reference_image_valid(self):
        data = encode_reference(cartoon()[80:290, 108:210])
        self.assertEqual(decode_reference(data).shape[2], 3)
        with self.assertRaises(ValueError):
            encode_reference(np.zeros((10, 10, 3), dtype=np.uint8))

    def test_export_candidates_are_not_the_whole_cartoon(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "drawn_movie.avi"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 8, (640, 360))
            self.assertTrue(writer.isOpened())
            try:
                for index in range(64):
                    active = (8 <= index < 24) or (46 <= index < 56)
                    writer.write(cartoon(active, shift=40 if index >= 46 else 0))
            finally:
                writer.release()
            reference = encode_reference(cartoon()[72:280, 108:206])
            clips = AnimationMatcher([reference]).find_clips(
                str(source), threading.Event(), lambda *_: None)
            self.assertGreaterEqual(len(clips), 2)
            self.assertLess(sum(c.duration for c in clips), 5.5)

    def test_animation_cache_is_separate_and_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = os.environ.get("SCENEPACKIE_CACHE_DIR")
            os.environ["SCENEPACKIE_CACHE_DIR"] = str(Path(tmp) / "scans")
            try:
                movie = Path(tmp) / "movie.mkv"
                movie.write_bytes(b"example")
                reference = encode_reference(cartoon()[80:290, 108:210])
                save_animation(str(movie), [reference], [Clip(4, 8, keep=False)])
                refs, clips = read_animation(str(movie))
                self.assertEqual(len(refs), 1)
                self.assertEqual([(c.start, c.end, c.keep) for c in clips], [(4, 8, False)])
                movie.write_bytes(b"modified movie")
                self.assertIsNone(read_animation(str(movie)))
                cleared, _ = clear_saved_scans()
                self.assertEqual(cleared, 1)
                self.assertTrue(movie.exists())
            finally:
                if original is None:
                    os.environ.pop("SCENEPACKIE_CACHE_DIR", None)
                else:
                    os.environ["SCENEPACKIE_CACHE_DIR"] = original


if __name__ == "__main__":
    unittest.main()
