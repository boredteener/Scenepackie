"""Prepare the native Scenepackie icons from the approved transparent artwork."""
from __future__ import annotations
import base64
from io import BytesIO
from pathlib import Path
import platform
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build_icons"


def main():
    source = ROOT / "assets" / "icon.webp.b64"
    icon = Image.open(BytesIO(base64.b64decode(source.read_text().strip(), validate=True))).convert("RGBA")
    if icon.size[0] != icon.size[1]:
        raise ValueError("App icon must be square")
    OUT.mkdir(exist_ok=True)
    icon.resize((512, 512), Image.Resampling.LANCZOS).save(OUT / "icon.png")
    icon.save(OUT / "Scenepackie.ico", format="ICO",
              sizes=[(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)])
    if platform.system() == "Darwin":
        import subprocess
        import shutil
        iconset = OUT / "Scenepackie.iconset"
        iconset.mkdir(exist_ok=True)
        for n in (16, 32, 128, 256, 512):
            icon.resize((n,n), Image.Resampling.LANCZOS).save(iconset / f"icon_{n}x{n}.png")
            icon.resize((n*2,n*2), Image.Resampling.LANCZOS).save(iconset / f"icon_{n}x{n}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "Scenepackie.icns")], check=True)
        shutil.rmtree(iconset)
    print("Native app icons generated.", flush=True)


if __name__ == "__main__":
    main()
