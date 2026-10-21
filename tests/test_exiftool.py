# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for finding exiftool."""

from pathlib import Path

import pytest

from ichnos import exiftool
from ichnos.exiftool import ExifToolNotFoundError, find_exiftool


@pytest.fixture(autouse=True)
def _require_exiftool() -> None:
    """These tests fake exiftool's location, so they don't need the real one."""


def test_environment_variable_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_EXIFTOOL", "/custom/exiftool")
    assert find_exiftool() == "/custom/exiftool"


def test_known_location_is_used_when_not_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "exiftool"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.delenv("ICHNOS_EXIFTOOL", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(exiftool, "KNOWN_LOCATIONS", (str(tmp_path / "nope"), str(fake)))
    assert find_exiftool() == str(fake)


def test_missing_exiftool_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ICHNOS_EXIFTOOL", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(exiftool, "KNOWN_LOCATIONS", (str(tmp_path / "nope"),))
    with pytest.raises(ExifToolNotFoundError):
        find_exiftool()
