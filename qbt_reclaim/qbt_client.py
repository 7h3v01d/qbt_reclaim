"""qBittorrent Web API client for qBt Reclaim.

Uses ``qbittorrent-api`` (the maintained library) — the v1 tool declared it
in requirements but actually imported the abandoned ``python-qbittorrent``
package, and referenced ``os.path`` without importing ``os``. Both fixed.

The key export is :meth:`QbtClient.get_claims`, which returns the set of
filesystem paths qBittorrent currently *claims* — every file of every
torrent, resolved against its save path and content path. Orphan detection
is then exact path/name matching instead of fuzzy string scoring.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import qbittorrentapi

log = logging.getLogger(__name__)


def norm(path: str) -> str:
    """Normalise a path for cross-platform comparison."""
    return os.path.normcase(os.path.normpath(path))


@dataclass
class TorrentClaims:
    """Everything qBittorrent says it owns on disk."""

    paths: set[str] = field(default_factory=set)       # absolute file paths
    dir_prefixes: set[str] = field(default_factory=set)  # content dirs of multi-file torrents
    names: set[str] = field(default_factory=set)       # basenames + relative paths (fallback)
    torrent_count: int = 0

    def claims_file(self, abs_path: str, basename: str, rel_path: str) -> bool:
        p = norm(abs_path)
        if p in self.paths:
            return True
        for prefix in self.dir_prefixes:
            if p.startswith(prefix + os.sep):
                return True
        n = os.path.normcase(basename)
        if n in self.names or os.path.normcase(rel_path) in self.names:
            return True
        return False


class QbtClient:
    """Thin, reconnect-friendly wrapper over qbittorrentapi.Client."""

    def __init__(self) -> None:
        self._client: qbittorrentapi.Client | None = None
        self.connected: bool = False
        self.version: str = ""
        self.last_error: str = ""

    def configure(self, host: str, port: int, username: str, password: str,
                  verify_tls: bool = True) -> None:
        self._client = qbittorrentapi.Client(
            host=host,
            port=port,
            username=username or None,
            password=password or None,
            VERIFY_WEBUI_CERTIFICATE=verify_tls,
            REQUESTS_ARGS={"timeout": (4, 15)},
        )
        self.connected = False
        self.version = ""
        self.last_error = ""

    def connect(self) -> bool:
        if self._client is None:
            self.last_error = "Client not configured."
            return False
        try:
            self._client.auth_log_in()
            self.version = str(self._client.app.version)
            self.connected = True
            self.last_error = ""
            log.info("Connected to qBittorrent %s", self.version)
            return True
        except qbittorrentapi.LoginFailed:
            self.last_error = "Login failed — check username/password."
        except qbittorrentapi.APIConnectionError as exc:
            self.last_error = f"Cannot reach Web UI: {exc}"
        except Exception as exc:  # noqa: BLE001 — surface anything to the UI
            self.last_error = f"Unexpected error: {exc}"
        self.connected = False
        log.error("qBittorrent connection failed: %s", self.last_error)
        return False

    # ------------------------------------------------------------- claims
    def get_claims(self, ignore_extensions: list[str] | None = None) -> TorrentClaims:
        """Build the claim set from every torrent in every state."""
        claims = TorrentClaims()
        if self._client is None or (not self.connected and not self.connect()):
            raise ConnectionError(self.last_error or "Not connected to qBittorrent.")

        strip_exts = tuple(e.lower() for e in (ignore_extensions or []))

        def add_name(name: str) -> None:
            n = os.path.normcase(name)
            claims.names.add(n)
            low = n.lower()
            for ext in strip_exts:
                if low.endswith(ext):
                    claims.names.add(n[: -len(ext)])

        torrents = self._client.torrents_info()
        claims.torrent_count = len(torrents)
        for t in torrents:
            add_name(t.name)
            save_path = t.save_path or ""
            content_path = getattr(t, "content_path", "") or ""
            if content_path:
                cp = norm(content_path)
                claims.paths.add(cp)
                if os.path.isdir(content_path):
                    claims.dir_prefixes.add(cp)
            try:
                for f in t.files:
                    rel = f.name  # relative to save_path, may contain subdirs
                    add_name(rel)
                    add_name(os.path.basename(rel))
                    if save_path:
                        claims.paths.add(norm(os.path.join(save_path, rel)))
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not list files for torrent '%s': %s", t.name, exc)

        log.info(
            "Claims built: %d torrents, %d paths, %d dir prefixes, %d names",
            claims.torrent_count, len(claims.paths),
            len(claims.dir_prefixes), len(claims.names),
        )
        return claims
