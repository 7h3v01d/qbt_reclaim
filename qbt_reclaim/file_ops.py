"""Filesystem operations for qBt Reclaim.

Improvements over the v1 tool:

* ``shutil.move`` instead of ``os.rename`` — moves across drives work
  (rename fails with EXDEV between volumes, e.g. H:\\ -> C:\\).
* Move never silently overwrites: name collisions in the backup folder
  get a numeric suffix.
* Optional recycle-bin deletion via ``send2trash`` when installed.
* Permission probing no longer opens files in append mode just to test
  writability (which bumps mtime on some filesystems); it uses
  ``os.access`` plus the Windows read-only attribute.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from send2trash import send2trash
    HAS_TRASH = True
except ImportError:  # pragma: no cover
    HAS_TRASH = False

STATUS_WRITABLE = "Writable"
STATUS_READONLY = "Read-Only"
STATUS_LOCKED = "Locked/Admin"
STATUS_ERROR = "Error"


@dataclass
class ScannedFile:
    path: str
    relative_path: str
    name: str
    size: int
    mtime: float
    status: str
    is_orphan: bool = False
    guarded: bool = False  # too recently modified to be safely flagged
    selected: bool = False


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(num_bytes)} {unit}"
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TB"


def file_status(path: str) -> str:
    """Classify a file's writability without touching its contents."""
    try:
        if os.name == "nt":
            attrs = os.stat(path).st_file_attributes  # type: ignore[attr-defined]
            if attrs & stat.FILE_ATTRIBUTE_READONLY:  # type: ignore[attr-defined]
                return STATUS_READONLY
        if os.access(path, os.W_OK):
            return STATUS_WRITABLE
        return STATUS_LOCKED
    except OSError as exc:
        log.warning("Status check failed for %s: %s", path, exc)
        return STATUS_ERROR


class FileOps:
    def __init__(self, scan_folder: str) -> None:
        self.scan_folder = scan_folder

    # ------------------------------------------------------------ scanning
    def scan(self) -> list[ScannedFile]:
        results: list[ScannedFile] = []
        root_path = Path(self.scan_folder)
        if not root_path.is_dir():
            log.warning("Scan folder does not exist: %s", self.scan_folder)
            return results

        for root, _dirs, files in os.walk(self.scan_folder):
            for filename in files:
                full = os.path.join(root, filename)
                try:
                    st = os.stat(full)
                    results.append(ScannedFile(
                        path=full,
                        relative_path=os.path.relpath(full, self.scan_folder),
                        name=filename,
                        size=st.st_size,
                        mtime=st.st_mtime,
                        status=file_status(full),
                    ))
                except OSError as exc:
                    log.error("Could not stat %s: %s", full, exc)
        return results

    # ------------------------------------------------------------- actions
    @staticmethod
    def _make_writable(path: str) -> None:
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        except OSError as exc:
            log.debug("chmod failed for %s: %s", path, exc)

    def delete(self, path: str, force: bool = False, use_trash: bool = False) -> tuple[bool, str]:
        try:
            if force:
                self._make_writable(path)
            if use_trash and HAS_TRASH:
                send2trash(path)
                log.info("Sent to recycle bin: %s", path)
            else:
                os.remove(path)
                log.info("Deleted: %s", path)
            return True, ""
        except OSError as exc:
            reason = self._explain(exc)
            log.error("Delete failed for %s: %s", path, reason)
            return False, reason
        except Exception as exc:  # noqa: BLE001 — send2trash raises its own types
            log.error("Delete failed for %s: %s", path, exc)
            return False, str(exc)

    def move(self, path: str, dest_folder: str, force: bool = False) -> tuple[bool, str]:
        try:
            if force:
                self._make_writable(path)
            os.makedirs(dest_folder, exist_ok=True)
            dest = self._unique_dest(dest_folder, os.path.basename(path))
            shutil.move(path, dest)
            log.info("Moved: %s -> %s", path, dest)
            return True, ""
        except OSError as exc:
            reason = self._explain(exc)
            log.error("Move failed for %s: %s", path, reason)
            return False, reason

    @staticmethod
    def _unique_dest(folder: str, name: str) -> str:
        dest = os.path.join(folder, name)
        if not os.path.exists(dest):
            return dest
        stem, ext = os.path.splitext(name)
        suffix = int(time.time())
        candidate = os.path.join(folder, f"{stem}.{suffix}{ext}")
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(folder, f"{stem}.{suffix}.{counter}{ext}")
            counter += 1
        return candidate

    @staticmethod
    def _explain(exc: OSError) -> str:
        winerr = getattr(exc, "winerror", None)
        if winerr == 32:
            return "File is locked by another process."
        if winerr == 5 or exc.errno == 13:
            return "Access denied — may need admin rights or Force mode."
        return str(exc)

    # -------------------------------------------------------- housekeeping
    def prune_empty_dirs(self) -> int:
        """Remove empty subfolders under the scan folder (never the root)."""
        removed = 0
        root = os.path.abspath(self.scan_folder)
        if not os.path.isdir(root):
            return 0
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            if os.path.abspath(dirpath) == root:
                continue
            if not dirnames and not filenames:
                try:
                    os.rmdir(dirpath)
                    removed += 1
                    log.info("Removed empty folder: %s", dirpath)
                except OSError as exc:
                    log.warning("Could not remove folder %s: %s", dirpath, exc)
        return removed
