"""Scenepackie desktop application — built for editors, without extra setup."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import subprocess
import os
import sys
import tempfile
from queue import Empty, Queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk
from scenepackie.core import resource_path

from scenepackie.core import Cancelled, FaceGroup, FaceScanner, Clip, binary, creation_flags, clock, export_clips, video_info
from scenepackie.progress import estimate_remaining
from scenepackie.cache import read_snapshot, save_characters, save_clips, clear_saved_scans
from scenepackie.preview import create_mac_preview


CREAM = "#F8F5EF"
PAPER = "#FFFDF8"
TAN = "#E6D9C6"
BROWN = "#684A37"
DARK = "#372D27"
MUTED = "#897B6F"
LINE = "#E9E1D6"


class Scenepackie:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("scenepackie")
        self.root.geometry("960x735")
        self.root.minsize(760, 570)
        self.root.configure(bg=CREAM)
        try:
            self.app_icon = ImageTk.PhotoImage(Image.open(resource_path("assets/icon.png")).convert("RGBA"), master=self.root)
            self.root.iconphoto(True, self.app_icon)
        except (OSError, RuntimeError, tk.TclError):
            pass
        self.source = ""
        self.groups: list[FaceGroup] = []
        self.clips: list[Clip] = []
        self.selection = None
        self.page = "upload"
        self.queue: Queue = Queue()
        self.cancel = threading.Event()
        self.working = False
        self.job_started = 0.0
        self.job_fraction = 0.0
        self.job_stage = ""
        self.return_page = "upload"
        self.photos: list[ImageTk.PhotoImage] = []
        self.make_zip = tk.BooleanVar(value=True)
        self.preview_process = None
        self.clip_vars = []
        self.saved_matches = {}
        self._theme()
        self._layout()
        self.show_upload()
        self.root.after(100, self._poll)

    def _theme(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Warm.Horizontal.TProgressbar", troughcolor=LINE, background=BROWN, borderwidth=0, thickness=8)

    def _label(self, parent, text, size=12, color=DARK, bold=False, **kwargs):
        return tk.Label(parent, text=text, font=("Segoe UI", size, "bold" if bold else "normal"), fg=color, bg=parent.cget("bg"), **kwargs)

    def _button(self, parent, text, action, primary=True, **kwargs):
        bg, fg = (BROWN, "#FFFFFF") if primary else (TAN, DARK)
        btn = tk.Button(parent, text=text, command=action, bg=bg, fg=fg, activebackground=DARK if primary else LINE,
                        activeforeground="#FFFFFF" if primary else DARK, relief="flat", bd=0, cursor="hand2",
                        font=("Segoe UI", 11, "bold"), padx=kwargs.pop("padx", 22), pady=kwargs.pop("pady", 12), **kwargs)
        return btn

    def _layout(self):
        header = tk.Frame(self.root, bg=CREAM, padx=46, pady=23)
        header.pack(fill="x")
        self._label(header, "scenepackie.", size=20, color=BROWN, bold=True).pack(side="left")
        self._label(header, "free  ·  private  ·  offline", size=10, color=MUTED).pack(side="right", pady=6)
        tk.Frame(self.root, bg=LINE, height=1).pack(fill="x")

        main = tk.Frame(self.root, bg=CREAM, padx=46, pady=27)
        main.pack(fill="both", expand=True)
        self._label(main, "make a scenepack.", size=29, bold=True, color=DARK).pack(anchor="w")
        self._label(main, "one video, one character, every matching clip.", size=12, color=MUTED).pack(anchor="w", pady=(2, 22))

        steps = tk.Frame(main, bg=CREAM)
        steps.pack(fill="x", pady=(0, 17))
        self.step_labels = []
        for name in ["01  add a video", "02  pick a character", "03  get your clips"]:
            label = self._label(steps, name, size=10, color=MUTED, bold=True)
            label.pack(side="left", padx=(0, 29))
            self.step_labels.append(label)
        self.body = tk.Frame(main, bg=PAPER, highlightbackground=LINE, highlightthickness=1)
        self.body.pack(fill="both", expand=True)

        footer = tk.Frame(self.root, bg=CREAM, padx=46, pady=16)
        footer.pack(fill="x")
        self.status = self._label(footer, "ready when you are", color=MUTED, size=10)
        self.status.pack(side="left")

    def _set_step(self, index):
        for i, label in enumerate(self.step_labels):
            label.configure(fg=BROWN if i == index else MUTED)

    def _clear(self):
        self._stop_preview()
        self.photos.clear()
        for widget in self.body.winfo_children():
            widget.destroy()

    def _panel(self, top=34):
        panel = tk.Frame(self.body, bg=PAPER, padx=38, pady=top)
        panel.pack(fill="both", expand=True)
        return panel

    def show_upload(self):
        self.page = "upload"
        self._set_step(0)
        self._clear()
        box = self._panel(49)
        self._label(box, "start with a video", size=21, bold=True).pack(anchor="w")
        self._label(box, "Choose a movie, TV episode or video from your computer.", color=MUTED, size=11).pack(anchor="w", pady=(5, 25))
        tile = tk.Frame(box, bg=CREAM, highlightbackground=TAN, highlightthickness=1, padx=23, pady=29)
        tile.pack(fill="x", pady=(0, 20))
        self._label(tile, "your video stays on your computer", size=12, bold=True, color=BROWN).pack(anchor="w")
        self._label(tile, "MP4, MKV, MOV, AVI and other supported videos", size=10, color=MUTED).pack(anchor="w", pady=(5, 15))
        self._button(tile, "Choose video", self.pick_video).pack(anchor="w")
        if self.source:
            self._label(box, Path(self.source).name, color=BROWN, size=12, bold=True, wraplength=650, justify="left").pack(anchor="w", pady=(0, 14))
            self._button(box, "Find characters   →", self.discover).pack(anchor="w")
        self._label(box, "No account, uploads, or subscriptions needed.", color=MUTED, size=10).pack(anchor="w", pady=(28, 0))
        self._button(box, "Clear saved scans", self.clear_scans, primary=False, padx=12, pady=7).pack(anchor="w", pady=(12, 0))

    def pick_video(self):
        path = filedialog.askopenfilename(title="Choose a video", filetypes=[("Video files", "*.mp4 *.mkv *.mov *.avi *.m4v *.webm"), ("All files", "*.*")])
        if not path:
            return
        try:
            video_info(path)
        except Exception as exc:
            messagebox.showerror("Couldn't open video", str(exc))
            return
        self.source = path
        self.groups = []
        self.clips = []
        self.saved_matches = {}
        self.show_upload()

    def _show_processing(self, title, description):
        """Replace the previous action screen so scans cannot be started twice."""
        self.page = "processing"
        self._clear()
        box = self._panel(39)
        self._label(box, "working on your video", size=23, bold=True).pack(anchor="w")
        self._label(box, description, size=11, color=MUTED, wraplength=630, justify="left").pack(anchor="w", pady=(7, 27))

        summary = tk.Frame(box, bg=CREAM, padx=24, pady=23, highlightbackground=LINE, highlightthickness=1)
        summary.pack(fill="x")
        top = tk.Frame(summary, bg=CREAM)
        top.pack(fill="x")
        self.stage_label = self._label(top, title, size=13, color=BROWN, bold=True)
        self.stage_label.pack(side="left", anchor="s")
        self.percent_label = self._label(top, "0%", size=22, color=DARK, bold=True)
        self.percent_label.pack(side="right")
        self.job_progress = ttk.Progressbar(summary, style="Warm.Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.job_progress.pack(fill="x", pady=(18, 19))
        times = tk.Frame(summary, bg=CREAM)
        times.pack(fill="x")
        self.elapsed_label = self._label(times, "Elapsed  00:00:00", color=MUTED, size=11)
        self.elapsed_label.pack(side="left")
        self.remaining_label = self._label(times, "Time left  Calculating...", color=MUTED, size=11)
        self.remaining_label.pack(side="right")

        self.processing_hint = self._label(box, "Scenepackie is still running. You don't need to click anything again.", color=MUTED, size=10, wraplength=635, justify="left")
        self.processing_hint.pack(anchor="w", pady=(22, 16))
        self.processing_cancel = self._button(box, "Cancel", self._cancel_job, primary=False, padx=23, pady=10)
        self.processing_cancel.pack(anchor="w")

    def _cancel_job(self):
        if not self.working or self.cancel.is_set():
            return
        self.cancel.set()
        self.processing_cancel.configure(text="Cancelling...", state="disabled", cursor="arrow")
        self.processing_hint.configure(text="Finishing the current step before stopping...")

    def _update_processing(self):
        """Update the clock independently of frame processing to show responsiveness."""
        if not self.working or self.page != "processing":
            return
        elapsed = max(0.0, time.monotonic() - self.job_started)
        fraction = self.job_fraction
        percent = min(100, max(0, round(fraction * 100)))
        self.stage_label.configure(text=self.job_stage)
        self.percent_label.configure(text=f"{percent}%")
        self.job_progress.configure(value=fraction * 100)
        self.elapsed_label.configure(text=f"Elapsed  {clock(elapsed)}")
        remaining = estimate_remaining(elapsed, fraction)
        if self.cancel.is_set():
            remaining_text = "Stopping..."
        elif fraction >= 1:
            remaining_text = "Finishing up..."
        elif remaining is None:
            remaining_text = "Calculating..."
        else:
            remaining_text = f"~{clock(remaining)} (estimate)"
        self.remaining_label.configure(text=f"Time left  {remaining_text}")
        self.status.configure(text=f"{self.job_stage.lower()}  ·  {percent}%")

    def _restore_page(self):
        if self.return_page == "faces":
            self.show_faces()
        elif self.return_page == "clips":
            self.show_clips()
        else:
            self.show_upload()

    def _job(self, task, callback, title, description):
        if self.working:
            return
        self.cancel = threading.Event()
        self.working = True
        self.return_page = self.page
        self.job_started = time.monotonic()
        self.job_fraction = 0.0
        self.job_stage = title
        self._show_processing(title, description)
        self._update_processing()

        def report(label, fraction):
            self.queue.put(("progress", (label, fraction)))

        def work():
            try:
                result = task(self.cancel, report)
                self.queue.put(("done", (callback, result)))
            except Cancelled:
                self.queue.put(("cancelled", None))
            except Exception as exc:
                self.queue.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def clear_scans(self):
        if self.working:
            return
        if not messagebox.askyesno("Clear saved scans", "Delete saved scan results? Your movies and exported clips will not be touched."):
            return
        try:
            count, _ = clear_saved_scans()
            self.saved_matches = {}
            messagebox.showinfo("Saved scans cleared", f"Removed {count} saved scan(s).")
        except OSError as exc:
            messagebox.showerror("Couldn't clear scans", str(exc))

    def _save_safely(self, fn):
        try:
            fn()
        except (OSError, ValueError, TypeError):
            self.status.configure(text="Finished, but couldn't save the scan")

    def discover(self):
        cached = read_snapshot(self.source)
        if cached is not None:
            self.groups, self.saved_matches = cached
            self.show_faces()
            self.status.configure(text="Loaded saved scan")
            return
        self._job(lambda cancel, report: FaceScanner().discover(self.source, cancel, report), self._found,
                  "Finding characters", "Scanning faces throughout your video. Longer movies can take a while, but the timer will keep running.")

    def _found(self, groups):
        self.groups = groups
        self.saved_matches = {}
        self._save_safely(lambda: save_characters(self.source, groups))
        self.show_faces()

    def show_faces(self):
        self.page = "faces"
        self._set_step(1)
        self._clear()
        box = self._panel(25)
        self._label(box, "who are we looking for?", size=19, bold=True).pack(anchor="w")
        self._label(box, "Choose a face below. If someone appears twice, choose their clearest photo.", size=10, color=MUTED).pack(anchor="w", pady=(4, 13))
        if not self.groups:
            self._label(box, "No repeated faces were found. Try a different or clearer video.", color=MUTED).pack(anchor="w", pady=18)
            self._button(box, "Choose another video", self.show_upload, primary=False).pack(anchor="w")
            return
        canvas = tk.Canvas(box, bg=PAPER, highlightthickness=0)
        scroll = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        gallery = tk.Frame(canvas, bg=PAPER)
        gallery.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=gallery, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        for index, group in enumerate(self.groups):
            card = tk.Frame(gallery, bg=CREAM, highlightbackground=LINE, highlightthickness=1, padx=9, pady=9)
            card.grid(row=index // 5, column=index % 5, padx=(0, 12), pady=(0, 12), sticky="n")
            image = Image.open(BytesIO(group.image)).convert("RGB").resize((106, 106))
            photo = ImageTk.PhotoImage(image, master=self.root)
            self.photos.append(photo)
            face = tk.Label(card, image=photo, bg=CREAM, cursor="hand2")
            face.pack()
            face.bind("<Button-1>", lambda _, i=index: self.choose_face(i))
            self._button(card, f"Choose  #{index+1}", lambda i=index: self.choose_face(i), primary=False, padx=7, pady=6).pack(fill="x", pady=(8, 0))
        self._label(box, "Faces are detected from video frames. Check the exported clips for missed or incorrect matches.", color=MUTED, size=9, wraplength=680, justify="left").pack(anchor="w", pady=(12, 0))

    def choose_face(self, index):
        self.selection = index
        if str(index) in self.saved_matches:
            self.clips = self.saved_matches[str(index)]
            self.show_clips()
            self.status.configure(text="Loaded saved clips")
            return
        group = self.groups[index]
        self._job(lambda cancel, report: FaceScanner().find_clips(self.source, group, cancel, report), self._matched,
                  "Finding matching scenes", "Looking through the video for your chosen character. This is a more detailed scan.")

    def _save_selection(self):
        if self.selection is not None:
            self.saved_matches[str(self.selection)] = self.clips
            self._save_safely(lambda: save_clips(self.source, self.selection, self.clips))

    def _matched(self, clips):
        self.clips = clips
        self._save_selection()
        self.show_clips()

    def _stop_preview(self):
        player = self.preview_process
        self.preview_process = None
        if player is not None and player.poll() is None:
            player.terminate()

    def preview_clip(self, clip):
        self._stop_preview()
        if clip.duration <= 0:
            return
        if sys.platform == "darwin":
            def playback():
                try:
                    target = create_mac_preview(self.source, clip)
                    subprocess.Popen(["open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.root.after(0, lambda: self.status.configure(text="Preview opened"))
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    self.root.after(0, lambda message=str(exc): messagebox.showerror("Preview unavailable", message))
            threading.Thread(target=playback, daemon=True).start()
            self.status.configure(text="Preparing clip preview...")
            return
        try:
            self.preview_process = subprocess.Popen(
                [binary("ffplay"), "-loglevel", "error", "-autoexit",
                 "-window_title", "scenepackie · clip preview",
                 "-ss", f"{clip.start:.3f}", "-t", f"{clip.duration:.3f}", "-i", self.source],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=creation_flags())
        except OSError as exc:
            messagebox.showerror("Couldn't preview clip", str(exc))

    def set_all_clips(self, keep):
        for clip, var in zip(self.clips, self.clip_vars):
            clip.keep = keep
            var.set(keep)
        self._update_selected()
        self._save_selection()

    def _update_selected(self):
        count = sum(clip.keep for clip in self.clips)
        if hasattr(self, "selected_label") and self.selected_label.winfo_exists():
            self.selected_label.configure(text=f"{count} of {len(self.clips)} clips selected")

    def show_clips(self):
        self.page = "clips"
        self._set_step(2)
        self._clear()
        box = self._panel(22)
        self._label(box, "your clips are ready to review", size=19, bold=True).pack(anchor="w")
        self._label(box, f"{len(self.clips)} clips found  ·  uncheck anything you don't want", size=11, color=MUTED).pack(anchor="w", pady=(3, 12))
        if not self.clips:
            self._label(box, "No matches found. Try another face from the character list.", color=MUTED).pack(anchor="w", pady=15)
            self._button(box, "Back to characters", self.show_faces, primary=False).pack(anchor="w")
            return
        tools = tk.Frame(box, bg=PAPER)
        tools.pack(fill="x", pady=(0, 10))
        self.selected_label = self._label(tools, "", size=10, color=MUTED)
        self.selected_label.pack(side="left")
        self._button(tools, "Deselect all", lambda: self.set_all_clips(False), primary=False, padx=10, pady=5).pack(side="right")
        self._button(tools, "Select all", lambda: self.set_all_clips(True), primary=False, padx=10, pady=5).pack(side="right", padx=(0, 8))
        self.clip_vars = []
        listing = tk.Frame(box, bg=PAPER)
        listing.pack(fill="both", expand=True)
        canvas = tk.Canvas(listing, bg=PAPER, highlightthickness=0)
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PAPER)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        for i, clip in enumerate(self.clips, 1):
            var = tk.BooleanVar(value=clip.keep)
            self.clip_vars.append(var)
            def change(value=var, item=clip):
                item.keep = value.get()
                self._update_selected()
                self._save_selection()
            row = tk.Frame(inner, bg=CREAM if i % 2 else PAPER, padx=10, pady=9)
            row.pack(fill="x", pady=(0, 2))
            tk.Checkbutton(row, text=f"Clip {i:03d}", variable=var, command=change, bg=row.cget("bg"), fg=DARK, activebackground=row.cget("bg"), font=("Segoe UI", 10, "bold"), selectcolor=PAPER).pack(side="left")
            self._button(row, "▶ Preview", lambda item=clip: self.preview_clip(item), primary=False, padx=9, pady=5).pack(side="right", padx=(10, 0))
            self._label(row, f"{clock(clip.start)}  –  {clock(clip.end)}     ({int(clip.duration)}s)", color=MUTED, size=10).pack(side="right")
        self._update_selected()
        controls = tk.Frame(box, bg=PAPER)
        controls.pack(fill="x", pady=(16, 0))
        tk.Checkbutton(controls, text="ZIP everything (individual clips + full scenepack)", variable=self.make_zip, bg=PAPER, fg=DARK, activebackground=PAPER, selectcolor=PAPER, font=("Segoe UI", 10)).pack(side="left")
        self._button(controls, "Export clips   →", self.export).pack(side="right")
        self._button(controls, "Back", self.show_faces, primary=False, padx=15).pack(side="right", padx=(0, 10))

    def export(self):
        folder = filedialog.askdirectory(title="Where should your scenepack go?")
        if not folder:
            return
        self._job(lambda cancel, report: export_clips(self.source, self.clips, folder, self.make_zip.get(), cancel, report), self._exported,
                  "Exporting clips", "Saving your selected clips to your computer. Please leave this window open until the export finishes.")

    def _exported(self, location):
        self.status.configure(text="finished!")
        messagebox.showinfo("Scenepack ready", f"Your clips were saved here:\n\n{location}\n\nYou can find the individual clips in the matching folder.")

    def _poll(self):
        try:
            while True:
                event, payload = self.queue.get_nowait()
                if event == "progress":
                    label, fraction = payload
                    if self.working:
                        self.job_stage = label
                        self.job_fraction = max(self.job_fraction, max(0.0, min(1.0, fraction)))
                else:
                    self.working = False
                    if event == "done":
                        callback, result = payload
                        self.status.configure(text="ready")
                        callback(result)
                    elif event == "cancelled":
                        self._restore_page()
                        self.status.configure(text="cancelled")
                    elif event == "error":
                        self._restore_page()
                        self.status.configure(text="couldn't finish")
                        messagebox.showerror("Something went wrong", payload)
        except Empty:
            pass
        self._update_processing()
        self.root.after(100, self._poll)


def main():
    root = tk.Tk()
    Scenepackie(root)
    root.mainloop()


if __name__ == "__main__":
    main()
