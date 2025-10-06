"""Treemap visualisation helpers."""
from __future__ import annotations

import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import matplotlib as mpl
import matplotlib.cm as cm
from matplotlib.axes import Axes
from matplotlib.colorbar import Colorbar
from matplotlib.offsetbox import AnchoredText
from matplotlib.patches import Rectangle
import squarify

from .scanner import FileInfo


@dataclass
class TreemapItem:
    path: Optional[str]
    label: str
    size: int
    age_seconds: Optional[float]
    is_aggregate: bool = False


def format_bytes(num: int) -> str:
    """Return a human readable representation of ``num`` bytes."""

    if num <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = min(int(math.log(num, 1024)), len(units) - 1)
    scaled = num / (1024 ** idx)
    return f"{scaled:.1f} {units[idx]}"


class TreemapVisualizer:
    """Render treemaps inside a Matplotlib ``Axes``."""

    def __init__(self, ax: Axes, *, on_path_selected: Optional[Callable[[str], None]] = None) -> None:
        self.ax = ax
        self.on_path_selected = on_path_selected
        self.figure = ax.figure
        self._patch_metadata: Dict[Rectangle, TreemapItem] = {}
        self._annotation = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="white", ec="0.5", alpha=0.9),
            arrowprops=dict(arrowstyle="->"),
        )
        self._annotation.set_visible(False)
        self._theme = "light"
        self._colorbar: Optional[Colorbar] = None
        self._size_legend: Optional[AnchoredText] = None
        canvas = self.figure.canvas
        canvas.mpl_connect("motion_notify_event", self._on_move)
        canvas.mpl_connect("button_press_event", self._on_click)

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        bg = "#121212" if theme == "dark" else "#ffffff"
        fg = "#f0f0f0" if theme == "dark" else "#222222"
        self.ax.set_facecolor(bg)
        self.figure.set_facecolor(bg)
        self._annotation.get_bbox_patch().set_facecolor("#333333" if theme == "dark" else "#ffffff")
        self._annotation.get_bbox_patch().set_edgecolor("#eeeeee" if theme == "dark" else "#666666")
        self._annotation.set_color(fg)
        if self._colorbar is not None:
            if self._colorbar.outline is not None:
                self._colorbar.outline.set_edgecolor(fg)
            self._colorbar.ax.yaxis.label.set_color(fg)
            self._colorbar.ax.tick_params(colors=fg)
            for spine in self._colorbar.ax.spines.values():
                spine.set_edgecolor(fg)
        if self._size_legend is not None:
            self._size_legend.txt.set_color(fg)
        self.figure.canvas.draw_idle()

    def draw(self, items: Iterable[TreemapItem]) -> None:
        self.ax.clear()
        if self._colorbar is not None:
            self._colorbar.remove()
            self._colorbar = None
        self._size_legend = None
        items_list = [item for item in items if item.size > 0]
        if not items_list:
            self.ax.text(
                0.5,
                0.5,
                "No files match the current filters",
                ha="center",
                va="center",
                color="#f0f0f0" if self._theme == "dark" else "#333333",
                transform=self.ax.transAxes,
            )
            self.ax.set_axis_off()
            self.figure.canvas.draw_idle()
            return

        sizes = [item.size for item in items_list]
        norm_area = squarify.normalize_sizes(sizes, 100, 100)
        rects = squarify.squarify(norm_area, 0, 0, 100, 100)

        ages = [item.age_seconds for item in items_list if item.age_seconds is not None]
        ages_days = [age / 86400 for age in ages]
        max_age_days = max(ages_days) if ages_days else 1
        norm = mpl.colors.Normalize(vmin=0, vmax=max_age_days)
        cmap_name = "viridis" if self._theme == "light" else "plasma"
        cmap_obj = cm.get_cmap(cmap_name)

        self._patch_metadata.clear()
        self.ax.set_axis_off()

        for rect, item in zip(rects, items_list):
            color = "#555555"
            if item.age_seconds is not None:
                color = cmap_obj(norm((item.age_seconds or 0) / 86400))
            patch = Rectangle((rect["x"], rect["y"]), rect["dx"], rect["dy"], facecolor=color, edgecolor="#202020", linewidth=0.5)
            self.ax.add_patch(patch)
            self._patch_metadata[patch] = item

            area = rect["dx"] * rect["dy"]
            label = item.label if not item.is_aggregate else f"{item.label}\n{format_bytes(item.size)}"
            if area > 30:
                self.ax.text(
                    rect["x"] + rect["dx"] / 2,
                    rect["y"] + rect["dy"] / 2,
                    label,
                    ha="center",
                    va="center",
                    color="#f8f8f8" if self._theme == "dark" else "#111111",
                    fontsize=8,
                )

        self.ax.set_xlim(0, 100)
        self.ax.set_ylim(0, 100)
        self.ax.invert_yaxis()

        if ages_days:
            scalar_mappable = cm.ScalarMappable(norm=norm, cmap=cmap_obj)
            scalar_mappable.set_array([])
            self._colorbar = self.figure.colorbar(scalar_mappable, ax=self.ax, fraction=0.046, pad=0.02)
            label_color = "#f0f0f0" if self._theme == "dark" else "#222222"
            self._colorbar.set_label("File age (days)", color=label_color)
            tick_labels = self._colorbar.get_ticks()
            self._colorbar.set_ticks(tick_labels)
            self._colorbar.ax.tick_params(colors=label_color)
            for spine in self._colorbar.ax.spines.values():
                spine.set_edgecolor(label_color)

        legend_text_color = "#f0f0f0" if self._theme == "dark" else "#222222"
        self._size_legend = AnchoredText(
            "Area ∝ file size",
            loc="lower left",
            prop=dict(color=legend_text_color, size=9),
            frameon=False,
            pad=0.3,
        )
        self.ax.add_artist(self._size_legend)

        self.figure.canvas.draw_idle()

    def _find_patch(self, event) -> Optional[Rectangle]:
        if event.inaxes != self.ax:
            return None
        for patch in self._patch_metadata:
            contains, _ = patch.contains(event)
            if contains:
                return patch
        return None

    def _on_move(self, event) -> None:
        patch = self._find_patch(event)
        if not patch:
            if self._annotation.get_visible():
                self._annotation.set_visible(False)
                self.figure.canvas.draw_idle()
            return
        item = self._patch_metadata.get(patch)
        if not item:
            return
        tooltip = self._format_tooltip(item)
        self._annotation.xy = (event.xdata, event.ydata)
        self._annotation.set_text(tooltip)
        self._annotation.set_visible(True)
        self.figure.canvas.draw_idle()

    def _on_click(self, event) -> None:
        if event.button != 1:
            return
        patch = self._find_patch(event)
        if not patch:
            return
        item = self._patch_metadata.get(patch)
        if not item or not item.path or item.is_aggregate:
            return
        if self.on_path_selected:
            self.on_path_selected(item.path)

    def _format_tooltip(self, item: TreemapItem) -> str:
        parts = [item.label]
        parts.append(format_bytes(item.size))
        if item.age_seconds is not None:
            age_days = item.age_seconds / 86400
            parts.append(f"Age: {age_days:.1f} days")
        if item.path:
            parts.append(item.path)
        return "\n".join(parts)


