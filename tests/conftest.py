# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared test fixtures.

Test images start as small metadata-free files in tests/data. Each fixture
copies one into a temporary folder and writes known, fake tags into it with
exiftool, so the tests never depend on anyone's real photos.
"""

import os
import shutil
from pathlib import Path

import pytest

from ichnos.exiftool import ExifToolNotFoundError, find_exiftool, run_exiftool

DATA = Path(__file__).parent / "data"


@pytest.fixture(autouse=True)
def _require_exiftool() -> None:
    """Skip tests that need exiftool when it's missing.

    In CI, ICHNOS_REQUIRE_EXIFTOOL=1 turns the skip into a failure, so a broken
    setup can't pass by quietly skipping every test.
    """
    try:
        find_exiftool()
    except ExifToolNotFoundError:
        if os.environ.get("ICHNOS_REQUIRE_EXIFTOOL"):
            pytest.fail("exiftool is required but was not found")
        pytest.skip("exiftool is not installed")


def write_tags(path: Path, *assignments: str) -> None:
    result = run_exiftool(["-overwrite_original", *assignments, str(path)])
    assert result.returncode == 0, result.stderr


@pytest.fixture
def plain_jpeg(tmp_path: Path) -> Path:
    path = tmp_path / "plain.jpg"
    shutil.copy(DATA / "plain.jpg", path)
    return path


@pytest.fixture
def tagged_jpeg(tmp_path: Path) -> Path:
    """A JPEG carrying every kind of tag the presets care about."""
    path = tmp_path / "sample.jpg"
    shutil.copy(DATA / "plain.jpg", path)
    write_tags(
        path,
        "-IFD0:Make=IchnosTest",
        "-IFD0:Model=Fixture",
        "-IFD0:Orientation#=6",
        "-IFD0:Artist=Jane Example",
        "-IFD0:Copyright=CC BY 4.0",
        "-ExifIFD:DateTimeOriginal=2026:08:14 20:41:07",
        "-ExifIFD:SerialNumber=3A1F0C9E",
        "-ExifIFD:ImageUniqueID=b8e2c0ffee41c7",
        "-GPS:GPSLatitude=37.6318",
        "-GPS:GPSLatitudeRef=N",
        "-GPS:GPSLongitude=22.7271",
        "-GPS:GPSLongitudeRef=E",
        "-XMP-exif:GPSLatitude=37.6318 N",
        "-XMP-photoshop:City=Argos",
        "-XMP-dc:Description=Sunset over the hills",
    )
    return path


@pytest.fixture
def tagged_png(tmp_path: Path) -> Path:
    path = tmp_path / "text.png"
    shutil.copy(DATA / "plain.png", path)
    write_tags(path, "-PNG:Comment=a private note", "-PNG:Author=Jane Example")
    return path
