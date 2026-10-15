# SPDX-License-Identifier: GPL-3.0-or-later
"""The main application window."""

from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QTreeWidget, QTreeWidgetItem

from ichnos.metadata import read_tags


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ichnos")
        self.resize(900, 600)

        self.tag_tree = QTreeWidget()
        self.tag_tree.setHeaderLabels(["Tag", "Value"])
        self.setCentralWidget(self.tag_tree)

    def open_file(self, path: Path) -> None:
        tags = read_tags(path)
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