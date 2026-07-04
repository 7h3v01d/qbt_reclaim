"""qBt Reclaim — main window."""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QStatusBar, QTableView, QTabWidget,
    QVBoxLayout, QWidget,
)

from . import __app_name__, __author__, __github__, __version__
from .config import LOG_FILE, AppConfig
from .file_ops import HAS_TRASH, ScannedFile, human_size
from .models import COL_CHECK, FilesFilterProxy, FilesTableModel
from .qbt_client import QbtClient
from .theme import build_qss, tokens
from .workers import ActionWorker, ConnectWorker, ScanWorker

log = logging.getLogger(__name__)


# --------------------------------------------------------------- admin bits
def is_admin() -> bool:
    if os.name == "nt":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return False
    try:
        return os.getuid() == 0
    except AttributeError:
        return False


def relaunch_as_admin(parent: QWidget) -> None:
    if os.name != "nt":
        QMessageBox.information(
            parent, "Elevation",
            "Elevated relaunch is Windows-only. Run with sudo from a terminal instead.")
        return
    try:
        script = os.path.abspath(sys.argv[0])
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, "runas", sys.executable, f'"{script}" {params}', None, 1)
        QApplication.quit()
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(parent, "Elevation failed", f"Could not relaunch elevated:\n{exc}")


