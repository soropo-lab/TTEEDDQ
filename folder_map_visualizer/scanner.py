"""Background directory scanning utilities."""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple


@dataclass(frozen=True)
class FileInfo:
    """Represents metadata about a file on disk."""

    path: str
    size: int
    modified: float

    @property
    def modified_time(self) -> time.struct_time:
        """Return the file modification time as ``time.struct_time``."""
        return time.localtime(self.modified)

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


ProgressCallback = Callable[[int, int, Optional[str]], None]
FinishCallback = Callable[[List[FileInfo], Optional[BaseException]], None]


def _iter_file_info(
    root: Path,
    stop_event: Optional[threading.Event] = None,
    follow_symlinks: bool = False,
) -> Iterator[FileInfo]:
    """Yield :class:`FileInfo` objects for every file inside ``root``.

    The implementation uses :func:`os.scandir` to minimise stat calls and keeps
    the UI responsive by honouring the optional ``stop_event``.
    """

    stack: List[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if stop_event and stop_event.is_set():
                        return
                    try:
                        if entry.is_dir(follow_symlinks=follow_symlinks):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=follow_symlinks):
                            stat = entry.stat(follow_symlinks=follow_symlinks)
                            yield FileInfo(
                                path=entry.path,
                                size=stat.st_size,
                                modified=stat.st_mtime,
                            )
                    except (FileNotFoundError, PermissionError, OSError):
                        continue
        except (FileNotFoundError, PermissionError, OSError):
            continue


def scan_directory(
    root_path: str,
    *,
    on_progress: Optional[ProgressCallback] = None,
    stop_event: Optional[threading.Event] = None,
    chunk_size: int = 200,
    follow_symlinks: bool = False,
) -> List[FileInfo]:
    """Scan ``root_path`` and return file metadata.

    ``on_progress`` is invoked after each chunk of files is processed with
    ``(file_count, total_bytes, last_path)``.

    Set ``follow_symlinks`` to ``True`` to traverse symbolic links.
    """

    root = Path(root_path).expanduser().resolve()
    files: List[FileInfo] = []
    total_bytes = 0

    chunk: List[FileInfo] = []
    for info in _iter_file_info(root, stop_event=stop_event, follow_symlinks=follow_symlinks):
        files.append(info)
        chunk.append(info)
        total_bytes += info.size
        if on_progress and len(chunk) >= chunk_size:
            on_progress(len(files), total_bytes, chunk[-1].path if chunk else None)
            chunk.clear()
    if on_progress and chunk:
        on_progress(len(files), total_bytes, chunk[-1].path if chunk else None)
    return files


def start_scan_in_thread(
    root_path: str,
    on_finish: FinishCallback,
    *,
    on_progress: Optional[ProgressCallback] = None,
    chunk_size: int = 200,
    follow_symlinks: bool = False,
) -> Tuple[threading.Thread, threading.Event]:
    """Start a background scan and return the worker thread and stop event."""

    stop_event = threading.Event()

    def worker() -> None:
        error: Optional[BaseException] = None
        result: List[FileInfo] = []
        try:
            result = scan_directory(
                root_path,
                on_progress=on_progress,
                stop_event=stop_event,
                chunk_size=chunk_size,
                follow_symlinks=follow_symlinks,
            )
        except BaseException as exc:  # pylint: disable=broad-except
            error = exc
        on_finish(result, error)

    thread = threading.Thread(target=worker, name="FolderScanner", daemon=True)
    thread.start()
    return thread, stop_event
