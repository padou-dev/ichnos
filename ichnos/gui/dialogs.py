# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialogs: review changes before writing, and results after."""

from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ichnos import __version__
from ichnos.exiftool import IchnosError, exiftool_version
from ichnos.metadata import FileMetadata
from ichnos.writer import FilePlan, WriteResult


class ReviewDialog(QDialog):
    """Lists every change, file by file. Accepting means 'write the copies'."""

    def __init__(
        self, items: list[tuple[FileMetadata, FilePlan]], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review changes")
        self.resize(720, 520)
        layout = QVBoxLayout(self)

        changing = [(meta, plan) for meta, plan in items if not plan.is_empty]
        intro = QLabel(
            f"{len(changing)} of {len(items)} ticked files will get a cleaned copy. "
            "Originals are not modified."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        tree = QTreeWidget()
        tree.setHeaderLabels(["Change", "Tag", "Reason / new value"])
        tree.setColumnWidth(0, 220)
        tree.setColumnWidth(1, 240)
        for meta, plan in items:
            removed = [t for t in meta.removable if t.removal_target in plan.removals]
            if plan.is_empty:
                QTreeWidgetItem(tree, [meta.path.name, "", "nothing to change, skipped"])
                continue
            summary = f"{len(removed)} removed"
            if plan.edits:
                summary += f", {len(plan.edits)} edited"
            top = QTreeWidgetItem(tree, [meta.path.name, "", summary])
            for tag in removed:
                QTreeWidgetItem(top, ["remove", tag.key, plan.removals[tag.removal_target].value])
            for (group, name), value in plan.edits.items():
                QTreeWidgetItem(top, ["edit", f"{group}:{name}", " ".join(value.split())])
        layout.addWidget(tree)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        write = QPushButton(f"Write {len(changing)} cop{'y' if len(changing) == 1 else 'ies'}")
        write.setObjectName("primary")
        write.setEnabled(bool(changing))
        buttons.addButton(write, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ResultsDialog(QDialog):
    """What happened after writing. Problems are shown first, never hidden."""

    def __init__(
        self,
        results: list[WriteResult],
        failures: dict[Path, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.inspect_requested = False
        self.setWindowTitle("Copies written")
        self.resize(640, 420)
        layout = QVBoxLayout(self)

        clean = [r for r in results if r.verified]
        partial = [r for r in results if not r.verified]
        headline = (
            f"<h3>{len(clean)} cop{'y' if len(clean) == 1 else 'ies'} written and verified</h3>"
        )
        if partial or failures:
            headline += (
                f"<p><b>{len(partial) + len(failures)} need attention.</b> "
                "Their details are listed first.</p>"
            )
        layout.addWidget(QLabel(headline))

        rows: list[str] = []
        for path, message in failures.items():
            rows.append(f"<p>✗ <b>{escape(path.name)}</b>: not written.<br>{escape(message)}</p>")
        for result in partial:
            problems = "<br>".join(escape(p) for p in result.leftovers)
            rows.append(
                f"<p>⚠ <b>{escape(result.source.name)}</b> → {escape(result.destination.name)}: "
                f"written, but not everything could be changed:<br>{problems}</p>"
            )
        for result in clean:
            extra = f", {result.edited} edited" if result.edited else ""
            rows.append(
                f"<p>✓ {escape(result.source.name)} → <b>{escape(result.destination.name)}</b>"
                f" ({result.removed} removed{extra})</p>"
            )
        browser = QTextBrowser()
        browser.setHtml("".join(rows))
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        if results:
            folder = results[0].destination.parent
            open_folder = buttons.addButton("Open folder", QDialogButtonBox.ButtonRole.ActionRole)
            open_folder.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
            )
            inspect = buttons.addButton("Inspect copies", QDialogButtonBox.ButtonRole.AcceptRole)
            inspect.setToolTip("Open the cleaned copies in Ichnos to check them yourself")
            inspect.clicked.connect(self._inspect)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _inspect(self) -> None:
        self.inspect_requested = True
        self.accept()


def show_about(parent: QWidget) -> None:
    try:
        exiftool = f"exiftool {exiftool_version()}"
    except IchnosError:
        exiftool = "exiftool not found"
    QMessageBox.about(
        parent,
        "About Ichnos",
        f"<h3>Ichnos {__version__}</h3>"
        "<p>View, edit and remove photo metadata, safely.</p>"
        "<p><i>Ichnos</i> (ίχνος) is Greek for <i>trace</i>: the traces a photo "
        "carries about where, when and by whom it was taken.</p>"
        f"<p>Uses {escape(exiftool)} by Phil Harvey.</p>"
        "<p>Licensed under the GNU GPL, version 3 or later.<br>"
        '<a href="https://github.com/padou-dev/ichnos">github.com/padou-dev/ichnos</a></p>',
    )
