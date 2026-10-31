# scenepackie.

A free, private character scenepack maker for editors. No accounts, no subscription, no cloud processing. A soft cream-and-brown desktop interface with three steps: **choose a video → choose a face → export your clips**.

## Download the Windows app (no installation)

1. Open **[Actions → Build portable Windows app](../../actions/workflows/windows-portable.yml)**.
2. Open the latest successful build (green check mark).
3. Under **Artifacts**, download **Scenepackie-Windows-Portable**.
4. Unzip the downloaded archive (you may find another ZIP inside) and open **Scenepackie/Scenepackie.exe**.

The program is portable. You don't need to install Python, FFmpeg, face-recognition packages or any other programs. Windows may show a SmartScreen warning because the app isn't code-signed. GitHub retains workflow artifacts for 30 days; trigger the workflow again to build a fresh copy.

## What this version does

- Reads local MP4/MOV/MKV and other videos supported by OpenCV/FFmpeg.
- Scans frames for faces and groups visually similar faces into selectable portraits.
- Shows a live percentage, elapsed clock, and approximate time remaining during character discovery, clip searching, and exporting. While working, the start button is replaced by the progress screen so it cannot accidentally launch duplicate jobs. Cancellation returns you to the previous screen.
- Searches the video for appearances of your chosen face.
- Makes short clips around the matching frames. Review the timestamps, deselect unwanted clips, and export frame-accurate H.264 MP4 clips with audio.
- Can create a ZIP alongside the ordinary clip folder. Includes `clips.json` with timestamps.
- Processes your movie completely **on your own computer**. Doesn't upload it or call an AI service.

## Current limitations

**Early working version, not a promise of complete character coverage.** It detects visible, sufficiently clear *faces*, not every full-body appearance or offscreen spoken line. Characters can appear in more than one portrait group; some lighting, movement and occlusion can lead to missed matches or false positives. Scene boundaries are approximate and can be reviewed before export. Video scans can take a while on full movies, especially slower computers. Exporting re-encodes at high visual quality (CRF 18); it does **not** preserve original encoded bitstreams or lossless quality. Source material must be your own or footage you're entitled to process and share.

## Developers

Python 3.11, Tkinter, OpenCV YuNet + SFace, Pillow and FFmpeg. To run from source, install requirements and get the models from `scripts/download_assets.py`. Windows builds bundle those dependencies automatically. Run tests with `python -m unittest discover -s tests -v`.

Third-party libraries and models have their own licenses. The Windows package bundles FFmpeg. See OpenCV Zoo and FFmpeg's licenses and respect their terms if redistributing builds.
