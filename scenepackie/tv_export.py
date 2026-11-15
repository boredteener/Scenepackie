"""Export TV character clips per season and as one continuous scenepack."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import zipfile

from scenepackie.core import (Cancelled, binary, clock, concat_manifest,
                             run_ffmpeg)
from scenepackie.tv import Episode, selected_entries

def _encode(source: str, start: float, duration: float, output: Path,
            cancel: threading.Event) -> None:
    if sys.platform == "darwin":
        from scenepackie.mac_media import mac_clip_args
        args = mac_clip_args(binary("ffmpeg"), source, start, duration, output)
    else:
        args = [binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-ss", f"{start:.3f}", "-i", source, "-t", f"{duration:.3f}",
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
                "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)]
    run_ffmpeg(args, cancel)


def _join(paths: list[Path], output: Path, cancel: threading.Event) -> None:
    if not paths:
        raise ValueError("No clips to combine.")
    with tempfile.TemporaryDirectory() as temp:
        manifest = Path(temp) / "input.txt"
        manifest.write_text(concat_manifest(paths), encoding="utf-8")
        if sys.platform == "darwin":
            from scenepackie.mac_media import mac_combined_args
            run_ffmpeg(mac_combined_args(binary("ffmpeg"), manifest, output), cancel)
            return
        try:
            run_ffmpeg([binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
                        "-nostdin", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(output)], cancel)
        except RuntimeError:
            run_ffmpeg([binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
                        "-nostdin", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(manifest), "-c:v", "libx264", "-crf", "18",
                        "-preset", "fast", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", str(output)], cancel)


def export_tv(root: str, episodes: list[Episode], state: dict, destination: str,
              make_zip: bool, cancel: threading.Event, progress) -> Path:
    """Preserves chronological episode order and all checked clip selections."""
    selected = [(episode, clip) for episode, clip in selected_entries(episodes, state) if clip.keep]
    if not selected:
        raise ValueError("Select at least one clip to export.")
    output_dir = Path(destination) / (Path(root).name + "_scenepack")
    output_dir.mkdir(parents=True, exist_ok=True)
    seasons = sorted({episode.season for episode, _ in selected})
    steps = len(selected) + len(seasons) + 1 + int(make_zip)
    done = 0
    all_paths: list[Path] = []
    season_paths: dict[int, list[Path]] = {number: [] for number in seasons}
    records = []
    episode_counts = {}
    for index, (episode, clip) in enumerate(selected, 1):
        if cancel.is_set():
            raise Cancelled()
        folder = output_dir / f"Season {episode.season}"
        folder.mkdir(parents=True, exist_ok=True)
        episode_counts[episode.label] = episode_counts.get(episode.label, 0) + 1
        episode_index = episode_counts[episode.label]
        name = (f"clip_{episode.label}_{episode_index:03d}_"
                f"{clock(clip.start).replace(':', '-')}.mp4")
        target = folder / name
        _encode(episode.path, clip.start, clip.duration, target, cancel)
        all_paths.append(target)
        season_paths[episode.season].append(target)
        records.append({"season": episode.season, "episode": episode.label,
                        "source": Path(episode.path).name, "clip": name,
                        "start": round(clip.start, 3), "end": round(clip.end, 3)})
        done += 1
        progress(f"Exporting TV clip {index} of {len(selected)}", done / steps)

    for season in seasons:
        if cancel.is_set():
            raise Cancelled()
        target = output_dir / f"Season {season}" / f"Season_{season}_scenepack.mp4"
        progress(f"Combining Season {season}", (done + .15) / steps)
        _join(season_paths[season], target, cancel)
        done += 1
        progress(f"Season {season} combined", done / steps)

    if cancel.is_set():
        raise Cancelled()
    progress("Combining all seasons", (done + .15) / steps)
    _join(all_paths, output_dir / "Full_Character_Scenepack.mp4", cancel)
    done += 1
    progress("Full scenepack combined", done / steps)
    (output_dir / "clips.json").write_text(
        json.dumps({"show": Path(root).name, "clips": records}, indent=2),
        encoding="utf-8")
    if make_zip:
        archive = output_dir.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zip_file:
            for file in output_dir.rglob("*"):
                if cancel.is_set():
                    raise Cancelled()
                if file.is_file():
                    zip_file.write(file, arcname=f"{output_dir.name}/{file.relative_to(output_dir).as_posix()}")
        progress("Finished", 1.0)
        return archive
    progress("Finished", 1.0)
    return output_dir
