"""Configuration for qBt Reclaim.

Stored at ``~/.qbt_reclaim/config.json``. Values are held in a dataclass
that is passed around explicitly — no module-level globals, so saving
settings actually takes effect everywhere immediately (a bug in the v1
tool: it rewrote the JSON but every consumer kept the stale globals).

Migration: if a legacy ``user_config.json`` from the old cleanup tool is
found in the working directory, its values are imported on first run.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".qbt_reclaim"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "reclaim.log"
LEGACY_CONFIG = Path("user_config.json")


@dataclass
class AppConfig:
    # qBittorrent Web UI
    qb_host: str = "localhost"
    qb_port: int = 8080
    qb_username: str = ""
    qb_password: str = ""
    qb_verify_tls: bool = True

    # folders
    scan_folder: str = str(Path.home() / "Downloads" / "In_Progress")
    backup_folder: str = str(Path.home() / "Downloads" / "Reclaim_Backup")

    # behaviour
    theme: str = "obsidian"            # obsidian | phosphor
    use_recycle_bin: bool = True       # send2trash when deleting (if available)
    remove_empty_folders: bool = True
    age_guard_minutes: int = 10        # never flag files newer than this as orphans
    ignore_extensions: list[str] = field(
        default_factory=lambda: [".!qB", ".parts"]
    )

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls()
        if CONFIG_FILE.exists():
            cfg._apply_file(CONFIG_FILE)
        elif LEGACY_CONFIG.exists():
            cfg._apply_legacy(LEGACY_CONFIG)
            cfg.save()
            log.info("Migrated legacy user_config.json -> %s", CONFIG_FILE)
        return cfg

    def _apply_file(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Could not read config %s: %s — using defaults", path, exc)
            return
        valid = {f.name for f in dataclasses.fields(self)}
        for key, value in data.items():
            if key in valid:
                setattr(self, key, value)

    def _apply_legacy(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Could not read legacy config: %s", exc)
            return
        mapping = {
            "QB_HOST": "qb_host",
            "QB_PORT": "qb_port",
            "QB_USERNAME": "qb_username",
            "QB_PASSWORD": "qb_password",
            "IN_PROGRESS_FOLDER": "scan_folder",
            "BACKUP_FOLDER": "backup_folder",
        }
        for old_key, new_key in mapping.items():
            if old_key in data:
                setattr(self, new_key, data[old_key])
        # don't carry over placeholder credentials
        if self.qb_username == "your_qb_username":
            self.qb_username = ""
        if self.qb_password == "your_qb_password":
            self.qb_password = ""

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(dataclasses.asdict(self), indent=2)
        CONFIG_FILE.write_text(payload, encoding="utf-8")
        # best effort: keep credentials owner-readable on POSIX
        if os.name == "posix":
            try:
                os.chmod(CONFIG_FILE, 0o600)
            except OSError:
                pass
        log.info("Config saved -> %s", CONFIG_FILE)
