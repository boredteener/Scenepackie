import subprocess
import tempfile
import threading
from pathlib import Path
import unittest
import sys

from scenepackie.core import Clip, binary, export_clips
from scenepackie.mac_media import mac_clip_args, mac_combined_args


class MacExportTests(unittest.TestCase):
    def test_container_options(self):
        a = mac_clip_args("ffmpeg", "source.mov", 3.5, 4.0, Path("out.mp4"))
        for value in ("libx264", "avc1", "yuv420p", "aac", "+faststart", "mp4"):
            self.assertIn(value, a)
        b = mac_combined_args("ffmpeg", Path("clips.txt"), Path("joined.mp4"))
        self.assertNotIn("copy", b)

    @unittest.skipUnless(sys.platform == "darwin", "macOS playback smoke test")
    def test_encoded_clips_decode_with_avfoundation(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            source = folder / "source.mp4"
            ffmpeg = binary("ffmpeg")
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=5",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
                check=True, capture_output=True)
            export_clips(str(source), [Clip(0.5, 1.6), Clip(2.3, 3.7)],
                str(folder), False, threading.Event(), lambda *_: None)
            produced = sorted((folder / "source_scenepack").glob("*.mp4"))
            self.assertEqual(len(produced), 3)
            for movie in produced:
                check = subprocess.run(["/usr/bin/afinfo", str(movie)],
                    capture_output=True)
                # afinfo is audio-specific; video is decoded with Apple's AVFoundation tool.
                swift = subprocess.run(["/usr/bin/swift", "-e",
                    "import AVFoundation; import Foundation; let a = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1])); let sem = DispatchSemaphore(value: 0); a.loadValuesAsynchronously(forKeys: [\"tracks\"]) { sem.signal() }; sem.wait(); var error: NSError?; guard a.statusOfValue(forKey: \"tracks\", error: &error) == .loaded, !a.tracks(withMediaType: .video).isEmpty else { exit(1) }", str(movie)],
                    capture_output=True, timeout=90)
                self.assertEqual(swift.returncode, 0, swift.stderr.decode(errors="replace"))
