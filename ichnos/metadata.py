# SPDX-License-Identifier: GPL-3.0-or-later
"""Read and write image metadata through exiftool."""

import json
import subprocess
from pathlib import Path


def read_tags(path: Path) -> dict[str, object]:
    """Return every metadata tag in the file, keyed as 'Group:TagName'."""
    result = subprocess.run(
        ["exiftool", "-json", "-G1", "-a", str(path)],
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(result.stdout)[0]