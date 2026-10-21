# SPDX-License-Identifier: GPL-3.0-or-later
"""Right-hand panel: a small preview and a summary of pending changes."""

from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from ichnos.metadata import Category, FileMetadata
from ichnos.theme_colors import ThemeColors
from ichnos.writer import DEFAULT_SUFFIX, FilePlan

PREVIEW_SIZE = QSize(320, 240)


def load_image(path: Path, box: QSize) -> QImage:
    """Read an image scaled to fit inside box, turned the right way up.

    Returns a null QImage for formats Qt can't decode (most RAW files, and
    HEIC unless a plugin is installed).
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)  # applies the EXIF orientation
    size = reader.size()
    if size.isValid():
        longest = max(size.width(), size.height(), 1)
        scale = min(1.0, max(box.width(), box.height()) / longest)
        reader.setScaledSize(
            QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale)))
        )
    return reader.read()


class _Stat(QFrame):
    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setObjectName("stat")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(0)
        top = QLabel(caption)
        top.setObjectName("dim")
        self.number = QLabel("–")
        font = self.number.font()
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * 1.6)
        font.setBold(True)
        self.number.setFont(font)
        bottom = QLabel("tags")
        bottom.setObjectName("dim")
        for widget in (top, self.number, bottom):
            layout.addWidget(widget)


class SidePanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(400)
        self._previews: dict[Path, QImage] = {}
        self._colors: ThemeColors | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setObjectName("dim")
        layout.addWidget(self.preview)

        heading = QLabel("PENDING CHANGES")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        stats = QGridLayout()
        self.before = _Stat("Before")
        self.after = _Stat("After")
        stats.addWidget(self.before, 0, 0)
        stats.addWidget(self.after, 0, 1)
        layout.addLayout(stats)

        self.changes = QLabel()
        self.changes.setWordWrap(True)
        self.changes.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.changes)

        self.scope = QLabel()
        self.scope.setWordWrap(True)
        self.scope.setObjectName("dim")
        layout.addWidget(self.scope)

        note = QFrame()
        note.setObjectName("note")
        note_layout = QVBoxLayout(note)
        title = QLabel("<b>Originals untouched</b>")
        body = QLabel(
            f"Each copy is saved next to its original as name{DEFAULT_SUFFIX}.ext "
            "and checked after writing. Existing files are never overwritten."
        )
        body.setWordWrap(True)
        body.setObjectName("dim")
        note_layout.addWidget(title)
        note_layout.addWidget(body)
        layout.addWidget(note)
        layout.addStretch(1)

    def set_colors(self, colors: ThemeColors) -> None:
        self._colors = colors

    def forget(self, path: Path) -> None:
        self._previews.pop(path, None)

    def _show_preview(self, meta: FileMetadata | None) -> None:
        if meta is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("")
            return
        image = self._previews.get(meta.path)
        if image is None:
            image = load_image(meta.path, PREVIEW_SIZE)
            self._previews[meta.path] = image
        if image.isNull():
            self.preview.setPixmap(QPixmap())
            kind = meta.file_type or meta.path.suffix.lstrip(".").upper()
            self.preview.setText(f"No preview for {kind} files.\nMetadata works as normal.")
        else:
            self.preview.setText("")
            self.preview.setPixmap(QPixmap.fromImage(image))
            self.preview.setToolTip(f"{meta.path.name}, shown the way it is meant to be viewed")

    def show_summary(
        self, meta: FileMetadata | None, plan: FilePlan, selected: int, changing: int
    ) -> None:
        self._show_preview(meta)
        if meta is None or self._colors is None:
            self.before.number.setText("–")
            self.after.number.setText("–")
            self.changes.setText("")
            self.scope.setText("")
            return

        c = self._colors
        removed = [t for t in meta.removable if t.removal_target in plan.removals]
        embedded = len(meta.embedded)
        self.before.number.setText(str(embedded))
        self.after.number.setText(str(embedded - len(removed)))
        self.after.number.setStyleSheet(f"color: {c.success};" if removed else "")

        lines: list[str] = []
        if removed:
            reasons = Counter(plan.removals[t.removal_target].value for t in removed)
            detail = ", ".join(f"{name} {count}" for name, count in reasons.most_common())
            lines.append(
                self._line("−", c.warning, f"{len(removed)} tags removed ({escape(detail)})")
            )
        else:
            lines.append(self._line("·", c.dim, "Nothing removed from this file"))
        if plan.edits:
            n = len(plan.edits)
            lines.append(
                self._line("~", c.accent, f"{n} tag{'s' if n != 1 else ''} edited (this file only)")
            )
        if meta.find("IFD0", "Orientation") is not None:
            lines.append(self._line("✓", c.success, "Orientation kept, so the photo stays upright"))
        if any(t.family == "ICC_Profile" for t in meta.tags):
            lines.append(self._line("✓", c.success, "Colour profile kept"))
        protected = sum(1 for t in meta.tags if t.category is Category.PROTECTED)
        if protected:
            lines.append(self._line("✓", c.success, f"{protected} structural tags protected"))
        self.changes.setText("<br>".join(lines))

        self.scope.setText(
            f"Removals apply to all {selected} ticked files; "
            f"{changing} of them will get a cleaned copy."
        )

    @staticmethod
    def _line(symbol: str, color: str, text: str) -> str:
        return f'<span style="color:{color}; font-weight:bold">{symbol}</span>&nbsp; {text}'
