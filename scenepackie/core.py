"""Offline face-based discovery, scene matching, and video export."""
from __future__ import annotations

import json
import re
import tempfile
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import zipfile
from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np


Progress = Callable[[str, float], None]


@dataclass
class FaceGroup:
    image: bytes
    templates: list[np.ndarray] = field(default_factory=list)
    hits: int = 1


@dataclass
class Clip:
    start: float
    end: float
    keep: bool = True

    @property
    def duration(self) -> float:
        return self.end - self.start


class Cancelled(Exception):
    pass


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative


def binary(name: str) -> str:
    path = resource_path(f"bin/{name}.exe" if os.name == "nt" else f"bin/{name}")
    if path.is_file():
        return str(path)
    if sys.platform == "darwin" and name == "ffmpeg":
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError, OSError):
            pass
    return name


def creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def video_info(path: str) -> tuple[float, float]:
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise ValueError("This video couldn't be opened. Try an MP4, MOV, or MKV file.")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        capture.release()
    if not math.isfinite(fps) or fps <= 0 or not math.isfinite(frames) or frames <= 0:
        if sys.platform == "darwin":
            result = subprocess.run([binary("ffmpeg"), "-hide_banner", "-i", path], capture_output=True, text=True, timeout=40, creationflags=creation_flags())
            match = re.search(r"Duration:\\s*(\\d+):(\\d+):(\\d+(?:\\.\\d+)?)", result.stderr)
            if not match:
                raise ValueError("Couldn't determine this video's length.")
            hours, minutes, seconds = match.groups()
            duration = 3600 * int(hours) + 60 * int(minutes) + float(seconds)
        else:
            result = subprocess.run([binary("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "default=nokey=1:noprint_wrappers=1", path], capture_output=True, text=True, timeout=40, creationflags=creation_flags())
            if result.returncode != 0:
                raise ValueError("Couldn't determine this video's length.")
            duration = float(result.stdout.strip())
        fps = fps if fps > 0 else 25.0
    else:
        duration = frames / fps
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("This video has an invalid duration.")
    return duration, fps


def normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).flatten()
    magnitude = float(np.linalg.norm(vector))
    return vector / max(magnitude, 1e-8)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def group_matches(times: list[float], duration: float, padding: float = 1.25, max_gap: float = 3.0) -> list[Clip]:
    if not times:
        return []
    ordered = sorted(set(t for t in times if math.isfinite(t) and 0 <= t <= duration))
    if not ordered:
        return []
    groups: list[list[float]] = [[ordered[0]]]
    for time in ordered[1:]:
        if time - groups[-1][-1] <= max_gap:
            groups[-1].append(time)
        else:
            groups.append([time])
    raw = [Clip(max(0.0, group[0] - padding), min(duration, group[-1] + padding)) for group in groups]
    merged: list[Clip] = []
    for clip in raw:
        if merged and clip.start <= merged[-1].end:
            merged[-1].end = max(merged[-1].end, clip.end)
        elif clip.end > clip.start:
            merged.append(clip)
    return merged


class FaceScanner:
    def __init__(self):
        detection = resource_path("models/face_detection_yunet_2023mar.onnx")
        recognition = resource_path("models/face_recognition_sface_2021dec.onnx")
        if not detection.exists() or not recognition.exists():
            raise RuntimeError("The face recognition files are missing from this app. Please download a complete release.")
        if not hasattr(cv2, "FaceDetectorYN") or not hasattr(cv2, "FaceRecognizerSF"):
            raise RuntimeError("The bundled face recognition engine isn't available.")
        self.detector = cv2.FaceDetectorYN.create(str(detection), "", (320, 320), score_threshold=0.82, nms_threshold=0.3, top_k=500)
        self.recognizer = cv2.FaceRecognizerSF.create(str(recognition), "")

    def features(self, frame: np.ndarray) -> list[tuple[np.ndarray, bytes]]:
        h, w = frame.shape[:2]
        factor = min(1.0, 640.0 / max(h, w))
        if factor < 1:
            frame = cv2.resize(frame, (max(1, round(w * factor)), max(1, round(h * factor))), interpolation=cv2.INTER_AREA)
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        if faces is None:
            return []
        results = []
        for face in faces:
            if face[2] < 25 or face[3] < 25:
                continue
            try:
                cropped = self.recognizer.alignCrop(frame, face)
                feature = normalize(self.recognizer.feature(cropped))
                x, y, fw, fh = (int(v) for v in face[:4])
                extra = int(max(fw, fh) * 0.22)
                portrait = frame[max(0, y-extra):min(height, y+fh+extra), max(0, x-extra):min(width, x+fw+extra)]
                if portrait.size == 0:
                    continue
                portrait = cv2.resize(portrait, (150, 150), interpolation=cv2.INTER_AREA)
                success, encoded = cv2.imencode(".png", portrait)
                if success:
                    results.append((feature, encoded.tobytes()))
            except cv2.error:
                continue
        return results

    def _sample(self, source: str, interval: float, cancel: threading.Event, progress: Progress, label: str):
        duration, fps = video_info(source)
        capture = cv2.VideoCapture(source)
        try:
            samples = max(1, int(math.ceil(duration / interval)))
            for index in range(samples):
                if cancel.is_set():
                    raise Cancelled()
                time = min(duration - 0.001, 0.5 + index * interval)
                capture.set(cv2.CAP_PROP_POS_MSEC, time * 1000)
                ok, frame = capture.read()
                detections = self.features(frame) if ok else []
                # Report decoded *or* unreadable samples, so the display never
                # stops updating just because a section of the video is damaged.
                if index % 8 == 0 or index == samples - 1:
                    progress(label, (index + 1) / samples)
                if ok:
                    yield time, detections
        finally:
            capture.release()
        progress(label, 1.0)

    def discover(self, source: str, cancel: threading.Event, progress: Progress) -> list[FaceGroup]:
        groups: list[FaceGroup] = []
        for _, detections in self._sample(source, 3.0, cancel, progress, "Finding characters"):
            for feature, portrait in detections:
                closest = -1
                best = 0.48
                for index, group in enumerate(groups):
                    score = max(similarity(feature, template) for template in group.templates)
                    if score > best:
                        closest, best = index, score
                if closest < 0:
                    if len(groups) < 80:
                        groups.append(FaceGroup(image=portrait, templates=[feature]))
                else:
                    group = groups[closest]
                    group.hits += 1
                    if len(group.templates) < 8 and best < 0.94:
                        group.templates.append(feature)
        return sorted((group for group in groups if group.hits >= 2), key=lambda item: item.hits, reverse=True)

    def find_clips(self, source: str, group: FaceGroup, cancel: threading.Event, progress: Progress) -> list[Clip]:
        times: list[float] = []
        duration, _ = video_info(source)
        for timestamp, detections in self._sample(source, 0.8, cancel, progress, "Finding matching scenes"):
            if any(max(similarity(feature, prototype) for prototype in group.templates) >= 0.42 for feature, _ in detections):
                times.append(timestamp)
        return group_matches(times, duration)


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def concat_manifest(paths: list[Path]) -> str:
    """Generate a safe FFmpeg concat demuxer list."""
    if not paths:
        raise ValueError("No clips to combine.")
    return "".join("file '" + str(p.resolve()).replace("\\", "/").replace("'", "'\\''") + "'\n" for p in paths)


def run_ffmpeg(args: list[str], cancel: threading.Event) -> None:
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=creation_flags())
    try:
        while process.poll() is None:
            if cancel.wait(0.2):
                process.kill()
                process.wait()
                raise Cancelled()
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        if process.returncode != 0:
            raise RuntimeError("Video processing failed: " + stderr[-700:])
    finally:
        if process.stderr:
            process.stderr.close()


def export_clips(source: str, clips: list[Clip], destination: str, make_zip: bool, cancel: threading.Event, progress: Progress) -> Path:
    selected = [clip for clip in clips if clip.keep]
    if not selected:
        raise ValueError("Select at least one clip to export.")
    export_dir = Path(destination) / (Path(source).stem + "_scenepack")
    export_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    exported: list[Path] = []
    steps = len(selected) + 2 + int(make_zip)
    for i, clip in enumerate(selected, 1):
        if cancel.is_set():
            raise Cancelled()
        filename = f"clip_{i:03d}_{clock(clip.start).replace(':', '-')}.mp4"
        target = export_dir / filename
        if sys.platform == "darwin":
            from scenepackie.mac_media import mac_clip_args
            args = mac_clip_args(binary("ffmpeg"), source, clip.start, clip.duration, target)
        else:
            args = [binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{clip.start:.3f}", "-i", source, "-t", f"{clip.duration:.3f}", "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target)]
        run_ffmpeg(args, cancel)
        exported.append(target)
        records.append({"file": filename, "start": round(clip.start, 3), "end": round(clip.end, 3)})
        progress(f"Exporting clip {i} of {len(selected)}", i / steps)
    progress("Combining your scenepack", (len(selected) + 0.25) / steps)
    combined = export_dir / (Path(source).stem + "_full_scenepack.mp4")
    # The individual exports share encoding parameters; stream-copy concatenation
    # preserves their quality and avoids a second expensive video encode.
    with tempfile.TemporaryDirectory() as temp:
        manifest = Path(temp) / "clips.txt"
        manifest.write_text(concat_manifest(exported), encoding="utf-8")
        try:
            if sys.platform == "darwin":
                from scenepackie.mac_media import mac_combined_args
                run_ffmpeg(mac_combined_args(binary("ffmpeg"), manifest, combined), cancel)
            else:
                run_ffmpeg([binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                        "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy",
                        "-movflags", "+faststart", str(combined)], cancel)
        except RuntimeError:
            # Fall back to decoding and re-encoding in case the input streams
            # can't be joined by stream copy.
            run_ffmpeg([binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                        "-f", "concat", "-safe", "0", "-i", str(manifest),
                        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", str(combined)], cancel)
    progress("Scenepack combined", (len(selected) + 1) / steps)
    (export_dir / "clips.json").write_text(json.dumps({"source": Path(source).name, "clips": records}, indent=2), encoding="utf-8")
    if make_zip:
        archive = export_dir.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as output:
            for file in export_dir.iterdir():
                if cancel.is_set():
                    raise Cancelled()
                if file.is_file():
                    output.write(file, arcname=f"{export_dir.name}/{file.name}")
        progress("Finished", 1.0)
        return archive
    progress("Finished", 1.0)
    return export_dir
