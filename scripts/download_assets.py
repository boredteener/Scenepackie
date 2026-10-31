"""Bundle offline OpenCV models and Windows FFmpeg during the GitHub Actions build."""
from pathlib import Path
from urllib.request import Request, urlopen
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
TOOLS = ROOT / "bin"


def download(url: str, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "Scenepackie-build/1.0"})
    with urlopen(request, timeout=120) as remote, destination.open("wb") as target:
        shutil.copyfileobj(remote, target)
    print(f"Downloaded {destination.name}: {destination.stat().st_size:,} bytes", flush=True)


def main():
    models = {
        "face_detection_yunet_2023mar.onnx": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    }
    for name, url in models.items():
        target = MODELS / name
        if not target.is_file():
            download(url, target)
        minimum = 10_000_000 if "recognition" in name else 100_000
        if target.stat().st_size < minimum or target.read_bytes()[:20].startswith(b"version https://git"):
            raise RuntimeError(f"Model download incomplete: {name}")

    TOOLS.mkdir(parents=True, exist_ok=True)
    # ffplay supplies video + audio previews without a VLC/Python installation.
    binaries = ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe")
    if any(not (TOOLS / name).is_file() for name in binaries):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "ffmpeg.zip"
            download("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", archive)
            with zipfile.ZipFile(archive) as source:
                for name in binaries:
                    entry = next((x for x in source.namelist() if x.lower().endswith("/bin/" + name)), None)
                    if entry is None:
                        raise RuntimeError(f"Could not find {name} in FFmpeg build")
                    with source.open(entry) as item, (TOOLS / name).open("wb") as target:
                        shutil.copyfileobj(item, target)
    if any((TOOLS / name).stat().st_size < 100_000 for name in binaries):
        raise RuntimeError("Incomplete bundled FFmpeg tools")
    print("Offline dependencies ready (including preview player).", flush=True)


if __name__ == "__main__":
    main()
