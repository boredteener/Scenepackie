"""Local, versioned scan snapshots. Never stores or modifies movie data."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

from scenepackie.core import Clip, FaceGroup

FORMAT = 1
SCAN_REVISION = 1


def cache_directory() -> Path:
    override = os.environ.get("SCENEPACKIE_CACHE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Scenepackie" / "cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Scenepackie" / "cache"
    return Path(os.getenv("XDG_CACHE_HOME") or Path.home() / ".cache") / "scenepackie"


def identity(source: str) -> dict:
    path = Path(source).resolve(strict=True)
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "modified_ns": stat.st_mtime_ns}


def snapshot_path(source: str) -> Path:
    key = hashlib.sha256(identity(source)["path"].encode("utf-8")).hexdigest()
    return cache_directory() / (key + ".json")


def read_snapshot(source: str) -> tuple[list[FaceGroup], dict[str, list[Clip]]] | None:
    """An incompatible, missing, corrupt or stale snapshot is treated as a cache miss."""
    try:
        target = snapshot_path(source)
        if not target.is_file() or target.stat().st_size > 35_000_000:
            return None
        data = json.loads(target.read_text(encoding="utf-8"))
        if data["format"] != FORMAT or data["scan_revision"] != SCAN_REVISION or data["source"] != identity(source):
            return None
        rows = data["faces"]
        if not isinstance(rows, list) or len(rows) > 80:
            return None
        groups = []
        for row in rows:
            image = base64.b64decode(row["image"], validate=True)
            if not 0 < len(image) < 1_000_000:
                return None
            vectors = [np.asarray(values, dtype=np.float32) for values in row["templates"]]
            if not (1 <= len(vectors) <= 8) or any(v.ndim != 1 or v.size != 128 or not np.isfinite(v).all() for v in vectors):
                return None
            groups.append(FaceGroup(image=image, templates=vectors, hits=int(row["hits"])))
        matches = {}
        for key, rows in data.get("clips", {}).items():
            if not key.isdecimal() or int(key) >= len(groups) or len(rows) > 100_000:
                return None
            clips = [Clip(float(c["start"]), float(c["end"]), bool(c["keep"])) for c in rows]
            if any(not (0 <= c.start < c.end < 10_000_000) for c in clips):
                return None
            matches[key] = clips
        return groups, matches
    except (OSError, KeyError, TypeError, ValueError, OverflowError, json.JSONDecodeError):
        return None


def _atomic_write(source: str, groups: list[FaceGroup], matches: dict[str, list[Clip]]) -> None:
    target = snapshot_path(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    contents = {
        "format": FORMAT,
        "scan_revision": SCAN_REVISION,
        "source": identity(source),
        "faces": [
            {
                "image": base64.b64encode(g.image).decode("ascii"),
                "templates": [np.asarray(v, dtype=np.float32).tolist() for v in g.templates],
                "hits": g.hits,
            } for g in groups
        ],
        "clips": {
            key: [{"start": c.start, "end": c.end, "keep": c.keep} for c in clips]
            for key, clips in matches.items()
        },
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=".scan-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(contents, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_characters(source: str, groups: list[FaceGroup]) -> None:
    """A completed discovery replaces old results; never called for cancelled scans."""
    _atomic_write(source, groups, {})


def save_clips(source: str, group_index: int, clips: list[Clip]) -> None:
    """Save only when a completed character scan already exists on disk."""
    snapshot = read_snapshot(source)
    if snapshot is None:
        return
    groups, matches = snapshot
    if not 0 <= group_index < len(groups):
        return
    matches[str(group_index)] = clips
    _atomic_write(source, groups, matches)


def clear_saved_scans() -> tuple[int, int]:
    """Remove only files created for scan snapshots, never videos or exports."""
    folder = cache_directory()
    if not folder.is_dir():
        return 0, 0
    count = size = 0
    for path in folder.glob("*.json"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            file_size = path.stat().st_size
            path.unlink()
            count += 1
            size += file_size
        except FileNotFoundError:
            continue
    return count, size
