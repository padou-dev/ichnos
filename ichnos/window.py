# SPDX-License-Identifier: GPL-3.0-or-later
"""The main application window."""

import subprocess
from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
)

from ichnos.metadata import read_tags


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ichnos")
        self.resize(900, 600)

        self.tag_tree = QTreeWidget()
        self.tag_tree.setHeaderLabels(["Tag", "Value"])
        self.setCentralWidget(self.tag_tree)

        open_action = QAction("&Open…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.choose_file)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(open_action)

    def choose_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open image",
            str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.heic *.heif *.webp *.tif *.tiff "
            "*.dng *.cr2 *.cr3 *.nef *.arw);;All files (*)",
        )
        if filename:
            self.open_file(Path(filename))

    def open_file(self, path: Path) -> None:
        try:
            tags = read_tags(path)
        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "exiftool not found",
                "Ichnos needs exiftool to read metadata, but it isn't installed "
                "or isn't on your PATH.",
            )
            return
        except subprocess.CalledProcessError as error:
            QMessageBox.critical(
                self,
                "Could not read file",
                f"Ichnos couldn't read {path.name}.\n\n{error.stderr.strip()}",
            )
            return

        self.tag_tree.clear()
        self.setWindowTitle(f"{path.name} — Ichnos")

        groups: dict[str, QTreeWidgetItem] = {}
        for key, value in tags.items():
            if ":" not in key:
                continue
            group, name = key.split(":", 1)
            if group not in groups:
                groups[group] = QTreeWidgetItem(self.tag_tree, [group])
            QTreeWidgetItem(groups[group], [name, str(value)])

        self.tag_tree.expandAll()
        self.tag_tree.resizeColumnToContents(0)