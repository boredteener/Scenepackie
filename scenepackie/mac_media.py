"""Mac-only MP4 encoding arguments for QuickTime-compatible exports."""
from __future__ import annotations

from pathlib import Path


def mac_video_options() -> list[str]:
    """H.264/AVC 8-bit with AAC audio, standard MP4 tags and finalized metadata."""
    return [
        "-map", "0:v:0", "-map", "0:a:0?",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-profile:v", "high", "-tag:v", "avc1",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-avoid_negative_ts", "make_zero", "-movflags", "+faststart",
        "-f", "mp4",
    ]


def mac_clip_args(executable: str, source: str, start: float, duration: float, destination: Path) -> list[str]:
    return [
        executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-ss", f"{start:.3f}", "-i", source, "-t", f"{duration:.3f}",
        *mac_video_options(), str(destination),
    ]


def mac_combined_args(executable: str, manifest: Path, destination: Path) -> list[str]:
    """Re-encode the join to rebuild timestamps instead of copying fragile MP4 timelines."""
    return [
        executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-fflags", "+genpts", "-f", "concat", "-safe", "0",
        "-i", str(manifest), *mac_video_options(), str(destination),
    ]
