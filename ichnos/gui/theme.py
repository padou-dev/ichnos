# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply Ichnos's look: colours, fonts and widget styling.

Colours come from the active Omarchy theme when there is one, and from
Ichnos's own dark or light palette otherwise (following the system's
dark/light setting). Both are watched, so switching an Omarchy theme or the
system colour scheme restyles Ichnos while it is running.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from ichnos.theme_colors import (
    DEFAULT_DARK,
    DEFAULT_LIGHT,
    ThemeColors,
    load_theme_colors,
    mix,
    omarchy_theme_dir,
)

# Monospace, like the design mockup. The first one installed wins.
FONT_FAMILIES = [
    "JetBrainsMono Nerd Font",
    "JetBrains Mono",
    "Cascadia Mono",
    "Cascadia Code",
    "Consolas",
    "DejaVu Sans Mono",
    "Menlo",
    "monospace",
]
FONT_POINT_SIZE = 10


def system_prefers_dark(app: QApplication, fallback_palette: QPalette) -> bool:
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return fallback_palette.color(QPalette.ColorRole.Window).lightnessF() < 0.5


class ThemeManager(QObject):
    """Owns the current colours and re-applies them when a theme changes."""

    changed = Signal()

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._initial_palette = QPalette(app.palette())
        self.colors: ThemeColors = DEFAULT_DARK
        self.from_omarchy = False

        self._watcher = QFileSystemWatcher(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.apply)
        self._watcher.directoryChanged.connect(lambda _path: self._debounce.start())
        self._watcher.fileChanged.connect(lambda _path: self._debounce.start())
        app.styleHints().colorSchemeChanged.connect(lambda _scheme: self._debounce.start())

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

        self.from_omarchy = colors is not None
        if colors is None:
            dark = system_prefers_dark(self._app, self._initial_palette)
            colors = DEFAULT_DARK if dark else DEFAULT_LIGHT
        self.colors = colors

        self._app.setStyle("Fusion")
        self._app.setPalette(self._palette_for(colors))
        self._app.setFont(self._font())
        self._app.setStyleSheet(self._stylesheet(colors))
        self.changed.emit()

    @staticmethod
    def _font() -> QFont:
        font = QFont()
        font.setFamilies(FONT_FAMILIES)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(FONT_POINT_SIZE)
        return font

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
            QPalette.ColorRole.Light: c.border,
            QPalette.ColorRole.Midlight: c.border,
            QPalette.ColorRole.Mid: c.border,
            QPalette.ColorRole.Dark: c.panel,
            QPalette.ColorRole.Shadow: c.panel,
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
        row_line = mix(c.panel, c.border, 0.5)
        return f"""
            QToolBar {{
                background: {c.panel}; border: none; border-bottom: 1px solid {c.border};
                padding: 6px 8px; spacing: 6px;
            }}
            QMenuBar {{ background: {c.background}; }}
            QMenuBar::item {{ padding: 4px 10px; }}
            QMenuBar::item:selected {{ background: {c.surface}; }}
            QMenu {{ background: {c.panel}; border: 1px solid {c.border}; padding: 4px; }}
            QMenu::item {{ padding: 5px 24px 5px 12px; }}
            QMenu::item:selected {{ background: {c.accent}; color: {c.accent_text}; }}
            QMenu::separator {{ height: 1px; background: {c.border}; margin: 4px 8px; }}
            QStatusBar {{ background: {c.panel}; border-top: 1px solid {c.border}; }}
            QStatusBar QLabel {{ padding: 2px 8px; }}
            QSplitter::handle {{ background: {c.border}; }}
            QSplitter::handle:horizontal {{ width: 1px; }}

            QTreeView, QListView, QTextBrowser {{
                background: {c.panel}; border: 1px solid {c.border}; border-radius: 4px;
                outline: 0;
            }}
            QTreeView::item {{ padding: 4px 2px; border-bottom: 1px solid {row_line}; }}
            QTreeView::item:selected {{ background: {c.surface}; }}
            QListView::item {{ padding: 6px 4px; margin: 1px 2px; border-radius: 3px; }}
            QListView::item:selected {{ background: {c.surface}; color: {c.foreground}; }}
            QHeaderView::section {{
                background: {c.panel}; color: {c.dim}; border: none;
                border-bottom: 1px solid {c.border}; padding: 6px 8px;
            }}

            QLineEdit {{
                background: {c.surface}; border: 1px solid {c.border}; border-radius: 3px;
                padding: 5px 8px; selection-background-color: {c.accent};
            }}
            QLineEdit:focus {{ border-color: {c.accent}; }}
            QPushButton {{
                background: {c.surface}; border: 1px solid {c.border}; border-radius: 4px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{ border-color: {c.accent}; }}
            QPushButton:disabled {{ color: {c.dim}; }}
            QPushButton#primary {{
                background: {c.accent}; color: {c.accent_text};
                border: none; padding: 7px 16px; font-weight: bold;
            }}
            QPushButton#primary:disabled {{ background: {c.border}; color: {c.dim}; }}
            QToolButton#preset {{
                padding: 6px 12px; border: 1px solid {c.border}; background: {c.surface};
            }}
            QToolButton#preset:hover {{ border-color: {c.accent}; }}
            QToolButton#preset:checked {{
                background: {c.accent}; color: {c.accent_text}; border-color: {c.accent};
                font-weight: bold;
            }}
            QToolButton#preset:disabled {{ color: {c.dim}; }}

            QLabel#heading {{
                color: {c.accent}; font-weight: bold; letter-spacing: 1px; font-size: 11px;
            }}
            QLabel#appName {{ color: {c.accent}; font-weight: bold; font-size: 15px; }}
            QLabel#dim {{ color: {c.dim}; }}
            QFrame#note {{ border: 1px solid {c.border}; border-radius: 4px; }}
            QFrame#stat {{ background: {c.surface}; border-radius: 4px; }}
            QToolTip {{
                background: {c.surface}; color: {c.foreground}; border: 1px solid {c.border};
                padding: 4px;
            }}
        """
