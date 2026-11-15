"""TV show season discovery, resumable character scans and scan storage."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from dataclasses import dataclass

import numpy as np

from scenepackie.core import FaceScanner, FaceGroup, Clip, Cancelled, normalize, similarity
from scenepackie.cache import cache_directory, identity, read_snapshot, save_characters
from scenepackie.animation import AnimationMatcher

EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}
FORMAT = 1


@dataclass(frozen=True)
class Episode:
    season: int
    number: int
    path: str

    @property
    def label(self) -> str:
        return f"S{self.season:02d}E{self.number:02d}"


def _sort_filename(p: Path):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", p.stem)]


def find_episodes(root: str, season_count: int) -> list[Episode]:
    """The user selects a show folder containing Season 1, Season 2 etc."""
    folder = Path(root).expanduser().resolve(strict=True)
    if not folder.is_dir() or not 1 <= season_count <= 30:
        raise ValueError("Choose a show folder and a valid number of seasons.")
    episodes: list[Episode] = []
    for season in range(1, season_count + 1):
        season_folder = folder / f"Season {season}"
        if not season_folder.is_dir():
            raise ValueError(f"Missing 'Season {season}' folder. Put it inside your TV show folder.")
        videos = sorted((p for p in season_folder.iterdir()
                         if p.is_file() and p.suffix.lower() in EXTENSIONS and not p.name.startswith(".")),
                        key=_sort_filename)
        if not videos:
            raise ValueError(f"Season {season} doesn't contain any supported episode videos.")
        for number, file in enumerate(videos, 1):
            episodes.append(Episode(season, number, str(file.resolve())))
    return episodes


def _signature(root: str, episodes: list[Episode], kind: str) -> dict:
    return {
        "folder": str(Path(root).resolve()),
        "kind": kind,
        "episodes": [{"season": e.season, "number": e.number, **identity(e.path)} for e in episodes],
    }


def _cache_path(root: str) -> Path:
    name = hashlib.sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()
    return cache_directory() / f"{name}-tv-show.json"


def blank_state() -> dict:
    return {"faces": [], "references": [], "selected": None, "clips": {}}


def read_state(root: str, episodes: list[Episode], kind: str) -> dict:
    target = _cache_path(root)
    try:
        if not target.is_file() or target.is_symlink() or target.stat().st_size > 35_000_000:
            return blank_state()
        data = json.loads(target.read_text(encoding="utf-8"))
        if data.get("format") != FORMAT or data.get("signature") != _signature(root, episodes, kind):
            return blank_state()
        state = data["state"]
        if not isinstance(state.get("clips"), dict) or len(state["clips"]) > len(episodes):
            return blank_state()
        known = {e.label for e in episodes}
        for key, rows in state["clips"].items():
            if key not in known or not isinstance(rows, list) or len(rows) > 10000:
                return blank_state()
            for row in rows:
                if not (0 <= float(row["start"]) < float(row["end"]) < 10000000):
                    return blank_state()
        if len(state.get("faces", [])) > 80 or len(state.get("references", [])) > 3:
            return blank_state()
        return state
    except (KeyError, OSError, ValueError, TypeError, OverflowError, json.JSONDecodeError):
        return blank_state()


def save_state(root: str, episodes: list[Episode], kind: str, state: dict) -> None:
    """Atomic, per-episode saves: a stopped scan never loses finished episodes."""
    target = _cache_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = {"format": FORMAT, "signature": _signature(root, episodes, kind), "state": state}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent,
                                         prefix=".tv-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(content, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def pack_faces(groups: list[FaceGroup]) -> list[dict]:
    return [{"image": base64.b64encode(g.image).decode("ascii"),
             "vectors": [np.asarray(v, dtype=np.float32).tolist() for v in g.templates],
             "hits": g.hits} for g in groups]


def unpack_faces(rows: list[dict]) -> list[FaceGroup]:
    groups = []
    for row in rows:
        vectors = [np.asarray(v, dtype=np.float32) for v in row["vectors"]]
        if not vectors or len(vectors) > 8 or any(x.shape != (128,) or not np.isfinite(x).all() for x in vectors):
            raise ValueError("Invalid saved character reference")
        groups.append(FaceGroup(base64.b64decode(row["image"], validate=True), vectors, int(row["hits"])))
    return groups


def pack_clips(clips: list[Clip]) -> list[dict]:
    return [{"start": c.start, "end": c.end, "keep": c.keep} for c in clips]


def unpack_clips(rows: list[dict]) -> list[Clip]:
    return [Clip(float(r["start"]), float(r["end"]), bool(r.get("keep", True))) for r in rows]


def combine_faces(groups: list[FaceGroup], additions: list[FaceGroup]) -> list[FaceGroup]:
    for candidate in additions:
        best_index, best_score = -1, 0.55
        for index, group in enumerate(groups):
            score = max(similarity(normalize(a), normalize(b)) for a in candidate.templates for b in group.templates)
            if score > best_score:
                best_index, best_score = index, score
        if best_index >= 0:
            found = groups[best_index]
            found.hits += candidate.hits
            for vector in candidate.templates:
                if len(found.templates) < 8 and max(similarity(normalize(vector), normalize(x)) for x in found.templates) < 0.93:
                    found.templates.append(vector)
        elif len(groups) < 80:
            groups.append(FaceGroup(candidate.image, list(candidate.templates), candidate.hits))
    return groups


def discover_cast(episodes: list[Episode], cancel: threading.Event, progress) -> list[FaceGroup]:
    result: list[FaceGroup] = []
    for index, ep in enumerate(episodes):
        if cancel.is_set():
            raise Cancelled()
        cached = read_snapshot(ep.path)
        if cached is None:
            scanner = FaceScanner()
            faces = scanner.discover(ep.path, cancel,
                 lambda label, fraction, i=index, e=ep: progress(
                    f"{e.label} · finding characters", (i + fraction) / len(episodes)))
            save_characters(ep.path, faces)
        else:
            faces = cached[0]
        combine_faces(result, faces)
        progress(f"{ep.label} · characters checked", (index + 1) / len(episodes))
    return sorted(result, key=lambda item: item.hits, reverse=True)


def scan_episodes(root: str, episodes: list[Episode], kind: str, state: dict,
                  cancel: threading.Event, progress, group: FaceGroup | None = None,
                  references: list[bytes] | None = None) -> dict:
    """Only unfinished episodes are rescanned; save each completed episode immediately."""
    if kind == "live" and group is None:
        raise ValueError("Choose a character first.")
    if kind == "animated" and not references:
        raise ValueError("Add an animated character reference first.")
    matcher = AnimationMatcher(references) if kind == "animated" else None
    clips = dict(state.get("clips") or {})
    for index, ep in enumerate(episodes):
        if cancel.is_set():
            raise Cancelled()
        if ep.label not in clips:
            label = f"{ep.label} · finding matching scenes"
            report = lambda _, fraction, i=index, e=ep: progress(
                f"{e.label} · finding matching scenes", (i + fraction) / len(episodes))
            if kind == "animated":
                matches = matcher.find_clips(ep.path, cancel, report)
            else:
                matches = FaceScanner().find_clips(ep.path, group, cancel, report)
            clips[ep.label] = pack_clips(matches)
            state["clips"] = clips
            save_state(root, episodes, kind, state)
        progress(f"{ep.label} · scenes checked", (index + 1) / len(episodes))
    return state


def selected_entries(episodes: list[Episode], state: dict) -> list[tuple[Episode, Clip]]:
    result = []
    for episode in episodes:
        for clip in unpack_clips(state.get("clips", {}).get(episode.label, [])):
            result.append((episode, clip))
    return result