# ----------------------------------------------------------------- log pipe
class GuiLogHandler(logging.Handler, QObject):
    """Streams log records into the Log tab, thread-safe via signal."""

    record_ready = pyqtSignal(str)

    def __init__(self) -> None:
        logging.Handler.__init__(self, level=logging.INFO)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s",
                                            datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.record_ready.emit(self.format(record))
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------ preview dialog
class PreviewDialog(QDialog):
    """Dry-run: show exactly what is about to happen before doing it."""

    def __init__(self, files: list[ScannedFile], mode: str, dest: str,
                 force: bool, use_trash: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm reclaim")
        self.setMinimumSize(640, 420)
        layout = QVBoxLayout(self)

        total = sum(f.size for f in files)
        verb = "MOVE" if mode == "move" else ("TRASH" if use_trash else "DELETE")
        header = QLabel(
            f"{verb}  //  {len(files)} file(s)  //  {human_size(total)}"
            + (f"\nDestination: {dest}" if mode == "move" else "")
            + ("\nForce mode: read-only attributes will be cleared." if force else "")
        )
        header.setProperty("class", "dim")
        layout.addWidget(header)

        listing = QPlainTextEdit()
        listing.setObjectName("logView")
        listing.setReadOnly(True)
        listing.setPlainText("\n".join(
            f"[{human_size(f.size):>10}]  {f.relative_path}" for f in files))
        layout.addWidget(listing, 1)

        warn = QLabel("Deletion is permanent unless recycle bin mode is on. Review the list.")
        warn.setProperty("class", "faint")
        layout.addWidget(warn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(f"{verb.title()} files")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = AppConfig.load()
        self.client = QbtClient()
        self._worker_refs: set[object] = set()
        self._admin = is_admin()

        self.setWindowTitle(f"{__app_name__} v{__version__} — {__github__}")
        self.resize(1180, 760)

        self._build_ui()
        self._attach_log_handler()
        self.apply_theme(self.cfg.theme)
        self._configure_client()
        self._probe_connection()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        root.addWidget(self._build_header())
        root.addWidget(self._build_stats_strip())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_reclaim_tab(), "RECLAIM")
        self.tabs.addTab(self._build_settings_tab(), "SETTINGS")
        self.tabs.addTab(self._build_log_tab(), "LOG")
        root.addWidget(self.tabs, 1)

        status = QStatusBar()
        self.setStatusBar(status)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.hide()
        status.addPermanentWidget(self.progress)
        status.showMessage("Ready.")

    def _build_header(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("headerBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 8, 14, 8)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("QBT // RECLAIM")
        title.setObjectName("appTitle")
        subtitle = QLabel("ORPHAN FILE CONSOLE")
        subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        lay.addLayout(title_box)
        lay.addStretch(1)

        self.conn_label = QLabel("● OFFLINE")
        self.conn_label.setToolTip("qBittorrent Web UI connection")
        lay.addWidget(self.conn_label)

        self.test_button = QPushButton("Test connection")
        self.test_button.clicked.connect(self._probe_connection)
        lay.addWidget(self.test_button)

        self.admin_label = QLabel("ELEVATED" if self._admin else "STANDARD")
        self.admin_label.setProperty("class", "faint")
        self.admin_label.setToolTip("Process privilege level")
        lay.addWidget(self.admin_label)

        if os.name == "nt" and not self._admin:
            elevate = QPushButton("Run as admin")
            elevate.clicked.connect(lambda: relaunch_as_admin(self))
            lay.addWidget(elevate)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["obsidian", "phosphor"])
        self.theme_combo.setCurrentText(self.cfg.theme)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        lay.addWidget(self.theme_combo)
        return bar

    def _build_stats_strip(self) -> QFrame:
        strip = QFrame()
        strip.setObjectName("panel")
        lay = QHBoxLayout(strip)
        lay.setContentsMargins(14, 6, 14, 6)

        def stat(label: str, warn: bool = False) -> QLabel:
            box = QVBoxLayout()
            box.setSpacing(0)
            value = QLabel("—")
            value.setProperty("class", "statValueWarn" if warn else "statValue")
            caption = QLabel(label)
            caption.setProperty("class", "statLabel")
            box.addWidget(value)
            box.addWidget(caption)
            lay.addLayout(box)
            lay.addSpacing(30)
            return value

        self.stat_files = stat("FILES SCANNED")
        self.stat_torrents = stat("ACTIVE TORRENTS")
        self.stat_orphans = stat("ORPHANS", warn=True)
        self.stat_reclaimable = stat("RECLAIMABLE", warn=True)
        self.stat_selected = stat("SELECTED")
        lay.addStretch(1)
        return strip

    def _build_reclaim_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # toolbar row
        bar = QHBoxLayout()
        self.scan_button = QPushButton("Scan folder")
        self.scan_button.setObjectName("primary")
        self.scan_button.clicked.connect(self.start_scan)
        bar.addWidget(self.scan_button)

        self.select_orphans_button = QPushButton("Select orphans")
        self.select_orphans_button.clicked.connect(lambda: self._bulk_select(orphans_only=True))
        bar.addWidget(self.select_orphans_button)

        self.select_all_button = QPushButton("Select visible")
        self.select_all_button.clicked.connect(lambda: self._bulk_select(orphans_only=False))
        bar.addWidget(self.select_all_button)

        self.clear_button = QPushButton("Clear selection")
        self.clear_button.clicked.connect(self._clear_selection)
        bar.addWidget(self.clear_button)

        bar.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("filter files…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(240)
        self.search_edit.textChanged.connect(lambda t: self.proxy.set_search(t))
        bar.addWidget(self.search_edit)

        self.orphans_only_check = QCheckBox("Orphans only")
        self.orphans_only_check.toggled.connect(self.proxy_orphans_toggled)
        bar.addWidget(self.orphans_only_check)
        lay.addLayout(bar)

        # table
        self.model = FilesTableModel(tokens(self.cfg.theme))
        self.proxy = FilesFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.model.dataChanged.connect(lambda *_: self._refresh_selected_stat())

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.clicked.connect(self._on_table_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        lay.addWidget(self.table, 1)

        # action row
        actions = QHBoxLayout()
        self.move_check = QCheckBox("Move to backup instead of delete")
        actions.addWidget(self.move_check)
        self.force_check = QCheckBox("Force (clear read-only)")
        actions.addWidget(self.force_check)
        actions.addStretch(1)
        self.reclaim_button = QPushButton("Reclaim selected…")
        self.reclaim_button.setObjectName("danger")
        self.reclaim_button.setEnabled(False)
        self.reclaim_button.clicked.connect(self.start_reclaim)
        actions.addWidget(self.reclaim_button)
        lay.addLayout(actions)
        return page

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(12)

        # connection group
        conn_group = QGroupBox("QBITTORRENT WEB UI")
        form = QFormLayout(conn_group)
        self.host_edit = QLineEdit(self.cfg.qb_host)
        form.addRow("Host", self.host_edit)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.cfg.qb_port)
        form.addRow("Port", self.port_spin)
        self.user_edit = QLineEdit(self.cfg.qb_username)
        form.addRow("Username", self.user_edit)
        self.pass_edit = QLineEdit(self.cfg.qb_password)
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password", self.pass_edit)
        outer.addWidget(conn_group)

        # folders group
        folder_group = QGroupBox("FOLDERS")
        folder_form = QFormLayout(folder_group)
        self.scan_edit, scan_row = self._folder_row(self.cfg.scan_folder)
        folder_form.addRow("Scan folder", scan_row)
        self.backup_edit, backup_row = self._folder_row(self.cfg.backup_folder)
        folder_form.addRow("Backup folder", backup_row)
        outer.addWidget(folder_group)

        # safety group
        safety_group = QGroupBox("SAFETY")
        safety_form = QFormLayout(safety_group)
        self.trash_check = QCheckBox("Send deletions to recycle bin (send2trash)")
        self.trash_check.setChecked(self.cfg.use_recycle_bin and HAS_TRASH)
        self.trash_check.setEnabled(HAS_TRASH)
        if not HAS_TRASH:
            self.trash_check.setToolTip("Install the 'send2trash' package to enable.")
        safety_form.addRow(self.trash_check)
        self.prune_check = QCheckBox("Remove empty subfolders after reclaim")
        self.prune_check.setChecked(self.cfg.remove_empty_folders)
        safety_form.addRow(self.prune_check)
        self.age_spin = QSpinBox()
        self.age_spin.setRange(0, 1440)
        self.age_spin.setSuffix(" min")
        self.age_spin.setValue(self.cfg.age_guard_minutes)
        self.age_spin.setToolTip(
            "Files modified more recently than this are never flagged as orphans —\n"
            "protects downloads that started after the torrent list was fetched.")
        safety_form.addRow("Age guard", self.age_spin)
        outer.addWidget(safety_group)

        save_button = QPushButton("Save settings + reconnect")
        save_button.setObjectName("primary")
        save_button.clicked.connect(self.save_settings)
        outer.addWidget(save_button, alignment=Qt.AlignmentFlag.AlignLeft)

        outer.addStretch(1)
        about = QLabel(
            f"{__app_name__} v{__version__}  //  {__author__} ({__github__})  //  Apache 2.0"
            f"\nConfig: ~/.qbt_reclaim/config.json   Log: {LOG_FILE.name}")
        about.setProperty("class", "faint")
        outer.addWidget(about)
        return page

    def _folder_row(self, initial: str) -> tuple[QLineEdit, QWidget]:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(initial)
        browse = QPushButton("…")
        browse.setFixedWidth(34)
        browse.clicked.connect(lambda: self._browse_into(edit))
        lay.addWidget(edit, 1)
        lay.addWidget(browse)
        return edit, row

    def _browse_into(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose folder", edit.text())
        if path:
            edit.setText(path)

    def _build_log_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        lay.addWidget(self.log_view)
        return page

    def _attach_log_handler(self) -> None:
        self._gui_log = GuiLogHandler()
        self._gui_log.record_ready.connect(self.log_view.appendPlainText)
        logging.getLogger().addHandler(self._gui_log)

    # --------------------------------------------------------------- theme
    def apply_theme(self, theme: str) -> None:
        self.cfg.theme = theme
        QApplication.instance().setStyleSheet(build_qss(theme))
        t = tokens(theme)
        self.model.set_theme(t)
        self._set_conn_indicator(self.client.connected, self.client.version or "offline")

    def _on_theme_changed(self, theme: str) -> None:
        self.apply_theme(theme)
        self.cfg.save()

    # ---------------------------------------------------------- connection
    def _configure_client(self) -> None:
        self.client.configure(
            self.cfg.qb_host, self.cfg.qb_port,
            self.cfg.qb_username, self.cfg.qb_password,
            self.cfg.qb_verify_tls)

    def _probe_connection(self) -> None:
        self.test_button.setEnabled(False)
        self.statusBar().showMessage("Probing qBittorrent Web UI…")
        worker = ConnectWorker(self.client)
        worker.result.connect(self._on_probe_result)
        self._track(worker)
        worker.start()

    def _on_probe_result(self, ok: bool, message: str) -> None:
        self.test_button.setEnabled(True)
        self._set_conn_indicator(ok, message)
        self.statusBar().showMessage(
            f"Connected — qBittorrent {message}" if ok else f"Connection failed: {message}", 8000)

    def _set_conn_indicator(self, ok: bool, message: str) -> None:
        t = tokens(self.cfg.theme)
        colour = t["ok"] if ok else t["danger"]
        label = f"● ONLINE {message}" if ok else "● OFFLINE"
        self.conn_label.setText(label)
        self.conn_label.setStyleSheet(f"color: {colour}; font-weight: 700;")
        self.conn_label.setToolTip(message)

    # ---------------------------------------------------------------- scan
    def start_scan(self) -> None:
        self._set_busy(True, "Scanning…")
        worker = ScanWorker(self.client, self.cfg)
        worker.progress.connect(lambda msg: self.statusBar().showMessage(msg))
        worker.finished_ok.connect(self._on_scan_done)
        worker.failed.connect(self._on_scan_failed)
        self._track(worker)
        worker.start()

    def _on_scan_done(self, files: list, torrent_count: int) -> None:
        self._set_busy(False)
        self.model.replace(files)
        orphans = [f for f in files if f.is_orphan]
        reclaimable = sum(f.size for f in orphans)
        self.stat_files.setText(str(len(files)))
        self.stat_torrents.setText(str(torrent_count))
        self.stat_orphans.setText(str(len(orphans)))
        self.stat_reclaimable.setText(human_size(reclaimable))
        self._refresh_selected_stat()
        self._set_conn_indicator(True, self.client.version)
        self.statusBar().showMessage(
            f"Scan complete — {len(files)} files, {len(orphans)} orphans, "
            f"{human_size(reclaimable)} reclaimable.", 10000)

        locked = [f for f in files if f.status == "Locked/Admin"]
        if locked and not self._admin and os.name == "nt":
            self.statusBar().showMessage(
                f"Scan complete — note: {len(locked)} file(s) need elevation to modify.", 12000)

    def _on_scan_failed(self, message: str) -> None:
        self._set_busy(False)
        self._set_conn_indicator(self.client.connected, message)
        QMessageBox.warning(self, "Scan failed", message)
        self.statusBar().showMessage(f"Scan failed: {message}", 10000)

    # ----------------------------------------------------------- selection
    def _on_table_clicked(self, proxy_index) -> None:
        if proxy_index.column() != COL_CHECK:
            return  # checkbox handles its own toggling via CheckStateRole

    def _visible_source_rows(self) -> list[int]:
        rows = []
        for proxy_row in range(self.proxy.rowCount()):
            src = self.proxy.mapToSource(self.proxy.index(proxy_row, 0))
            rows.append(src.row())
        return rows

    def _bulk_select(self, orphans_only: bool) -> None:
        rows = self._visible_source_rows()
        if orphans_only:
            rows = [r for r in rows if self.model.file_at(r).is_orphan]
        self.model.set_selected_rows(rows, True)
        self._refresh_selected_stat()

    def _clear_selection(self) -> None:
        all_rows = list(range(len(self.model.all_files())))
        self.model.set_selected_rows(all_rows, False)
        self._refresh_selected_stat()

    def _refresh_selected_stat(self) -> None:
        selected = self.model.selected_files()
        total = sum(f.size for f in selected)
        self.stat_selected.setText(
            f"{len(selected)} / {human_size(total)}" if selected else "—")
        self.reclaim_button.setEnabled(bool(selected))

    def proxy_orphans_toggled(self, checked: bool) -> None:
        self.proxy.set_orphans_only(checked)

    def _show_context_menu(self, pos) -> None:
        proxy_index = self.table.indexAt(pos)
        if not proxy_index.isValid():
            return
        src = self.proxy.mapToSource(proxy_index)
        f = self.model.file_at(src.row())
        menu = QMenu(self)
        open_action = QAction("Open containing folder", menu)
        open_action.triggered.connect(lambda: self._open_folder(f.path))
        copy_action = QAction("Copy full path", menu)
        copy_action.triggered.connect(
            lambda: QApplication.clipboard().setText(f.path))
        menu.addAction(open_action)
        menu.addAction(copy_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    @staticmethod
    def _open_folder(path: str) -> None:
        folder = os.path.dirname(path)
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", path])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except OSError as exc:
            log.error("Could not open folder %s: %s", folder, exc)

    # -------------------------------------------------------------- reclaim
    def start_reclaim(self) -> None:
        selected = self.model.selected_files()
        if not selected:
            return
        mode = "move" if self.move_check.isChecked() else "delete"
        force = self.force_check.isChecked()
        use_trash = self.cfg.use_recycle_bin and HAS_TRASH and mode == "delete"

        dialog = PreviewDialog(selected, mode, self.cfg.backup_folder,
                               force, use_trash, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._set_busy(True, "Reclaiming…", determinate=len(selected))
        worker = ActionWorker(selected, self.cfg, mode, force)
        worker.progress.connect(self._on_action_progress)
        worker.finished_ok.connect(self._on_action_done)
        self._track(worker)
        worker.start()

    def _on_action_progress(self, done: int, total: int, current: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.statusBar().showMessage(f"[{done}/{total}] {current}")

    def _on_action_done(self, ok_count: int, failures: list, pruned: int) -> None:
        self._set_busy(False)
        msg = f"Reclaimed {ok_count} file(s)."
        if pruned:
            msg += f" Removed {pruned} empty folder(s)."
        if failures:
            msg += f" {len(failures)} failed."
            details = "\n".join(f"{path}\n    → {reason}" for path, reason in failures)
            QMessageBox.warning(self, "Some files could not be reclaimed", details)
        self.statusBar().showMessage(msg, 10000)
        self.start_scan()  # refresh the view

    # -------------------------------------------------------------- settings
    def save_settings(self) -> None:
        self.cfg.qb_host = self.host_edit.text().strip()
        self.cfg.qb_port = self.port_spin.value()
        self.cfg.qb_username = self.user_edit.text()
        self.cfg.qb_password = self.pass_edit.text()
        self.cfg.scan_folder = self.scan_edit.text().strip()
        self.cfg.backup_folder = self.backup_edit.text().strip()
        self.cfg.use_recycle_bin = self.trash_check.isChecked()
        self.cfg.remove_empty_folders = self.prune_check.isChecked()
        self.cfg.age_guard_minutes = self.age_spin.value()
        self.cfg.theme = self.theme_combo.currentText()
        self.cfg.save()
        self._configure_client()
        self._probe_connection()
        self.statusBar().showMessage("Settings saved.", 6000)

    # -------------------------------------------------------------- plumbing
    def _track(self, worker) -> None:
        """Keep a strong reference until the thread finishes (GC safety)."""
        self._worker_refs.add(worker)
        worker.finished.connect(lambda w=worker: self._worker_refs.discard(w))

    def _set_busy(self, busy: bool, message: str = "", determinate: int = 0) -> None:
        for widget in (self.scan_button, self.reclaim_button,
                       self.select_orphans_button, self.select_all_button,
                       self.clear_button):
            widget.setEnabled(not busy)
        if busy:
            self.progress.show()
            if determinate:
                self.progress.setRange(0, determinate)
                self.progress.setValue(0)
            else:
                self.progress.setRange(0, 0)  # marquee
            if message:
                self.statusBar().showMessage(message)
        else:
            self.progress.hide()
            self._refresh_selected_stat()

    def closeEvent(self, event) -> None:
        logging.getLogger().removeHandler(self._gui_log)
        for worker in list(self._worker_refs):
            worker.wait(3000)
        super().closeEvent(event)


# ---------------------------------------------------------------- launcher
def run() -> int:
    from .config import CONFIG_DIR
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    font = QFont("JetBrains Mono", 10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    return app.exec()
