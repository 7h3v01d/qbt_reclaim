# qBt Reclaim

**Orphan file console for qBittorrent.** Scans your incomplete / in-progress download folder, cross-references every file against the torrents qBittorrent actually knows about, and lets you reclaim the dead weight — safely.

Dark industrial PyQt6 rewrite of the original cleanup tool. Two themes: **obsidian** (navy / teal / amber) and **phosphor** (near-black / green).

> Author: Leon Priest ([7h3v01d](https://github.com/7h3v01d)) · Apache 2.0

---

## What it does

1. Connects to the qBittorrent Web UI and builds a **claim set**: every file path of every torrent in every state, resolved against save paths and content paths.
2. Walks your scan folder and marks anything the claim set doesn't cover as an **orphan** — exact path and name matching, no fuzzy string scoring.
3. Lets you review, filter, sort, and select, then **delete** (recycle bin by default) or **move to a backup folder** — with a dry-run preview of exactly what will happen before anything is touched.

## Safety features

| Feature | Detail |
|---|---|
| Recycle bin | Deletions go through `send2trash` when installed (on by default) |
| Age guard | Files modified in the last *N* minutes are never flagged (shown as `fresh`) — protects downloads added after the torrent list was fetched |
| Dry-run preview | Full file listing with sizes shown before any action executes |
| Incomplete extensions | `.!qB` / `.parts` suffixes are stripped before matching, so in-flight qBittorrent files are correctly recognised as claimed |
| Collision-safe moves | Backups never overwrite — name clashes get a timestamp suffix |
| Cross-drive moves | Uses `shutil.move`, so backing up to another volume just works |

## Install & run

```bash
pip install -r requirements.txt
python main.py          # or: python -m qbt_reclaim
```

Requires Python 3.10+ and a qBittorrent instance with the **Web UI enabled** (Options → Web UI). Set host / port / credentials in the Settings tab; config lives at `~/.qbt_reclaim/config.json` and a legacy `user_config.json` from the old tool is migrated automatically on first run.

> **Note:** credentials are stored in plaintext JSON (owner-readable on POSIX). Use a dedicated qBittorrent Web UI account, or enable "Bypass authentication for clients on localhost" in qBittorrent and leave the credentials blank.

## Fixed from v1

- Imported the abandoned `python-qbittorrent` package while declaring `qbittorrent-api` in requirements — now genuinely on `qbittorrent-api`.
- `NameError` on multi-file torrents (`os` used without import in the API module).
- Fuzzy-name orphan detection (fuzzywuzzy `partial_ratio`) replaced with exact path/claim matching — no more false positives from short torrent names.
- Delete/move ran on the GUI thread and froze the window on large batches — now on a worker thread with per-file progress.
- Saving settings rewrote the JSON but never updated the live client — reconnection used stale values. Config is now a dataclass passed explicitly; saves take effect immediately.
- `os.rename` for backups failed across drives (`EXDEV`) and silently overwrote name collisions.
- Writability probe opened files in append mode (bumping mtime on some filesystems) — now uses `os.access` + the Windows read-only attribute.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
