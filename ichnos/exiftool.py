# SPDX-License-Identifier: GPL-3.0-or-later
"""Run exiftool as a subprocess.

Every call goes through :func:`run_exiftool`, which passes arguments through an
argument file on stdin instead of the command line. That keeps non-ASCII file
names and tag values intact on Windows, and allows values containing newlines.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

EXIFTOOL_ENV = "ICHNOS_EXIFTOOL"

# Places exiftool is installed but which may not be on PATH. Arch Linux puts
# it in /usr/bin/vendor_perl, which is only added to PATH by login shells, so
# apps started from a launcher, a service or a container may not see it.
KNOWN_LOCATIONS = (
    "/usr/bin/vendor_perl/exiftool",
    "/usr/bin/site_perl/exiftool",
    "/usr/local/bin/exiftool",
    "/opt/homebrew/bin/exiftool",
)


class IchnosError(Exception):
    """Base class for errors that Ichnos reports to the user."""


class ExifToolNotFoundError(IchnosError):
    """exiftool is not installed or not on PATH."""

    def __init__(self) -> None:
        super().__init__(
            "exiftool was not found. Install it and make sure it is on your "
            f"PATH, or set {EXIFTOOL_ENV} to the full path of the program."
        )


class ExifToolError(IchnosError):
    """exiftool ran but reported a failure."""


@dataclass(frozen=True)
class ExifToolResult:
    returncode: int
    stdout: str
    stderr: str

    def _lines_starting(self, prefix: str) -> list[str]:
        return [
            line.strip() for line in self.stderr.splitlines() if line.strip().startswith(prefix)
        ]

    @property
    def errors(self) -> list[str]:
        return self._lines_starting("Error")

    @property
    def warnings(self) -> list[str]:
        return self._lines_starting("Warning")


def find_exiftool() -> str:
    """Return the exiftool executable to run."""
    override = os.environ.get(EXIFTOOL_ENV)
    if override:
        return override
    found = shutil.which("exiftool")
    if found is not None:
        return found
    for location in KNOWN_LOCATIONS:
        if os.path.isfile(location) and os.access(location, os.X_OK):
            return location
    raise ExifToolNotFoundError()


def _argfile_line(arg: str) -> str:
    """Encode one argument as a line of an exiftool argument file."""
    if "\n" in arg or "\r" in arg:
        escaped = arg.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")
        return "#[CSTR]" + escaped
    return arg


def run_exiftool(args: list[str]) -> ExifToolResult:
    """Run exiftool with the given arguments and return its output."""
    command = [find_exiftool(), "-charset", "filename=utf8", "-@", "-"]
    argfile = "\n".join(_argfile_line(arg) for arg in args) + "\n"
    # Stop a console window flashing up when the GUI runs exiftool on Windows.
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        completed = subprocess.run(
            command,
            input=argfile,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
    except FileNotFoundError as error:
        raise ExifToolNotFoundError() from error
    return ExifToolResult(completed.returncode, completed.stdout, completed.stderr)


def exiftool_version() -> str:
    """Return the installed exiftool version, e.g. '13.59'."""
    result = run_exiftool(["-ver"])
    if result.returncode != 0:
        raise ExifToolError(result.stderr.strip() or "exiftool -ver failed")
    return result.stdout.strip()
