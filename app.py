from __future__ import annotations

import os
import queue
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import imageio_ffmpeg

APP_NAME = "MP4 to MP3 Batch Converter"


def find_embedded_dash_mp4(path: Path) -> int | None:
    """Find an appended fragmented-DASH MP4 payload, as used by this PLAYit sample."""
    file_size = path.stat().st_size
    carry = b""
    position = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return None
            data = carry + chunk
            base = position - len(carry)
            search_from = 0
            while True:
                marker = data.find(b"ftyp", search_from)
                if marker < 0:
                    break
                absolute_marker = base + marker
                candidate = absolute_marker - 4
                search_from = marker + 4
                if candidate <= 0 or candidate + 16 >= file_size:
                    continue
                stream.seek(candidate)
                ftyp_header = stream.read(16)
                box_size = int.from_bytes(ftyp_header[:4], "big")
                if ftyp_header[4:8] != b"ftyp" or not 16 <= box_size <= 4096:
                    continue
                stream.seek(candidate + 8)
                brands = stream.read(box_size - 8)
                if b"dash" not in brands:
                    continue
                moov_start = candidate + box_size
                stream.seek(moov_start)
                moov_header = stream.read(8)
                if len(moov_header) < 8 or moov_header[4:8] != b"moov":
                    continue
                moov_size = int.from_bytes(moov_header[:4], "big")
                if not 8 <= moov_size <= 1024 * 1024:
                    continue
                moov = moov_header + stream.read(moov_size - 8)
                if len(moov) != moov_size or b"mvex" not in moov:
                    continue
                # A fragmented MP4 begins with sidx/moof after its init segment.
                stream.seek(moov_start + moov_size)
                following = stream.read(8)
                if len(following) == 8 and following[4:8] in (b"sidx", b"moof"):
                    return candidate
            carry = data[-7:]
            position += len(chunk)
            stream.seek(position)


class ConverterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("700x430")
        self.minsize(620, 390)
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running = False
        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self.recursive = tk.BooleanVar(value=False)
        self.overwrite = tk.BooleanVar(value=False)
        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text=APP_NAME, font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(0, 14))
        self._path_row(root, "Folder containing MP4 files", self.source, self._choose_source)
        self._path_row(root, "Save converted MP3 files to", self.destination, self._choose_destination)
        options = ttk.Frame(root)
        options.pack(fill="x", pady=8)
        ttk.Checkbutton(options, text="Include MP4 files in subfolders", variable=self.recursive).pack(anchor="w")
        ttk.Checkbutton(options, text="Replace MP3 files that already exist", variable=self.overwrite).pack(anchor="w", pady=(5, 0))
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", pady=(14, 8))
        self.status = ttk.Label(root, text="Choose folders to get started.")
        self.status.pack(anchor="w")
        self.log = tk.Text(root, height=9, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(10, 12))
        self.start_button = ttk.Button(root, text="Convert MP4 files to MP3", command=self.start)
        self.start_button.pack(anchor="e")

    def _path_row(self, parent, label, variable, command) -> None:
        ttk.Label(parent, text=label).pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 11))
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=command).pack(side="left", padx=(8, 0))

    def _choose_source(self) -> None:
        path = filedialog.askdirectory(title="Select folder containing MP4 files")
        if path:
            self.source.set(path)
            if not self.destination.get():
                self.destination.set(path)

    def _choose_destination(self) -> None:
        path = filedialog.askdirectory(title="Select folder for MP3 files")
        if path:
            self.destination.set(path)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self) -> None:
        if self.running:
            return
        source, destination = Path(self.source.get()).expanduser(), Path(self.destination.get()).expanduser()
        if not source.is_dir():
            messagebox.showerror("Invalid source folder", "Select an existing folder containing MP4 files.")
            return
        if not destination.exists():
            try:
                destination.mkdir(parents=True)
            except OSError as exc:
                messagebox.showerror("Cannot create destination", str(exc))
                return
        if not destination.is_dir():
            messagebox.showerror("Invalid destination", "The destination must be a folder.")
            return
        try:
            same = os.path.samefile(source, destination)
        except OSError:
            same = source.resolve() == destination.resolve()
        if same and self.recursive.get():
            messagebox.showerror("Folder conflict", "For recursive conversion, choose a different destination folder to avoid processing outputs as inputs.")
            return
        files = sorted(source.rglob("*") if self.recursive.get() else source.iterdir())
        files = [p for p in files if p.is_file() and p.suffix.lower() == ".mp4"]
        if not files:
            messagebox.showinfo("No MP4 files", "No MP4 files were found with the selected options.")
            return
        self.running = True
        self.start_button.configure(state="disabled")
        self.progress.start(12)
        self.status.configure(text=f"Converting {len(files)} file(s)…")
        self._append_log(f"Found {len(files)} MP4 file(s).")
        args = (source, destination, files, self.recursive.get(), self.overwrite.get())
        threading.Thread(target=self._convert, args=args, daemon=True).start()

    def _convert(self, source: Path, destination: Path, files: list[Path], recursive: bool, overwrite: bool) -> None:
        ok = failed = skipped = 0
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        for index, src in enumerate(files, 1):
            rel = src.relative_to(source) if recursive else Path(src.name)
            out = (destination / rel).with_suffix(".mp3")
            temporary_input: Path | None = None
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                if out.exists() and not overwrite:
                    skipped += 1
                    self.events.put(("log", f"SKIP (already exists): {out}"))
                    continue
                input_path = src
                payload_offset = find_embedded_dash_mp4(src)
                if payload_offset is not None:
                    handle, temporary_name = tempfile.mkstemp(suffix=".mp4", prefix="playit_payload_")
                    os.close(handle)
                    temporary_input = Path(temporary_name)
                    with src.open("rb") as original, temporary_input.open("wb") as extracted:
                        original.seek(payload_offset)
                        shutil.copyfileobj(original, extracted)
                    input_path = temporary_input
                    self.events.put(("log", f"PLAYit Smart Muxer payload found in {src.name}; extracting embedded audio."))
                cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y" if overwrite else "-n", "-i", str(input_path), "-vn", "-codec:a", "libmp3lame", "-b:a", "192k", str(out)]
                result = subprocess.run(cmd, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.returncode == 0:
                    ok += 1
                    self.events.put(("log", f"OK: {src.name} → {out}"))
                else:
                    failed += 1
                    detail = result.stderr.strip().splitlines()
                    self.events.put(("log", f"FAILED: {src.name} — {(detail[-1] if detail else 'ffmpeg error')[:250]}"))
            except Exception as exc:
                failed += 1
                self.events.put(("log", f"FAILED: {src.name} — {exc}"))
            finally:
                if temporary_input is not None:
                    temporary_input.unlink(missing_ok=True)
            self.events.put(("status", f"Processed {index}/{len(files)} · {ok} converted · {skipped} skipped · {failed} failed"))
        self.events.put(("done", f"Finished: {ok} converted, {skipped} skipped, {failed} failed."))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "log":
                    self._append_log(text)
                elif kind == "status":
                    self.status.configure(text=text)
                else:
                    self.running = False
                    self.progress.stop()
                    self.start_button.configure(state="normal")
                    self.status.configure(text=text)
                    self._append_log(text)
                    if "failed" in text and not text.endswith("0 failed."):
                        messagebox.showwarning("Conversion finished", text)
                    else:
                        messagebox.showinfo("Conversion finished", text)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)


if __name__ == "__main__":
    ConverterApp().mainloop()
