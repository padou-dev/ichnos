# SPDX-License-Identifier: GPL-3.0-or-later
"""Run slow jobs (exiftool calls, thumbnails) off the GUI thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal

Progress = Callable[[int, int], None]
Job = Callable[[Progress], Any]


class Worker(QThread):
    """Runs job(progress) in a background thread.

    The signals are delivered on the GUI thread, so their slots may touch
    widgets safely.
    """

    progressed = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(object)  # the exception

    def __init__(self, job: Job, parent=None) -> None:
        super().__init__(parent)
        self._job = job

    def run(self) -> None:
        try:
            result = self._job(self.progressed.emit)
        except Exception as error:  # noqa: BLE001 - reported to the user
            self.failed.emit(error)
            return
        self.succeeded.emit(result)
