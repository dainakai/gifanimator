#!/usr/bin/env python3
from __future__ import annotations

from collections import OrderedDict
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageSequence, ImageTk

try:
    RESAMPLE_FILTER = Image.Resampling.BILINEAR
except AttributeError:
    RESAMPLE_FILTER = Image.BILINEAR


@dataclass
class GifEntry:
    path: Path
    mtime: float
    size: int


class GifAnimatorApp:
    FRAME_CACHE_LIMIT = 120
    SORT_OPTIONS = (
        "Name (A-Z)",
        "Name (Z-A)",
        "Time (Old-New)",
        "Time (New-Old)",
    )

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GIF Animator")
        self.root.geometry("1200x760")
        self.root.minsize(980, 640)

        self.current_file: Optional[Path] = None
        self.current_directory: Optional[Path] = None
        self.gif_entries: list[GifEntry] = []

        self.pil_frames: list[Image.Image] = []
        self.frame_durations_ms: list[int] = []
        self.current_frame_index = 0
        self.playing = False
        self.playback_after_id: Optional[str] = None
        self.resize_after_id: Optional[str] = None
        self.preview_render_cache: OrderedDict[tuple[int, int, int], ImageTk.PhotoImage] = OrderedDict()
        self.preview_size = (0, 0)
        self.current_photo: Optional[ImageTk.PhotoImage] = None

        self.speed_var = tk.DoubleVar(value=1.0)
        self.sort_var = tk.StringVar(value=self.SORT_OPTIONS[0])
        self._updating_slider = False

        self._build_ui()
        self._bind_shortcuts()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        app_frame = ttk.Frame(self.root, padding=8)
        app_frame.grid(row=0, column=0, sticky="nsew")
        app_frame.columnconfigure(0, weight=0, minsize=340)
        app_frame.columnconfigure(1, weight=1)
        app_frame.rowconfigure(0, weight=1)

        self._build_sidebar(app_frame)
        self._build_viewer(app_frame)

        self.status_var = tk.StringVar(value="GIFファイルを開いてください")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        status.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sidebar = ttk.LabelFrame(parent, text="Directory GIFs", padding=8)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)

        open_btn = ttk.Button(sidebar, text="GIFを開く", command=self.select_gif_file)
        open_btn.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        sort_row = ttk.Frame(sidebar)
        sort_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        sort_row.columnconfigure(1, weight=1)
        ttk.Label(sort_row, text="並び替え").grid(row=0, column=0, sticky="w", padx=(0, 6))

        sort_combo = ttk.Combobox(
            sort_row,
            state="readonly",
            textvariable=self.sort_var,
            values=self.SORT_OPTIONS,
        )
        sort_combo.grid(row=0, column=1, sticky="ew")
        sort_combo.bind("<<ComboboxSelected>>", lambda _: self.refresh_file_list())

        columns = ("name", "mtime", "size")
        self.file_tree = ttk.Treeview(
            sidebar,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=20,
        )
        self.file_tree.heading("name", text="Name")
        self.file_tree.heading("mtime", text="Modified")
        self.file_tree.heading("size", text="Size")
        self.file_tree.column("name", width=170, anchor="w")
        self.file_tree.column("mtime", width=120, anchor="w")
        self.file_tree.column("size", width=70, anchor="e")
        self.file_tree.grid(row=2, column=0, sticky="nsew")
        self.file_tree.bind("<Double-1>", self._on_file_double_click)

        tree_scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=2, column=1, sticky="ns")

        nav_row = ttk.Frame(sidebar)
        nav_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        nav_row.columnconfigure(0, weight=1)
        nav_row.columnconfigure(1, weight=1)

        prev_file_btn = ttk.Button(nav_row, text="Prev File", command=lambda: self.open_adjacent_file(-1))
        prev_file_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        next_file_btn = ttk.Button(nav_row, text="Next File", command=lambda: self.open_adjacent_file(1))
        next_file_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _build_viewer(self, parent: ttk.Frame) -> None:
        viewer = ttk.LabelFrame(parent, text="Preview", padding=8)
        viewer.grid(row=0, column=1, sticky="nsew")
        viewer.columnconfigure(0, weight=1)
        viewer.rowconfigure(0, weight=1)

        self.image_label = ttk.Label(viewer, anchor="center")
        self.image_label.grid(row=0, column=0, sticky="nsew")
        self.image_label.bind("<Configure>", self._on_preview_resize)

        controls = ttk.Frame(viewer)
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        controls.columnconfigure(1, weight=1)

        playback_row = ttk.Frame(controls)
        playback_row.grid(row=0, column=0, columnspan=2, sticky="ew")

        self.play_btn = ttk.Button(playback_row, text="再生", command=self.play)
        self.play_btn.grid(row=0, column=0, sticky="ew")
        self.pause_btn = ttk.Button(playback_row, text="停止", command=self.pause)
        self.pause_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        prev_frame_btn = ttk.Button(playback_row, text="◀", width=4, command=lambda: self.step_frame(-1))
        prev_frame_btn.grid(row=0, column=2, sticky="ew", padx=(12, 0))
        next_frame_btn = ttk.Button(playback_row, text="▶", width=4, command=lambda: self.step_frame(1))
        next_frame_btn.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        speed_frame = ttk.Frame(playback_row)
        speed_frame.grid(row=0, column=4, sticky="e", padx=(16, 0))
        ttk.Label(speed_frame, text="速度").grid(row=0, column=0, padx=(0, 6))
        ttk.Radiobutton(speed_frame, text="0.5x", variable=self.speed_var, value=0.5).grid(row=0, column=1)
        ttk.Radiobutton(speed_frame, text="1x", variable=self.speed_var, value=1.0).grid(row=0, column=2)
        ttk.Radiobutton(speed_frame, text="2x", variable=self.speed_var, value=2.0).grid(row=0, column=3)

        self.frame_slider = tk.Scale(
            controls,
            from_=0,
            to=0,
            orient=tk.HORIZONTAL,
            showvalue=False,
            command=self._on_slider_change,
            resolution=1,
        )
        self.frame_slider.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 2))

        info_row = ttk.Frame(controls)
        info_row.grid(row=2, column=0, columnspan=2, sticky="ew")
        info_row.columnconfigure(0, weight=1)

        self.frame_info_var = tk.StringVar(value="Frame: - / -")
        ttk.Label(info_row, textvariable=self.frame_info_var).grid(row=0, column=0, sticky="w")
        save_frame_btn = ttk.Button(info_row, text="現在フレームを保存", command=self.save_current_frame)
        save_frame_btn.grid(row=0, column=1, sticky="e")

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Left>", lambda _: self.step_frame(-1))
        self.root.bind("<Right>", lambda _: self.step_frame(1))
        self.root.bind("<space>", self._toggle_play_pause)

    def _toggle_play_pause(self, _: tk.Event) -> None:
        if self.playing:
            self.pause()
        else:
            self.play()

    def select_gif_file(self) -> None:
        initial_dir = str(self.current_directory) if self.current_directory else str(Path.cwd())
        path = filedialog.askopenfilename(
            title="GIFファイルを選択",
            initialdir=initial_dir,
            filetypes=[("GIF files", "*.gif *.GIF"), ("All files", "*.*")],
        )
        if path:
            self.load_gif(Path(path))

    def load_gif(self, path: Path) -> None:
        if not path.exists():
            messagebox.showerror("Error", f"File not found:\n{path}")
            return

        try:
            pil_frames, durations = self._read_gif_frames(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", f"GIF読み込みに失敗しました:\n{exc}")
            return

        self.pause()
        self.current_file = path.resolve()
        self.current_directory = self.current_file.parent
        self.pil_frames = pil_frames
        self.frame_durations_ms = durations
        self._clear_preview_cache()
        self.current_frame_index = 0

        self._set_slider_bounds(len(self.pil_frames))
        self.show_frame(0, force=True)
        self.refresh_file_list()
        self._select_current_file_in_tree()
        self.status_var.set(f"Loaded: {self.current_file}")

    def _read_gif_frames(self, path: Path) -> tuple[list[Image.Image], list[int]]:
        frames: list[Image.Image] = []
        durations: list[int] = []

        with Image.open(path) as img:
            if img.format != "GIF":
                raise ValueError("選択したファイルはGIFではありません。")

            base_duration = int(img.info.get("duration", 100))
            for frame in ImageSequence.Iterator(img):
                frame_duration = int(frame.info.get("duration", base_duration or 100))
                frames.append(frame.copy())
                durations.append(max(20, frame_duration))

        if not frames:
            raise ValueError("フレームが見つかりませんでした。")

        return frames, durations

    def _set_slider_bounds(self, frame_count: int) -> None:
        max_index = max(0, frame_count - 1)
        self._updating_slider = True
        self.frame_slider.configure(from_=0, to=max_index)
        self.frame_slider.set(0)
        self._updating_slider = False

    def _clear_preview_cache(self) -> None:
        self.preview_render_cache.clear()

    def _fit_frame_to_preview(self, frame: Image.Image, preview_size: tuple[int, int]) -> Image.Image:
        width, height = preview_size
        src_w, src_h = frame.size
        if src_w <= 0 or src_h <= 0:
            return frame

        scale = min(width / src_w, height / src_h)
        target_w = max(1, int(src_w * scale))
        target_h = max(1, int(src_h * scale))
        if target_w == src_w and target_h == src_h:
            return frame
        return frame.resize((target_w, target_h), RESAMPLE_FILTER)

    def _get_preview_size(self) -> tuple[int, int]:
        width = self.image_label.winfo_width()
        height = self.image_label.winfo_height()
        if width <= 1 or height <= 1:
            return (640, 480)
        return (width, height)

    def _get_or_create_photo(self, frame_index: int) -> ImageTk.PhotoImage:
        preview_size = self._get_preview_size()
        cache_key = (frame_index, preview_size[0], preview_size[1])
        cached = self.preview_render_cache.get(cache_key)
        if cached is not None:
            self.preview_render_cache.move_to_end(cache_key)
            return cached

        frame = self.pil_frames[frame_index]
        if frame.mode not in ("RGB", "RGBA"):
            frame = frame.convert("RGBA")
        resized_frame = self._fit_frame_to_preview(frame, preview_size)
        photo = ImageTk.PhotoImage(resized_frame)
        self.preview_render_cache[cache_key] = photo
        self.preview_render_cache.move_to_end(cache_key)
        while len(self.preview_render_cache) > self.FRAME_CACHE_LIMIT:
            self.preview_render_cache.popitem(last=False)
        return photo

    def show_frame(self, index: int, force: bool = False) -> None:
        if not self.pil_frames:
            return

        index = max(0, min(index, len(self.pil_frames) - 1))
        if not force and index == self.current_frame_index and self.current_photo is not None:
            return

        self.current_frame_index = index
        photo = self._get_or_create_photo(index)
        self.current_photo = photo
        self.image_label.configure(image=photo)
        self.image_label.image = photo

        self._updating_slider = True
        self.frame_slider.set(index)
        self._updating_slider = False

        self.frame_info_var.set(f"Frame: {index + 1} / {len(self.pil_frames)}")

    def _on_preview_resize(self, event: tk.Event) -> None:
        new_size = (max(1, event.width), max(1, event.height))
        if new_size == self.preview_size:
            return

        self.preview_size = new_size
        self._clear_preview_cache()
        if self.resize_after_id is not None:
            self.root.after_cancel(self.resize_after_id)
        self.resize_after_id = self.root.after(80, self._rerender_current_frame)

    def _rerender_current_frame(self) -> None:
        self.resize_after_id = None
        if self.pil_frames:
            self.show_frame(self.current_frame_index, force=True)

    def step_frame(self, delta: int) -> None:
        if not self.pil_frames:
            return
        next_index = (self.current_frame_index + delta) % len(self.pil_frames)
        self.show_frame(next_index)

    def _on_slider_change(self, value: str) -> None:
        if self._updating_slider or not self.pil_frames:
            return
        frame_index = int(float(value))
        self.show_frame(frame_index)

    def play(self) -> None:
        if not self.pil_frames:
            return
        if self.playing:
            return
        self.playing = True
        self._schedule_next_frame()

    def pause(self) -> None:
        self.playing = False
        if self.playback_after_id is not None:
            self.root.after_cancel(self.playback_after_id)
            self.playback_after_id = None

    def _schedule_next_frame(self) -> None:
        if not self.playing or not self.pil_frames:
            return

        speed = self.speed_var.get() or 1.0
        delay = int(self.frame_durations_ms[self.current_frame_index] / speed)
        delay = max(20, delay)
        self.playback_after_id = self.root.after(delay, self._playback_tick)

    def _playback_tick(self) -> None:
        if not self.playing or not self.pil_frames:
            return
        next_index = (self.current_frame_index + 1) % len(self.pil_frames)
        self.show_frame(next_index)
        self._schedule_next_frame()

    def refresh_file_list(self) -> None:
        if not self.current_directory:
            return

        entries: list[GifEntry] = []
        for item in self.current_directory.iterdir():
            if not item.is_file() or item.suffix.lower() != ".gif":
                continue
            stat = item.stat()
            entries.append(GifEntry(path=item.resolve(), mtime=stat.st_mtime, size=stat.st_size))

        sort_key = self.sort_var.get()
        if sort_key == "Name (A-Z)":
            entries.sort(key=lambda e: e.path.name.lower())
        elif sort_key == "Name (Z-A)":
            entries.sort(key=lambda e: e.path.name.lower(), reverse=True)
        elif sort_key == "Time (Old-New)":
            entries.sort(key=lambda e: e.mtime)
        elif sort_key == "Time (New-Old)":
            entries.sort(key=lambda e: e.mtime, reverse=True)

        self.gif_entries = entries
        self._render_file_tree()

    def _render_file_tree(self) -> None:
        self.file_tree.delete(*self.file_tree.get_children())
        for entry in self.gif_entries:
            mtime_text = datetime.fromtimestamp(entry.mtime).strftime("%Y-%m-%d %H:%M")
            size_kb = f"{entry.size / 1024:.1f} KB"
            self.file_tree.insert(
                "",
                "end",
                iid=str(entry.path),
                values=(entry.path.name, mtime_text, size_kb),
            )

    def _select_current_file_in_tree(self) -> None:
        if not self.current_file:
            return
        iid = str(self.current_file)
        if not self.file_tree.exists(iid):
            return
        self.file_tree.selection_set(iid)
        self.file_tree.focus(iid)
        self.file_tree.see(iid)

    def _on_file_double_click(self, _: tk.Event) -> None:
        selected = self.file_tree.selection()
        if not selected:
            return
        selected_path = Path(selected[0])
        if self.current_file and selected_path == self.current_file:
            return
        self.load_gif(selected_path)

    def open_adjacent_file(self, offset: int) -> None:
        if not self.gif_entries:
            return

        if self.current_file is None:
            self.load_gif(self.gif_entries[0].path)
            return

        all_paths = [entry.path for entry in self.gif_entries]
        if self.current_file not in all_paths:
            self.load_gif(all_paths[0])
            return

        index = all_paths.index(self.current_file)
        next_index = (index + offset) % len(all_paths)
        self.load_gif(all_paths[next_index])

    def save_current_frame(self) -> None:
        if not self.pil_frames or not self.current_file:
            messagebox.showinfo("Info", "先にGIFを開いてください。")
            return

        default_name = f"{self.current_file.stem}_frame_{self.current_frame_index + 1:04d}.png"
        output = filedialog.asksaveasfilename(
            title="フレーム保存",
            initialdir=str(self.current_file.parent),
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("GIF image", "*.gif"), ("All files", "*.*")],
        )
        if not output:
            return

        output_path = Path(output)
        frame = self.pil_frames[self.current_frame_index]
        try:
            if output_path.suffix.lower() == ".gif":
                frame.convert("P", palette=Image.ADAPTIVE).save(output_path, format="GIF")
            else:
                frame.save(output_path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", f"保存に失敗しました:\n{exc}")
            return

        self.status_var.set(f"Saved frame: {output_path}")


def main() -> None:
    root = tk.Tk()
    app = GifAnimatorApp(root)
    if app.current_file:
        app.load_gif(app.current_file)
    root.mainloop()


if __name__ == "__main__":
    main()
