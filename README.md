# scenepackie.

**Make the clips. Get back to editing.**

Scenepackie is a small, free desktop tool that finds a chosen face in a movie or episode and cuts the matching footage into a scenepack. Made for people who would rather edit than spend their evening scrubbing through a timeline.

No login. No subscription. No uploading your movie anywhere.

## Download

**[Get Scenepackie 0.4 from Releases](../../releases/latest)**

Choose the download for your computer:

- **Windows:** `Scenepackie-v0.4-Windows.zip` — extract and launch `Scenepackie.exe`.
- **Mac with Apple Silicon (M1/M2/M3/M4 and newer):** `Scenepackie-v0.4-Mac-Apple-Silicon.zip` — extract and open `Scenepackie.app`.
- **Intel Mac:** `Scenepackie-v0.4-Mac-Intel.zip` — extract and open `Scenepackie.app`.

You don't need Python, Homebrew, FFmpeg or a terminal. The Mac downloads are not Apple-notarized; macOS may block the first launch. If so, use **System Settings → Privacy & Security → Open Anyway** after attempting to open the app. Do this only if you trust the download. Windows may similarly display a SmartScreen warning on unsigned builds.

## How it works

1. Pick a movie or TV episode from your computer.
2. Hit **Find characters** and choose the person you're looking for.
3. Review the matches. You can preview each clip with sound and uncheck anything you don't want.
4. Export the individual clips plus one full continuous scenepack video. You can also save a ZIP.

**New in 0.4:** Finished character and clip scans are saved automatically. Opening the same unchanged video again lets you continue without another full scan. The **Clear saved scans** button deletes that stored scan data, never your video or exported files. Moving or modifying the source video may require a new scan.

## A few things to know

Scenepackie looks for visible faces. A character whose face is hidden, turned away or only on screen for a split second can be missed. Sometimes another person gets picked up by mistake. Always check your clips before sharing them.

Larger videos take longer. The progress screen shows elapsed time, percentage, and an approximate time remaining. Video quality is kept high on export, but clips are re-encoded rather than bit-for-bit copied. Scenepackie does not contain films or episodes, and you should only process and distribute material you're entitled to use.

## Building from source

Python 3.11. Install `requirements.txt` plus `imageio-ffmpeg` on Mac, download the OpenCV models through `scripts/download_assets.py`, then run `python app.py`. The portable downloads already include everything needed. Run tests with:

```sh
python -m unittest discover -s tests -v
```

Code is MIT-licensed. FFmpeg, OpenCV, model files and other included dependencies retain their own licenses; consult their upstream licensing terms when redistributing the app.
