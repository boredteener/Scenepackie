"""Create QuickTime-compatible previews without touching the original video."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from scenepackie.core import Clip, binary, creation_flags


def preview_args(ffmpeg: str, source: str, clip: Clip, output: Path) -> list[str]:
    """Use universally supported H.264/AAC in a properly finalized MP4 container."""
    if clip.duration <= 0:
        raise ValueError("The selected clip has no playable duration.")
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", source, "-ss", f"{clip.start:.3f}", "-t", f"{clip.duration:.3f}",
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-profile:v", "baseline", "-level:v", "3.1", "-tag:v", "avc1",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        "-f", "mp4", str(output),
    ]


def create_mac_preview(source: str, clip: Clip, ffmpeg: str | None = None,
                       directory: Path | None = None) -> Path:
    """Return a unique, validated MP4 filename to avoid QuickTime reopening stale data."""
    folder = directory or (Path(tempfile.gettempdir()) / "scenepackie-previews")
    folder.mkdir(parents=True, exist_ok=True)
    # Clean up only old previews made by Scenepackie (not a user's exports).
    now = time.time()
    for old in folder.glob("scenepackie-*.mp4"):
        try:
            if old.is_file() and now - old.stat().st_mtime > 24 * 3600:
                old.unlink()
        except OSError:
            pass

    result = folder / f"scenepackie-{uuid.uuid4().hex}.mp4"
    executable = ffmpeg or binary("ffmpeg")
    try:
        command = preview_args(executable, source, clip, result)
        completed = subprocess.run(command, capture_output=True, check=False,
                                   creationflags=creation_flags(), timeout=180)
        if completed.returncode != 0:
            reason = completed.stderr.decode("utf-8", errors="replace")[-1200:].strip()
            raise RuntimeError("Couldn't prepare this clip for playback. " + reason)
        if not result.is_file() or result.stat().st_size < 2048:
            raise RuntimeError("The preview file was empty or incomplete.")
        # Validate actual MP4 container and decode a frame before QuickTime sees it.
        with result.open("rb") as f:
            header = f.read(32)
        if b"ftyp" not in header:
            raise RuntimeError("The preview is not a valid MP4 file.")
        checked = subprocess.run(
            [executable, "-hide_banner", "-loglevel", "error", "-nostdin",
             "-i", str(result), "-frames:v", "1", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30,
            creationflags=creation_flags())
        if checked.returncode != 0:
            raise RuntimeError("Couldn't decode the preview video.")
        return result
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        result.unlink(missing_ok=True)
        raise
