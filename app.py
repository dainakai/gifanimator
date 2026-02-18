#!/usr/bin/env python3
from __future__ import annotations

from collections import OrderedDict
import os
import re
import subprocess
import sys
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageSequence, ImageTk

import tkinter.font as tkfont


def _find_available_font_family(root: tk.Tk, candidates: tuple[str, ...]) -> Optional[str]:
    try:
        available = {family.casefold(): family for family in tkfont.families(root)}
    except tk.TclError:
        return None

    for candidate in candidates:
        family = available.get(candidate.casefold())
        if family:
            return family
    return None


def _select_ui_font_family(root: tk.Tk) -> Optional[str]:
    override = os.environ.get("GIF_ANIMATOR_FONT_FAMILY")
    if override:
        return _find_available_font_family(root, (override,))

    if not sys.platform.startswith("linux"):
        return None

    return _find_available_font_family(
        root,
        (
            "Noto Sans CJK JP",
            "Noto Sans JP",
            "Source Han Sans JP",
            "Ubuntu",
            "Cantarell",
            "Noto Sans",
            "DejaVu Sans",
        ),
    )


def _select_fixed_font_family(root: tk.Tk) -> Optional[str]:
    override = os.environ.get("GIF_ANIMATOR_FIXED_FONT_FAMILY")
    if override:
        return _find_available_font_family(root, (override,))

    if not sys.platform.startswith("linux"):
        return None

    return _find_available_font_family(
        root,
        (
            "Noto Sans Mono CJK JP",
            "Source Han Code JP",
            "Ubuntu Mono",
            "DejaVu Sans Mono",
        ),
    )


def apply_font_scaling(
    root: tk.Tk,
    text_scale: float,
    min_abs_size: int = 10,
    ui_font_family: Optional[str] = None,
    fixed_font_family: Optional[str] = None,
) -> None:
    """
    Tk の named font（TkDefaultFont 等）を text_scale 倍して更新する。
    フォントサイズは、正なら point 指定、負なら pixel 指定なので符号を保って拡大する。
    """
    ui_font_names = (
        "TkDefaultFont",
        "TkTextFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkCaptionFont",
        "TkSmallCaptionFont",
        "TkIconFont",
        "TkTooltipFont",
    )
    fixed_font_names = ("TkFixedFont",)

    for name in ui_font_names + fixed_font_names:
        try:
            f = tkfont.nametofont(name)
        except tk.TclError:
            continue

        size = int(f.cget("size"))
        if size == 0:
            continue

        abs_size = abs(size)
        new_abs = max(min_abs_size, int(round(abs_size * text_scale)))
        configure_kwargs = {"size": new_abs if size > 0 else -new_abs}
        if name in fixed_font_names:
            if fixed_font_family:
                configure_kwargs["family"] = fixed_font_family
        elif ui_font_family:
            configure_kwargs["family"] = ui_font_family
        f.configure(**configure_kwargs)

    # ttk の一部テーマでフォントが固定される場合の保険（基本は named font 更新だけで足ります）
    try:
        style = ttk.Style(root)
        style.configure(".", font=tkfont.nametofont("TkDefaultFont"))
        style.configure("Treeview", font=tkfont.nametofont("TkDefaultFont"))
        style.configure("Treeview.Heading", font=tkfont.nametofont("TkHeadingFont"))
    except tk.TclError:
        pass


try:
    RESAMPLE_FILTER = Image.Resampling.BILINEAR
except AttributeError:
    RESAMPLE_FILTER = Image.BILINEAR


def _safe_float(value: str | None) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _detect_ui_scale_from_env() -> Optional[float]:
    """
    GNOME/Wayland 系でよく使われる環境変数から UI スケール（96DPI=1.0 基準）を推定する。
    - 150% の場合、概ね 1.5 が得られる想定。
    """
    gdk_scale = _safe_float(os.environ.get("GDK_SCALE"))
    gdk_dpi_scale = _safe_float(os.environ.get("GDK_DPI_SCALE"))
    if gdk_scale is not None or gdk_dpi_scale is not None:
        scale = (gdk_scale or 1.0) * (gdk_dpi_scale or 1.0)
        if 0.5 <= scale <= 4.0:
            return scale

    qt_scale = _safe_float(os.environ.get("QT_SCALE_FACTOR"))
    if qt_scale is not None and 0.5 <= qt_scale <= 4.0:
        return qt_scale

    return None


