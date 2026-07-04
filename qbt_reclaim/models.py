"""Table model and filter proxy for the file grid."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt,
)
from PyQt6.QtGui import QColor

from .file_ops import (
    STATUS_LOCKED, STATUS_READONLY, STATUS_WRITABLE,
    ScannedFile, human_size,
)

COL_CHECK, COL_FILE, COL_SIZE, COL_MODIFIED, COL_STATUS, COL_ORPHAN = range(6)
HEADERS = ["", "FILE", "SIZE", "MODIFIED", "STATUS", "ORPHAN"]
RAW_ROLE = Qt.ItemDataRole.UserRole + 1


class FilesTableModel(QAbstractTableModel):
    def __init__(self, theme_tokens: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._files: list[ScannedFile] = []
        self.set_theme(theme_tokens)

    def set_theme(self, t: dict[str, str]) -> None:
        self._c_warn = QColor(t["warn"])
        self._c_danger = QColor(t["danger"])
        self._c_ok = QColor(t["ok"])
        self._c_dim = QColor(t["fg_dim"])

    # -------------------------------------------------------------- basics
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._files)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == COL_CHECK:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    # ---------------------------------------------------------------- data
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        f = self._files[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_FILE:
                return f.relative_path
            if col == COL_SIZE:
                return human_size(f.size)
            if col == COL_MODIFIED:
                return datetime.fromtimestamp(f.mtime).strftime("%Y-%m-%d %H:%M")
            if col == COL_STATUS:
                return f.status
            if col == COL_ORPHAN:
                if f.is_orphan:
                    return "ORPHAN"
                return "fresh" if f.guarded else "claimed"

        elif role == Qt.ItemDataRole.CheckStateRole and col == COL_CHECK:
            return Qt.CheckState.Checked if f.selected else Qt.CheckState.Unchecked

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == COL_STATUS:
                if f.status == STATUS_WRITABLE:
                    return self._c_ok
                if f.status == STATUS_READONLY:
                    return self._c_warn
                if f.status == STATUS_LOCKED:
                    return self._c_danger
            if col == COL_ORPHAN:
                return self._c_warn if f.is_orphan else self._c_dim

        elif role == Qt.ItemDataRole.ToolTipRole and col == COL_FILE:
            return f.path

        elif role == RAW_ROLE:  # raw values so the proxy sorts correctly
            if col == COL_SIZE:
                return f.size
            if col == COL_MODIFIED:
                return f.mtime
            if col == COL_ORPHAN:
                return int(f.is_orphan)
            if col == COL_CHECK:
                return int(f.selected)
            if col == COL_FILE:
                return f.relative_path.lower()
            if col == COL_STATUS:
                return f.status

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if index.isValid() and role == Qt.ItemDataRole.CheckStateRole and index.column() == COL_CHECK:
            checked = Qt.CheckState(value) == Qt.CheckState.Checked
            self._files[index.row()].selected = checked
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            return True
        return False

    # ------------------------------------------------------------- helpers
    def replace(self, files: list[ScannedFile]) -> None:
        self.beginResetModel()
        self._files = files
        self.endResetModel()

    def all_files(self) -> list[ScannedFile]:
        return self._files

    def selected_files(self) -> list[ScannedFile]:
        return [f for f in self._files if f.selected]

    def file_at(self, row: int) -> ScannedFile:
        return self._files[row]

    def set_selected_rows(self, rows: list[int], selected: bool) -> None:
        for row in rows:
            self._files[row].selected = selected
        if rows:
            top = self.index(min(rows), COL_CHECK)
            bottom = self.index(max(rows), COL_CHECK)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.CheckStateRole])


class FilesFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._search = ""
        self._orphans_only = False
        self.setSortRole(RAW_ROLE)

    def set_search(self, text: str) -> None:
        self._search = text.lower().strip()
        self.invalidateFilter()

    def set_orphans_only(self, enabled: bool) -> None:
        self._orphans_only = enabled
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model: FilesTableModel = self.sourceModel()  # type: ignore[assignment]
        f = model.file_at(source_row)
        if self._orphans_only and not f.is_orphan:
            return False
        if self._search and self._search not in f.relative_path.lower():
            return False
        return True
