# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for ichnos.metadata."""

import subprocess
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from ichnos.metadata import read_tags


@pytest.fixture
def tagged_jpeg(tmp_path: Path) -> Path:
    """A small JPEG with known camera and GPS tags written into it."""
    path = tmp_path / "sample.jpg"

    image = QImage(64, 48, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))
    assert image.save(str(path), "JPEG")

    subprocess.run(
        [
            "exiftool",
            "-overwrite_original",
            "-Make=IchnosTest",
            "-Model=Fixture",
            "-GPSLatitude=37.6318",
            "-GPSLatitudeRef=N",
            "-GPSLongitude=22.7271",
            "-GPSLongitudeRef=E",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


def test_read_tags_finds_camera_tags(tagged_jpeg: Path) -> None:
    tags = read_tags(tagged_jpeg)
    assert tags["IFD0:Make"] == "IchnosTest"
    assert tags["IFD0:Model"] == "Fixture"


def test_read_tags_finds_gps_tags(tagged_jpeg: Path) -> None:
    tags = read_tags(tagged_jpeg)
    assert "GPS:GPSLatitude" in tags
    assert "GPS:GPSLongitude" in tags


def test_read_tags_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        read_tags(tmp_path / "does_not_exist.jpg")