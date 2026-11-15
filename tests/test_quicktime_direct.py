"""Check the fast Mac QuickTime preview path without the old helper."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scenepackie.core import Clip, binary
from scenepackie.preview import create_mac_preview, preview_args


class DirectQuickTimeTests(unittest.TestCase):
    def test_seek_first_for_fast_previews(self):
        command = preview_args("ffmpeg", "movie.mp4", Clip(320.2, 324.4), Path("clip.mp4"))
        self.assertLess(command.index("-ss"), command.index("-i"))
        self.assertIn("ultrafast", command)
        for setting in ("libx264", "aac", "avc1", "yuv420p", "+faststart"):
            self.assertIn(setting, command)

    @unittest.skipUnless(sys.platform == "darwin", "Mac playback export integration test")
    def test_preview_is_decodable_on_mac(self):
        ffmpeg = binary("ffmpeg")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "source.mp4"
            subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=7",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=7",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                str(source),
            ], check=True, capture_output=True, timeout=35)
            target = create_mac_preview(str(source), Clip(4.2, 5.1), ffmpeg=ffmpeg,
                                        directory=folder / "preview")
            self.assertGreater(target.stat().st_size, 2048)
            decoded = subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(target),
                "-f", "null", "-",
            ], capture_output=True, timeout=30)
            self.assertEqual(decoded.returncode, 0,
                             decoded.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