def build_treemap_items(
    files: List[FileInfo],
    base_path: Path,
    *,
    max_items: int = 400,
) -> List[TreemapItem]:
    """Convert ``FileInfo`` records into ``TreemapItem`` entries."""

    now = time.time()
    prepared: List[TreemapItem] = []

    for file_info in files:
        rel = os.path.relpath(file_info.path, base_path)
        label = rel.replace(os.sep, "\n") if len(rel) < 40 else os.path.basename(file_info.path)
        prepared.append(
            TreemapItem(
                path=file_info.path,
                label=label,
                size=file_info.size,
                age_seconds=max(0.0, now - file_info.modified) if file_info.modified else None,
            )
        )

    prepared.sort(key=lambda item: item.size, reverse=True)
    if len(prepared) <= max_items:
        return prepared

    top_items = prepared[: max_items - 1]
    other_size = sum(item.size for item in prepared[max_items - 1 :])
    top_items.append(
        TreemapItem(
            path=None,
            label="Other",
            size=other_size,
            age_seconds=None,
            is_aggregate=True,
        )
    )
    return top_items


def open_path_in_explorer(path: str) -> None:
    """Open ``path`` in the platform specific file explorer."""

    target = Path(path)
    if not target.exists():
        return

    try:
        target_str = str(target)
        if sys.platform.startswith("win"):
            if target.is_dir():
                os.startfile(target_str)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["explorer", f'/select,"{target_str}"'])
        elif sys.platform == "darwin":
            if target.is_dir():
                subprocess.Popen(["open", target_str])
            else:
                subprocess.Popen(["open", "-R", target_str])
        else:
            directory = target if target.is_dir() else target.parent
            subprocess.Popen(["xdg-open", str(directory)])
    except Exception:
        # The UI layer handles error reporting if needed.
        pass
