"""Background workers for qBt Reclaim.

All heavy work runs off the GUI thread — including delete/move, which the
v1 tool ran on the main thread (freezing the window on large batches).

Conventions:
* Every worker's ``run()`` is decorated ``@pyqtSlot()``.
* The main window keeps workers alive in a ``_worker_refs`` set and
  releases them on ``finished`` — no premature garbage collection.
"""

from __future__ import annotations

import logging
import os
import time

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot

from .config import AppConfig
from .file_ops import FileOps, ScannedFile
from .qbt_client import QbtClient

log = logging.getLogger(__name__)


class ConnectWorker(QThread):
    """Probe the qBittorrent Web UI without blocking the GUI."""

    result = pyqtSignal(bool, str)  # connected, message (version or error)

    def __init__(self, client: QbtClient, parent=None) -> None:
        super().__init__(parent)
        self._client = client

    @pyqtSlot()
    def run(self) -> None:
        ok = self._client.connect()
        msg = self._client.version if ok else self._client.last_error
        self.result.emit(ok, msg)


class ScanWorker(QThread):
    """Scan the folder, fetch torrent claims, mark orphans."""

    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(list, int)   # list[ScannedFile], torrent_count
    failed = pyqtSignal(str)

    def __init__(self, client: QbtClient, cfg: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self._client = client
        self._cfg = cfg

    @pyqtSlot()
    def run(self) -> None:
        try:
            scan_root = self._cfg.scan_folder
            if not os.path.isdir(scan_root):
                self.failed.emit(
                    f"Scan folder does not exist:\n{scan_root}\n\n"
                    "Set the correct path in Settings → Scan folder.")
                return

            self.progress.emit("Fetching torrent inventory from qBittorrent…")
            claims = self._client.get_claims(self._cfg.ignore_extensions)

            self.progress.emit("Walking scan folder…")
            ops = FileOps(self._cfg.scan_folder)
            files = ops.scan()

            self.progress.emit(f"Cross-referencing {len(files)} files…")
            guard_cutoff = time.time() - self._cfg.age_guard_minutes * 60
            strip_exts = tuple(e.lower() for e in self._cfg.ignore_extensions)

            for f in files:
                base, rel = f.name, f.relative_path
                low = base.lower()
                for ext in strip_exts:
                    if low.endswith(ext):
                        base = base[: -len(ext)]
                        rel = rel[: -len(ext)]
                        break
                claimed = claims.claims_file(f.path, base, rel)
                f.guarded = (not claimed) and f.mtime > guard_cutoff
                f.is_orphan = (not claimed) and (not f.guarded)

            self.finished_ok.emit(files, claims.torrent_count)
        except ConnectionError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Scan worker crashed")
            self.failed.emit(f"Scan failed: {exc}")


class ActionWorker(QThread):
    """Delete or move a batch of files with per-file progress."""

    progress = pyqtSignal(int, int, str)          # done, total, current path
    finished_ok = pyqtSignal(int, list, int)      # ok_count, failures[(path, reason)], pruned_dirs

    def __init__(self, files: list[ScannedFile], cfg: AppConfig,
                 mode: str, force: bool, parent=None) -> None:
        super().__init__(parent)
        self._files = files
        self._cfg = cfg
        self._mode = mode  # "delete" | "move"
        self._force = force

    @pyqtSlot()
    def run(self) -> None:
        ops = FileOps(self._cfg.scan_folder)
        total = len(self._files)
        ok_count = 0
        failures: list[tuple[str, str]] = []

        for i, f in enumerate(self._files, start=1):
            self.progress.emit(i, total, f.relative_path)
            if self._mode == "move":
                ok, reason = ops.move(f.path, self._cfg.backup_folder, self._force)
            else:
                ok, reason = ops.delete(f.path, self._force, self._cfg.use_recycle_bin)
            if ok:
                ok_count += 1
            else:
                failures.append((f.path, reason))

        pruned = ops.prune_empty_dirs() if self._cfg.remove_empty_folders else 0
        self.finished_ok.emit(ok_count, failures, pruned)
