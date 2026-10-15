# SPDX-License-Identifier: GPL-3.0-or-later
import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Ichnos")

    window = QMainWindow()
    window.setWindowTitle("Ichnos")
    window.setCentralWidget(QLabel("Hello from Ichnos"))
    window.resize(900, 600)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())