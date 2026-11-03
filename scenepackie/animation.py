"""Character appearance matching for 2D and 3D animation.

Animation does not use the live-action face recognizer. The editor supplies
tight character crops; matches require visual evidence from those crops.
"""
from __future__ import annotations

import math
import threading

import cv2
import numpy as np

from scenepackie.core import Cancelled, Clip, group_matches, video_info

SCALES = (0.64, 0.80, 1.0, 1.24, 1.52)
SAMPLE_SECONDS = 0.8
MAX_WIDTH = 640


def encode_reference(crop: np.ndarray) -> bytes:
    if crop is None or crop.size == 0 or min(crop.shape[:2]) < 28:
        raise ValueError("Select a larger, clear area around the character.")
    ok, data = cv2.imencode(".png", crop)
    if not ok:
        raise ValueError("Couldn't save that selection. Try another frame.")
    return data.tobytes()


def decode_reference(data: bytes) -> np.ndarray:
    if not data or len(data) > 5_000_000:
        raise ValueError("Invalid animated character reference.")
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or min(image.shape[:2]) < 28:
        raise ValueError("Invalid animated character reference.")
    return image


def _small(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= MAX_WIDTH:
        return frame
    ratio = MAX_WIDTH / w
    return cv2.resize(frame, (MAX_WIDTH, max(1, round(h * ratio))), interpolation=cv2.INTER_AREA)


def _hist(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    result = cv2.calcHist([hsv], [0, 1], None, [20, 12], [0, 180, 0, 256])
    cv2.normalize(result, result, norm_type=cv2.NORM_L1)
    return result


class AnimationMatcher:
    def __init__(self, references: list[bytes]):
        if not 1 <= len(references) <= 3:
            raise ValueError("Choose one to three clear views of the character.")
        self.refs = []
        self.sift = cv2.SIFT_create(nfeatures=350) if hasattr(cv2, "SIFT_create") else None
        for data in references:
            image = _small(decode_reference(data))
            gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (3, 3), 0)
            h, w = gray.shape
            if h > 320 or w > 320:
                factor = min(320 / h, 320 / w)
                image = cv2.resize(image, (max(28, round(w * factor)), max(28, round(h * factor))))
                gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (3, 3), 0)
            keys, features = [], None
            if self.sift is not None:
                keys, features = self.sift.detectAndCompute(gray, None)
            self.refs.append((gray, _hist(image), keys, features))

    @staticmethod
    def _evidence(gray: np.ndarray, histogram: np.ndarray, frame: np.ndarray, base_gray: np.ndarray) -> bool:
        for factor in SCALES:
            height = round(gray.shape[0] * factor)
            width = round(gray.shape[1] * factor)
            if min(width, height) < 24 or height > frame.shape[0] or width > frame.shape[1]:
                continue
            template = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_LINEAR)
            if cv2.meanStdDev(template)[1][0, 0] < 11:
                continue
            response = cv2.matchTemplate(base_gray, template, cv2.TM_CCOEFF_NORMED)
            _, peak, _, top_left = cv2.minMaxLoc(response)
            if peak < 0.83:
                continue
            x, y = top_left
            candidate = frame[y:y + height, x:x + width]
            if candidate.size == 0:
                continue
            color_agreement = cv2.compareHist(histogram, _hist(candidate), cv2.HISTCMP_CORREL)
            if color_agreement >= 0.62:
                return True
        return False

    def matches_frame(self, frame: np.ndarray) -> bool:
        frame = _small(frame)
        base_gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (3, 3), 0)
        for gray, colors, _, descriptors in self.refs:
            if self._evidence(gray, colors, frame, base_gray):
                return True

        # Distinctive marks on 3D models and detailed animation survive moderate
        # pose/camera changes even when the full template no longer aligns.
        if self.sift is None:
            return False
        frame_keys, frame_features = self.sift.detectAndCompute(base_gray, None)
        if frame_features is None or len(frame_features) < 12:
            return False
        matcher = cv2.BFMatcher(cv2.NORM_L2)
        for _, _, ref_keys, ref_features in self.refs:
            if ref_features is None or len(ref_features) < 12:
                continue
            pairs = matcher.knnMatch(ref_features, frame_features, k=2)
            good = [a for pair in pairs if len(pair) == 2
                    for a, b in [pair] if a.distance < 0.67 * b.distance]
            if len(good) < 12:
                continue
            ref_points = np.float32([ref_keys[m.queryIdx].pt for m in good])
            frame_points = np.float32([frame_keys[m.trainIdx].pt for m in good])
            matrix, inliers = cv2.estimateAffinePartial2D(
                ref_points, frame_points, method=cv2.RANSAC,
                ransacReprojThreshold=4.0, maxIters=1200)
            if matrix is None or inliers is None:
                continue
            count = int(inliers.sum())
            scale = math.hypot(float(matrix[0, 0]), float(matrix[0, 1]))
            if count >= 12 and count / len(good) >= 0.65 and 0.35 <= scale <= 2.5:
                return True
        return False

    def find_clips(self, source: str, cancel: threading.Event, progress) -> list[Clip]:
        duration, _ = video_info(source)
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            raise ValueError("This video couldn't be opened.")
        timestamps = []
        samples = max(1, int(math.ceil(duration / SAMPLE_SECONDS)))
        try:
            for index in range(samples):
                if cancel.is_set():
                    raise Cancelled()
                t = min(max(0.0, duration - 0.01), 0.4 + index * SAMPLE_SECONDS)
                capture.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                success, frame = capture.read()
                if success and self.matches_frame(frame):
                    timestamps.append(t)
                if index % 5 == 0 or index == samples - 1:
                    progress("Finding animated scenes", (index + 1) / samples)
        finally:
            capture.release()
        if len(timestamps) / samples > 0.72:
            raise ValueError("This selection matched most of the movie. Try a tighter crop around the character, without the background.")
        return group_matches(timestamps, duration, padding=0.55, max_gap=1.3)
