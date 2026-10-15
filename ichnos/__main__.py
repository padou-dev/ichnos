# SPDX-License-Identifier: GPL-3.0-or-later
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ichnos.window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Ichnos")

    window = MainWindow()
    if len(sys.argv) > 1:
        window.open_file(Path(sys.argv[1]))
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())