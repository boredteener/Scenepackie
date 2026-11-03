"""Saved animation references and matching clips, kept separate from live-action scans."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile

from scenepackie.cache import cache_directory, identity
from scenepackie.core import Clip
from scenepackie.animation import decode_reference

VERSION = 1


def cache_path(source: str) -> Path:
    identifier = hashlib.sha256(identity(source)["path"].encode("utf-8")).hexdigest()
    return cache_directory() / (identifier + "-animation.json")


def read_animation(source: str) -> tuple[list[bytes], list[Clip] | None] | None:
    try:
        file = cache_path(source)
        if not file.is_file() or file.is_symlink() or file.stat().st_size > 20_000_000:
            return None
        data = json.loads(file.read_text(encoding="utf-8"))
        if data.get("version") != VERSION or data.get("source") != identity(source):
            return None
        refs = [base64.b64decode(s, validate=True) for s in data["references"]]
        if not (1 <= len(refs) <= 3):
            return None
        for image in refs:
            decode_reference(image)
        rows = data.get("clips")
        if rows is None:
            clips = None
        else:
            if not isinstance(rows, list) or len(rows) > 25000:
                return None
            clips = [Clip(float(v["start"]), float(v["end"]), bool(v["keep"])) for v in rows]
            if any(not (0 <= clip.start < clip.end < 10000000) for clip in clips):
                return None
        return refs, clips
    except (OSError, KeyError, ValueError, TypeError, OverflowError, json.JSONDecodeError):
        return None


def save_animation(source: str, refs: list[bytes], clips: list[Clip] | None = None) -> None:
    if not (1 <= len(refs) <= 3):
        return
    data = {
        "version": VERSION,
        "source": identity(source),
        "references": [base64.b64encode(ref).decode("ascii") for ref in refs],
        "clips": None if clips is None else [
            {"start": clip.start, "end": clip.end, "keep": clip.keep} for clip in clips
        ],
    }
    target = cache_path(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", dir=target.parent, prefix=".anim-", suffix=".tmp",
                encoding="utf-8", delete=False) as stream:
            pending = Path(stream.name)
            json.dump(data, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, target)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)
