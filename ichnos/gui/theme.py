# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply colours to the app: the Omarchy theme when there is one, else the system's.

On Omarchy the theme is also watched, so switching themes recolours Ichnos
while it is running.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from ichnos.theme_colors import ThemeColors, load_theme_colors, omarchy_theme_dir


def _hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)


def colors_from_palette(palette: QPalette) -> ThemeColors:
    """Fallback colours that sit well with the system's own light or dark style."""
    background = _hex(palette.color(QPalette.ColorRole.Window))
    foreground = _hex(palette.color(QPalette.ColorRole.WindowText))
    dark = QColor(background).lightnessF() < 0.5
    return ThemeColors(
        background=background,
        foreground=foreground,
        accent=_hex(palette.color(QPalette.ColorRole.Highlight)),
        warning="#f0a050" if dark else "#a85a00",
        success="#70c070" if dark else "#2e7d32",
        error="#f07070" if dark else "#c62828",
        source="system",
    )


class ThemeManager(QObject):
    """Owns the current colours and re-applies them when the Omarchy theme changes."""

    changed = Signal()

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._system_style = app.style().name()
        self._system_palette = QPalette(app.palette())
        self.colors = colors_from_palette(self._system_palette)
        self.from_omarchy = False

        self._watcher = QFileSystemWatcher(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.apply)
        self._watcher.directoryChanged.connect(lambda _path: self._debounce.start())
        self._watcher.fileChanged.connect(lambda _path: self._debounce.start())

    def _watch(self, folder: Path | None) -> None:
        old = self._watcher.directories() + self._watcher.files()
        if old:
            self._watcher.removePaths(old)
        if folder is None:
            return
        # Omarchy switches themes by replacing the `theme` link inside `current`,
        # so watch the parent folder as well as the theme itself.
        paths = [str(p) for p in (folder.parent, folder) if p.exists()]
        paths += [str(f) for f in folder.iterdir() if f.is_file()] if folder.is_dir() else []
        if paths:
            self._watcher.addPaths(paths)

    def apply(self) -> None:
        folder = omarchy_theme_dir()
        colors = load_theme_colors(folder)
        self._watch(folder)

        if colors is None:
            if self.from_omarchy:  # only undo what we changed
                self._app.setStyle(self._system_style)
                self._app.setPalette(self._system_palette)
            self.from_omarchy = False
            self.colors = colors_from_palette(self._app.palette())
        else:
            self.from_omarchy = True
            self._app.setStyle("Fusion")
            self._app.setPalette(self._palette_for(colors))
            self.colors = colors
        self._app.setStyleSheet(self._stylesheet(self.colors))
        self.changed.emit()

    @staticmethod
    def _palette_for(c: ThemeColors) -> QPalette:
        palette = QPalette()
        roles = {
            QPalette.ColorRole.Window: c.background,
            QPalette.ColorRole.WindowText: c.foreground,
            QPalette.ColorRole.Base: c.panel,
            QPalette.ColorRole.AlternateBase: c.surface,
            QPalette.ColorRole.Text: c.foreground,
            QPalette.ColorRole.Button: c.surface,
            QPalette.ColorRole.ButtonText: c.foreground,
            QPalette.ColorRole.Highlight: c.accent,
            QPalette.ColorRole.HighlightedText: c.accent_text,
            QPalette.ColorRole.ToolTipBase: c.surface,
            QPalette.ColorRole.ToolTipText: c.foreground,
            QPalette.ColorRole.PlaceholderText: c.dim,
            QPalette.ColorRole.Link: c.accent,
            QPalette.ColorRole.BrightText: c.error,
            QPalette.ColorRole.Mid: c.border,
            QPalette.ColorRole.Dark: c.panel,
        }
        for role, value in roles.items():
            palette.setColor(role, QColor(value))
        for role in (
            QPalette.ColorRole.WindowText,
            QPalette.ColorRole.Text,
            QPalette.ColorRole.ButtonText,
        ):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c.dim))
        return palette

    @staticmethod
    def _stylesheet(c: ThemeColors) -> str:
        return f"""
            QPushButton#primary {{
                background: {c.accent}; color: {c.accent_text};
                border: none; border-radius: 4px; padding: 6px 16px; font-weight: bold;
            }}
            QPushButton#primary:disabled {{ background: {c.border}; color: {c.dim}; }}
            QToolButton#preset {{
                padding: 5px 12px; border: 1px solid {c.border}; background: {c.surface};
            }}
            QToolButton#preset:checked {{
                background: {c.accent}; color: {c.accent_text}; border-color: {c.accent};
                font-weight: bold;
            }}
            QToolButton#preset:disabled {{ color: {c.dim}; }}
            QLabel#heading {{
                color: {c.accent}; font-weight: bold; letter-spacing: 1px;
            }}
            QLabel#appName {{ color: {c.accent}; font-weight: bold; font-size: 15px; }}
            QLabel#dim {{ color: {c.dim}; }}
            QFrame#note {{ border: 1px solid {c.border}; border-radius: 4px; }}
            QFrame#stat {{ background: {c.surface}; border-radius: 4px; }}
        """
