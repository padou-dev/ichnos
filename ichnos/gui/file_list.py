# SPDX-License-Identifier: GPL-3.0-or-later
"""The list of open files. A ticked file is included when copies are written."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QMenu

from ichnos.metadata import FileMetadata
from ichnos.presets import has_location

PATH_ROLE = Qt.ItemDataRole.UserRole
THUMB_SIZE = QSize(48, 36)


class FileList(QListWidget):
    focused = Signal(object)  # Path or None
    selection_changed = Signal()
    remove_requested = Signal(object)  # list of Paths

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setIconSize(THUMB_SIZE)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSpacing(2)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)  # long names: "screen…_08.png"
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.currentItemChanged.connect(self._on_current_changed)
        self.itemChanged.connect(lambda _item: self.selection_changed.emit())
        self._items: dict[Path, QListWidgetItem] = {}

    def add(self, meta: FileMetadata, thumbnail: QImage | None) -> None:
        if meta.path in self._items:
            return
        self.blockSignals(True)  # the caller refreshes once after adding
        try:
            self._add(meta, thumbnail)
        finally:
            self.blockSignals(False)

    def _add(self, meta: FileMetadata, thumbnail: QImage | None) -> None:
        item = QListWidgetItem(self)
        item.setData(PATH_ROLE, meta.path)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        item.setCheckState(Qt.CheckState.Checked)
        if thumbnail is not None and not thumbnail.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(thumbnail)))
        self._items[meta.path] = item
        self.update_details(meta)

    def update_details(self, meta: FileMetadata) -> None:
        item = self._items.get(meta.path)
        if item is None:
            return
        count = len(meta.removable)
        details = f"{count} removable tag{'s' if count != 1 else ''}"
        if has_location(meta):
            details = "has location · " + details
        item.setText(f"{meta.path.name}\n{details}")
        item.setToolTip(str(meta.path))

    def remove(self, paths: list[Path]) -> None:
        for path in paths:
            item = self._items.pop(path, None)
            if item is not None:
                self.takeItem(self.row(item))

    def paths(self) -> list[Path]:
        return [self.item(i).data(PATH_ROLE) for i in range(self.count())]

    def checked_paths(self) -> list[Path]:
        return [
            self.item(i).data(PATH_ROLE)
            for i in range(self.count())
            if self.item(i).checkState() == Qt.CheckState.Checked
        ]

    def set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.blockSignals(True)
        for i in range(self.count()):
            self.item(i).setCheckState(state)
        self.blockSignals(False)
        self.selection_changed.emit()

    def focus_path(self, path: Path) -> None:
        item = self._items.get(path)
        if item is not None:
            self.setCurrentItem(item)

    def selected_paths(self) -> list[Path]:
        return [item.data(PATH_ROLE) for item in self.selectedItems()]

    def _on_current_changed(self, current: QListWidgetItem | None, _previous) -> None:
        self.focused.emit(current.data(PATH_ROLE) if current is not None else None)

    def _context_menu(self, position) -> None:
        if not self.selectedItems():
            return
        menu = QMenu(self)
        action = menu.addAction("Remove from list")
        action.triggered.connect(lambda: self.remove_requested.emit(self.selected_paths()))
        menu.exec(self.viewport().mapToGlobal(position))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selectedItems():
            self.remove_requested.emit(self.selected_paths())
            return
        super().keyPressEvent(event)
