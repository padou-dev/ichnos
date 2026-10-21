# SPDX-License-Identifier: GPL-3.0-or-later
"""Start the graphical app."""

from __future__ import annotations

import sys
from importlib import resources

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ichnos import APP_ID, __version__
from ichnos.gui.main_window import MainWindow
from ichnos.gui.theme import ThemeManager
from ichnos.metadata import expand_paths


def app_icon() -> QIcon:
    icon_file = resources.files("ichnos") / "resources" / f"{APP_ID}.svg"
    return QIcon(str(icon_file))


def run(files: list[str]) -> int:
    QApplication.setApplicationName("Ichnos")
    QApplication.setOrganizationName("Ichnos")
    QApplication.setApplicationVersion(__version__)
    # Matches the .desktop file, so Wayland compositors (and Hyprland window
    # rules) see the app as io.github.padou_dev.Ichnos.
    QApplication.setDesktopFileName(APP_ID)

    app = QApplication(sys.argv[:1])
    app.setWindowIcon(app_icon())

    theme = ThemeManager(app)
    theme.apply()

    window = MainWindow(theme)
    window.show()
    paths = expand_paths(files)
    if paths:
        window.add_files(paths)
    return app.exec()
