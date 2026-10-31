"""Scenepackie desktop application — built for editors, without extra setup."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from scenepackie.core import Cancelled, FaceGroup, FaceScanner, Clip, clock, export_clips, video_info


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
        self.source = ""
        self.groups: list[FaceGroup] = []
        self.clips: list[Clip] = []
        self.selection = None
        self.page = "upload"
        self.queue: Queue = Queue()
        self.cancel = threading.Event()
        self.working = False
        self.photos: list[ImageTk.PhotoImage] = []
        self.make_zip = tk.BooleanVar(value=True)
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
        self.progress = ttk.Progressbar(footer, style="Warm.Horizontal.TProgressbar", mode="determinate", maximum=100, length=185)
        self.progress.pack(side="right", pady=4)
        self.progress.pack_forget()
        self.cancel_button = self._button(footer, "Cancel", self.cancel.set, primary=False)

    def _set_step(self, index):
        for i, label in enumerate(self.step_labels):
            label.configure(fg=BROWN if i == index else MUTED)

    def _clear(self):
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
        self.show_upload()

    def _job(self, task, callback):
        if self.working:
            return
        self.cancel = threading.Event()
        self.working = True
        self.progress.configure(value=0)
        self.progress.pack(side="right", padx=(14, 0), pady=4)
        self.cancel_button.pack(side="right")
        self.status.configure(text="working...")

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

    def discover(self):
        self._job(lambda cancel, report: FaceScanner().discover(self.source, cancel, report), self._found)

    def _found(self, groups):
        self.groups = groups
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
        group = self.groups[index]
        self._job(lambda cancel, report: FaceScanner().find_clips(self.source, group, cancel, report), self._matched)

    def _matched(self, clips):
        self.clips = clips
        self.show_clips()

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
            def change(value=var, item=clip):
                item.keep = value.get()
            row = tk.Frame(inner, bg=CREAM if i % 2 else PAPER, padx=10, pady=9)
            row.pack(fill="x", pady=(0, 2))
            tk.Checkbutton(row, text=f"Clip {i:03d}", variable=var, command=change, bg=row.cget("bg"), fg=DARK, activebackground=row.cget("bg"), font=("Segoe UI", 10, "bold"), selectcolor=PAPER).pack(side="left")
            self._label(row, f"{clock(clip.start)}  –  {clock(clip.end)}     ({int(clip.duration)}s)", color=MUTED, size=10).pack(side="right")
        controls = tk.Frame(box, bg=PAPER)
        controls.pack(fill="x", pady=(16, 0))
        tk.Checkbutton(controls, text="Also make a ZIP file", variable=self.make_zip, bg=PAPER, fg=DARK, activebackground=PAPER, selectcolor=PAPER, font=("Segoe UI", 10)).pack(side="left")
        self._button(controls, "Export clips   →", self.export).pack(side="right")
        self._button(controls, "Back", self.show_faces, primary=False, padx=15).pack(side="right", padx=(0, 10))

    def export(self):
        folder = filedialog.askdirectory(title="Where should your scenepack go?")
        if not folder:
            return
        self._job(lambda cancel, report: export_clips(self.source, self.clips, folder, self.make_zip.get(), cancel, report), self._exported)

    def _exported(self, location):
        self.status.configure(text="finished!")
        messagebox.showinfo("Scenepack ready", f"Your clips were saved here:\n\n{location}\n\nYou can find the individual clips in the matching folder.")

    def _poll(self):
        try:
            while True:
                event, payload = self.queue.get_nowait()
                if event == "progress":
                    label, fraction = payload
                    self.status.configure(text=label.lower())
                    self.progress.configure(value=max(0, min(100, fraction * 100)))
                else:
                    self.working = False
                    self.progress.pack_forget()
                    self.cancel_button.pack_forget()
                    if event == "done":
                        callback, result = payload
                        self.status.configure(text="ready")
                        callback(result)
                    elif event == "cancelled":
                        self.status.configure(text="cancelled")
                    elif event == "error":
                        self.status.configure(text="couldn't finish")
                        messagebox.showerror("Something went wrong", payload)
        except Empty:
            pass
        self.root.after(100, self._poll)


def main():
    root = tk.Tk()
    Scenepackie(root)
    root.mainloop()


if __name__ == "__main__":
    main()