def _detect_dpi_from_xrdb() -> Optional[float]:
    """
    X11 系で設定されることがある Xft.dpi を xrdb から読む。
    例: Xft.dpi: 144
    """
    try:
        out = subprocess.check_output(
            ["xrdb", "-query"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None

    m = re.search(r"Xft\.dpi:\s*([0-9.]+)", out)
    if not m:
        return None

    dpi = _safe_float(m.group(1))
    if dpi is None:
        return None
    if 50.0 <= dpi <= 400.0:
        return dpi
    return None


def configure_hidpi(root: tk.Tk) -> float:
    """
    Ubuntu(4K/150% 等)で Tkinter がスケールを拾い損ねるケースに備え、
    - UI スケール（96DPI=1.0 基準）を推定
    - tk scaling（px/point）を設定
    を行う。

    返り値:
        ui_scale: 96DPI=1.0 の相対スケール。150% なら 1.5。
    """
    # 手動上書き（必要なら環境変数で固定できるようにする）
    # 例: GIF_ANIMATOR_UI_SCALE=1.5
    override = _safe_float(os.environ.get("GIF_ANIMATOR_UI_SCALE"))
    if override is not None and 0.5 <= override <= 4.0:
        ui_scale = override
    else:
        ui_scale = _detect_ui_scale_from_env()
        if ui_scale is None:
            dpi = _detect_dpi_from_xrdb()
            if dpi is None:
                try:
                    dpi = float(root.winfo_fpixels("1i"))  # pixels per inch
                except tk.TclError:
                    dpi = 96.0
            ui_scale = dpi / 96.0

    ui_scale = max(0.75, min(ui_scale, 3.0))

    # Tk の scaling は「1 point(1/72 inch) あたり何ピクセルか」
    # 基準 96DPI の場合は 96/72 = 1.333...
    # 150% (=144DPI) なら 144/72 = 2.0
    tk_scaling = (96.0 / 72.0) * ui_scale
    try:
        root.tk.call("tk", "scaling", tk_scaling)
    except tk.TclError:
        # 環境によっては失敗することがあるため握りつぶす（UI は ui_scale 側でも調整する）
        pass

    return ui_scale


@dataclass
class GifEntry:
    path: Path
    mtime: float
    size: int


class GifAnimatorApp:
    FRAME_CACHE_LIMIT = 120
    MIN_FRAME_DELAY_MS = 30
    RESIZE_EPSILON_PX = 2
    SORT_OPTIONS = (
        "Name (A-Z)",
        "Name (Z-A)",
        "Time (Old-New)",
        "Time (New-Old)",
    )

    def __init__(self, root: tk.Tk, ui_scale: float = 1.0) -> None:
        self.root = root
        self.ui_scale = ui_scale

        # ピクセル固定値を UI スケールで扱うための補助
        def s(value: int | float) -> int:
            return max(1, int(round(value * self.ui_scale)))

        self.s = s  # helper をインスタンスに保持

        self.root.title("GIF Animator")
        self.root.geometry(f"{self.s(1200)}x{self.s(760)}")
        self.root.minsize(self.s(980), self.s(640))

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

        # リサイズ検出の閾値もスケールさせる（高 DPI で過敏になりすぎないように）
        self.resize_epsilon_px = max(2, self.s(self.RESIZE_EPSILON_PX))

        self._build_ui()
        self._bind_shortcuts()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        app_frame = ttk.Frame(self.root, padding=self.s(8))
        app_frame.grid(row=0, column=0, sticky="nsew")
        app_frame.columnconfigure(0, weight=0, minsize=self.s(340))
        app_frame.columnconfigure(1, weight=1)
        app_frame.rowconfigure(0, weight=1)

        self._build_sidebar(app_frame)
        self._build_viewer(app_frame)

        self.status_var = tk.StringVar(value="GIFファイルを開いてください")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        status.grid(row=1, column=0, sticky="ew", padx=self.s(8), pady=(0, self.s(8)))

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sidebar = ttk.LabelFrame(parent, text="Directory GIFs", padding=self.s(8))
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, self.s(8)))
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)

        open_btn = ttk.Button(sidebar, text="GIFを開く", command=self.select_gif_file)
        self._enable_press_to_activate(open_btn, self.select_gif_file)
        open_btn.grid(row=0, column=0, sticky="ew", pady=(0, self.s(8)))

        sort_row = ttk.Frame(sidebar)
        sort_row.grid(row=1, column=0, sticky="ew", pady=(0, self.s(8)))
        sort_row.columnconfigure(1, weight=1)
        ttk.Label(sort_row, text="並び替え").grid(row=0, column=0, sticky="w", padx=(0, self.s(6)))

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
        self.file_tree.column("name", width=self.s(170), anchor="w")
        self.file_tree.column("mtime", width=self.s(120), anchor="w")
        self.file_tree.column("size", width=self.s(70), anchor="e")
        self.file_tree.grid(row=2, column=0, sticky="nsew")
        self.file_tree.bind("<Double-1>", self._on_file_double_click)

        tree_scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=2, column=1, sticky="ns")

        nav_row = ttk.Frame(sidebar)
        nav_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(self.s(8), 0))
        nav_row.columnconfigure(0, weight=1)
        nav_row.columnconfigure(1, weight=1)

        prev_file_btn = ttk.Button(nav_row, text="Prev File", command=lambda: self.open_adjacent_file(-1))
        self._enable_press_to_activate(prev_file_btn, lambda: self.open_adjacent_file(-1))
        prev_file_btn.grid(row=0, column=0, sticky="ew", padx=(0, self.s(4)))
        next_file_btn = ttk.Button(nav_row, text="Next File", command=lambda: self.open_adjacent_file(1))
        self._enable_press_to_activate(next_file_btn, lambda: self.open_adjacent_file(1))
        next_file_btn.grid(row=0, column=1, sticky="ew", padx=(self.s(4), 0))

    def _build_viewer(self, parent: ttk.Frame) -> None:
        viewer = ttk.LabelFrame(parent, text="Preview", padding=self.s(8))
        viewer.grid(row=0, column=1, sticky="nsew")
        viewer.columnconfigure(0, weight=1)
        viewer.rowconfigure(0, weight=1)

        self.image_label = ttk.Label(viewer, anchor="center")
        self.image_label.grid(row=0, column=0, sticky="nsew")
        self.image_label.bind("<Configure>", self._on_preview_resize)

        controls = ttk.Frame(viewer)
        controls.grid(row=1, column=0, sticky="ew", pady=(self.s(8), 0))
        controls.columnconfigure(1, weight=1)

        playback_row = ttk.Frame(controls)
        playback_row.grid(row=0, column=0, columnspan=2, sticky="ew")

        self.play_btn = ttk.Button(playback_row, text="再生", command=self.play)
        self._enable_press_to_activate(self.play_btn, self.play)
        self.play_btn.grid(row=0, column=0, sticky="ew")

        self.pause_btn = ttk.Button(playback_row, text="停止", command=self.pause)
        self._enable_press_to_activate(self.pause_btn, self.pause)
        self.pause_btn.grid(row=0, column=1, sticky="ew", padx=(self.s(6), 0))

        prev_frame_btn = ttk.Button(playback_row, text="◀", width=4, command=lambda: self.step_frame(-1))
        self._enable_press_to_activate(prev_frame_btn, lambda: self.step_frame(-1))
        prev_frame_btn.grid(row=0, column=2, sticky="ew", padx=(self.s(12), 0))

        next_frame_btn = ttk.Button(playback_row, text="▶", width=4, command=lambda: self.step_frame(1))
        self._enable_press_to_activate(next_frame_btn, lambda: self.step_frame(1))
        next_frame_btn.grid(row=0, column=3, sticky="ew", padx=(self.s(6), 0))

        speed_frame = ttk.Frame(playback_row)
        speed_frame.grid(row=0, column=4, sticky="e", padx=(self.s(16), 0))
        ttk.Label(speed_frame, text="速度").grid(row=0, column=0, padx=(0, self.s(6)))
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
        self.frame_slider.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(self.s(8), self.s(2)))

        info_row = ttk.Frame(controls)
        info_row.grid(row=2, column=0, columnspan=2, sticky="ew")
        info_row.columnconfigure(0, weight=1)

        self.frame_info_var = tk.StringVar(value="Frame: - / -")
        ttk.Label(info_row, textvariable=self.frame_info_var).grid(row=0, column=0, sticky="w")

        save_frame_btn = ttk.Button(info_row, text="現在フレームを保存", command=self.save_current_frame)
        self._enable_press_to_activate(save_frame_btn, self.save_current_frame)
        save_frame_btn.grid(row=0, column=1, sticky="e")

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Left>", lambda _: self.step_frame(-1))
        self.root.bind("<Right>", lambda _: self.step_frame(1))
        self.root.bind("<space>", self._toggle_play_pause)

    def _enable_press_to_activate(self, button: ttk.Button, callback) -> None:
        # tkinter の標準ボタンは release 時に command 実行されるため、
        # 描画負荷が高い場面でも押下だけで反応するよう補助する。
        def on_press(event: tk.Event) -> str:
            if "disabled" in button.state():
                return "break"
            button.state(["pressed"])
            self.root.after_idle(callback)
            return "break"

        def on_release(_: tk.Event) -> str:
            button.state(["!pressed"])
            return "break"

        button.bind("<ButtonPress-1>", on_press, add="+")
        button.bind("<ButtonRelease-1>", on_release, add="+")
        button.bind("<Leave>", lambda _: button.state(["!pressed"]), add="+")

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
            return (self.s(640), self.s(480))
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
        if self.preview_size != (0, 0):
            width_delta = abs(new_size[0] - self.preview_size[0])
            height_delta = abs(new_size[1] - self.preview_size[1])
            if width_delta <= self.resize_epsilon_px and height_delta <= self.resize_epsilon_px:
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
        delay = max(self.MIN_FRAME_DELAY_MS, delay)
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

    ui_scale = configure_hidpi(root)
    ui_font_family = _select_ui_font_family(root)
    fixed_font_family = _select_fixed_font_family(root)
    apply_font_scaling(
        root,
        text_scale=ui_scale,
        ui_font_family=ui_font_family,
        fixed_font_family=fixed_font_family,
    )

    app = GifAnimatorApp(root, ui_scale=ui_scale)
    if app.current_file:
        app.load_gif(app.current_file)
    root.mainloop()


if __name__ == "__main__":
    main()
