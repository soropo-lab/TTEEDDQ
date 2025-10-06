"""Application entry point for the Folder Map Visualizer."""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from . import scanner
from .scanner import FileInfo
from .treemap import TreemapVisualizer, build_treemap_items, format_bytes, open_path_in_explorer


class FolderMapApp:
    """Tkinter based GUI for exploring folder treemaps."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Folder Map Visualizer")
        self.root.geometry("1200x800")

        self.style = ttk.Style(self.root)
        self.dark_mode = tk.BooleanVar(value=False)

        self.current_directory = tk.StringVar()
        self.status_var = tk.StringVar(value="Select a folder to begin.")
        self.summary_var = tk.StringVar(value="No data loaded yet.")
        self.min_size_var = tk.StringVar(value="0")
        self.extensions_var = tk.StringVar()
        self.max_age_var = tk.StringVar()  # in days
        self.max_items_var = tk.StringVar(value="400")
        self.sort_mode = tk.StringVar(value="Size (desc)")

        self._scan_thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._scan_generation = 0
        self._active_generation = 0
        self._scan_start_time: Optional[float] = None
        self._progress_queue: "queue.Queue[Tuple[str, int, object]]" = queue.Queue()
        self._files: List[FileInfo] = []
        self._filtered_files: List[FileInfo] = []

        self._build_ui()
        self.apply_theme()
        self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        container = ttk.Frame(self.root, padding=10)
        container.grid(row=0, column=0, sticky="nsew")
        container.rowconfigure(2, weight=1)
        container.columnconfigure(0, weight=1)
        self._container = container

        # Folder selection row
        path_frame = ttk.Frame(container)
        path_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        path_frame.columnconfigure(1, weight=1)

        ttk.Label(path_frame, text="Selected folder:").grid(row=0, column=0, sticky="w")
        path_entry = ttk.Entry(path_frame, textvariable=self.current_directory, state="readonly")
        path_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(path_frame, text="Browse…", command=self.select_folder).grid(row=0, column=2)
        ttk.Button(path_frame, text="Export image", command=self.export_image).grid(row=0, column=3, padx=(5, 0))
        ttk.Checkbutton(path_frame, text="Dark mode", variable=self.dark_mode, command=self.apply_theme).grid(row=0, column=4, padx=(10, 0))

        # Summary
        summary_label = ttk.Label(container, textvariable=self.summary_var)
        summary_label.grid(row=1, column=0, sticky="w", pady=(0, 10))
        self._summary_label = summary_label

        # Filter section
        filter_frame = ttk.LabelFrame(container, text="Filters & options")
        filter_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        filter_frame.columnconfigure(6, weight=1)

        ttk.Label(filter_frame, text="Min size (MB)").grid(row=0, column=0, sticky="w")
        min_size_entry = ttk.Entry(filter_frame, width=10, textvariable=self.min_size_var)
        min_size_entry.grid(row=0, column=1, sticky="w", padx=(0, 10))
        min_size_entry.bind("<Return>", lambda _: self.refresh_visualization())
        min_size_entry.bind("<FocusOut>", lambda _: self.refresh_visualization())

        ttk.Label(filter_frame, text="Extensions (.py,.txt)").grid(row=0, column=2, sticky="w")
        ext_entry = ttk.Entry(filter_frame, width=20, textvariable=self.extensions_var)
        ext_entry.grid(row=0, column=3, sticky="w", padx=(0, 10))
        ext_entry.bind("<Return>", lambda _: self.refresh_visualization())
        ext_entry.bind("<FocusOut>", lambda _: self.refresh_visualization())

        ttk.Label(filter_frame, text="Max age (days)").grid(row=0, column=4, sticky="w")
        age_entry = ttk.Entry(filter_frame, width=10, textvariable=self.max_age_var)
        age_entry.grid(row=0, column=5, sticky="w", padx=(0, 10))
        age_entry.bind("<Return>", lambda _: self.refresh_visualization())
        age_entry.bind("<FocusOut>", lambda _: self.refresh_visualization())

        ttk.Label(filter_frame, text="Max rectangles").grid(row=0, column=6, sticky="w")
        max_items_entry = ttk.Entry(filter_frame, width=10, textvariable=self.max_items_var)
        max_items_entry.grid(row=0, column=7, sticky="w", padx=(0, 10))
        max_items_entry.bind("<Return>", lambda _: self.refresh_visualization())
        max_items_entry.bind("<FocusOut>", lambda _: self.refresh_visualization())

        ttk.Label(filter_frame, text="Sort by").grid(row=0, column=8, sticky="w")
        sort_box = ttk.Combobox(
            filter_frame,
            width=15,
            state="readonly",
            textvariable=self.sort_mode,
            values=(
                "Size (desc)",
                "Size (asc)",
                "Name (A-Z)",
                "Modified (newest)",
                "Modified (oldest)",
            ),
        )
        sort_box.grid(row=0, column=9, sticky="w")
        sort_box.bind("<<ComboboxSelected>>", lambda _: self.refresh_visualization())

        ttk.Button(filter_frame, text="Apply", command=self.refresh_visualization).grid(row=0, column=10, padx=(10, 0))

        # Plot frame
        plot_frame = ttk.Frame(container)
        plot_frame.grid(row=3, column=0, sticky="nsew")
        plot_frame.rowconfigure(1, weight=1)
        plot_frame.columnconfigure(0, weight=1)

        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.visualizer = TreemapVisualizer(self.ax, on_path_selected=self.open_path)
        canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.grid(row=1, column=0, sticky="nsew")
        toolbar = NavigationToolbar2Tk(canvas, plot_frame)
        toolbar.update()
        toolbar.pack_forget()
        toolbar.grid(row=0, column=0, sticky="w")
        self._canvas = canvas

        status_bar = ttk.Label(container, textvariable=self.status_var, anchor="w")
        status_bar.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self._status_bar = status_bar

    # ------------------------------------------------------------------
    # Scanning logic
    # ------------------------------------------------------------------
    def select_folder(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            self.current_directory.set(folder)
            self.start_scan(folder)

    def start_scan(self, folder: str) -> None:
        if self._stop_event:
            self._stop_event.set()
        self._scan_generation += 1
        generation = self._scan_generation
        self._active_generation = generation
        self._files = []
        self._filtered_files = []
        self.summary_var.set("Scanning in progress…")
        self.status_var.set("Scanning…")
        self._scan_start_time = time.time()

        def on_progress(count: int, total_bytes: int, last_path: Optional[str]) -> None:
            self._progress_queue.put(("progress", generation, (count, total_bytes, last_path)))

        def on_finish(result: List[FileInfo], error: Optional[BaseException]) -> None:
            self._progress_queue.put(("finish", generation, (result, error)))

        thread, stop_event = scanner.start_scan_in_thread(
            folder,
            on_finish,
            on_progress=on_progress,
        )
        self._scan_thread = thread
        self._stop_event = stop_event

    def _poll_queue(self) -> None:
        try:
            while True:
                message, generation, payload = self._progress_queue.get_nowait()
                if generation != self._active_generation:
                    continue
                if message == "progress":
                    count, total_bytes, last_path = payload
                    preview = Path(last_path).name if last_path else ""
                    self.status_var.set(
                        f"Scanning… {count} files, {format_bytes(total_bytes)} processed. {preview}"
                    )
                elif message == "finish":
                    files, error = payload
                    if error:
                        messagebox.showerror("Scan failed", str(error))
                        self.status_var.set("Scan failed.")
                    else:
                        duration = 0.0
                        if self._scan_start_time:
                            duration = time.time() - self._scan_start_time
                        self._files = files
                        self.status_var.set(
                            f"Scan complete: {len(files)} files, duration {duration:.1f}s."
                        )
                        self.refresh_visualization()
                    self._scan_start_time = None
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # Filtering & visualisation
    # ------------------------------------------------------------------
    def refresh_visualization(self) -> None:
        if not self.current_directory.get():
            return
        directory = Path(self.current_directory.get())
        self._filtered_files = self._apply_filters()
        max_items = self._parse_int(self.max_items_var.get(), default=400, minimum=50)
        treemap_items = build_treemap_items(self._filtered_files, directory, max_items=max_items)
        self.visualizer.draw(treemap_items)
        self._canvas.draw_idle()
        self._update_summary()

    def _apply_filters(self) -> List[FileInfo]:
        files = list(self._files)
        if not files:
            return []
        min_size_mb = self._parse_float(self.min_size_var.get(), default=0.0, minimum=0.0)
        min_size_bytes = int(min_size_mb * 1024 * 1024)
        extensions = [ext.strip().lower() for ext in self.extensions_var.get().split(",") if ext.strip()]
        extensions = [ext if ext.startswith(".") else f".{ext}" for ext in extensions]
        max_age_days = self._parse_float(self.max_age_var.get(), default=None, minimum=0.0)

        filtered: List[FileInfo] = []
        now = time.time()
        for info in files:
            if info.size < min_size_bytes:
                continue
            if extensions:
                if Path(info.path).suffix.lower() not in extensions:
                    continue
            if max_age_days is not None:
                age_days = (now - info.modified) / 86400
                if age_days > max_age_days:
                    continue
            filtered.append(info)

        mode = self.sort_mode.get()
        if mode == "Size (asc)":
            filtered.sort(key=lambda item: item.size)
        elif mode == "Name (A-Z)":
            filtered.sort(key=lambda item: item.name.lower())
        elif mode == "Modified (newest)":
            filtered.sort(key=lambda item: item.modified, reverse=True)
        elif mode == "Modified (oldest)":
            filtered.sort(key=lambda item: item.modified)
        else:
            filtered.sort(key=lambda item: item.size, reverse=True)
        return filtered

    def _update_summary(self) -> None:
        total_size = sum(info.size for info in self._files)
        filtered_size = sum(info.size for info in self._filtered_files)
        summary = [
            f"Files: {len(self._filtered_files)} / {len(self._files)}",
            f"Size: {format_bytes(filtered_size)} / {format_bytes(total_size)}",
        ]
        if self._files:
            newest = max(self._files, key=lambda info: info.modified)
            oldest = min(self._files, key=lambda info: info.modified)
            summary.append(
                f"Newest: {newest.name}"
            )
            summary.append(
                f"Oldest: {oldest.name}"
            )
        self.summary_var.set(" | ".join(summary))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def apply_theme(self) -> None:
        theme = "dark" if self.dark_mode.get() else "light"
        if theme == "dark":
            self.style.theme_use("clam")
            background = "#1f1f1f"
            foreground = "#f0f0f0"
            field_bg = "#2a2a2a"
        else:
            self.style.theme_use("default")
            background = "#ffffff"
            foreground = "#202020"
            field_bg = "#ffffff"
        self.root.configure(bg=background)
        for widget in (self._container, self._summary_label, self._status_bar):
            widget.configure(style="")
        self.style.configure("TFrame", background=background)
        self.style.configure("TLabel", background=background, foreground=foreground)
        self.style.configure("TLabelFrame", background=background, foreground=foreground)
        self.style.configure("TLabelFrame.Label", background=background, foreground=foreground)
        self.style.configure("TCheckbutton", background=background, foreground=foreground)
        self.style.configure("TEntry", fieldbackground=field_bg, foreground=foreground)
        self.style.configure("TCombobox", fieldbackground=field_bg, foreground=foreground)
        self.visualizer.set_theme(theme)
        self._canvas.draw_idle()

    def export_image(self) -> None:
        if not self.current_directory.get():
            messagebox.showinfo("Export", "Scan a directory before exporting.")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("SVG", "*.svg"), ("PDF", "*.pdf")],
        )
        if not file_path:
            return
        try:
            self.figure.savefig(file_path)
            messagebox.showinfo("Export", f"Treemap saved to {file_path}")
        except Exception as exc:  # pragma: no cover - GUI error reporting
            messagebox.showerror("Export failed", str(exc))

    def open_path(self, path: str) -> None:
        try:
            open_path_in_explorer(path)
        except Exception as exc:  # pragma: no cover - GUI error reporting
            messagebox.showerror("Open failed", str(exc))

    def _parse_float(self, value: str, *, default: Optional[float], minimum: float) -> Optional[float]:
        if not value:
            return default
        try:
            result = float(value)
        except ValueError:
            return default
        return max(result, minimum)

    def _parse_int(self, value: str, *, default: int, minimum: int) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return default
        return max(result, minimum)


def main() -> None:
    root = tk.Tk()
    app = FolderMapApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
