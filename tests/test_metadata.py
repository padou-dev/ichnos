# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for reading and classifying metadata."""

import shutil
from pathlib import Path

import pytest

from ichnos.exiftool import ExifToolError
from ichnos.metadata import (
    Category,
    Tag,
    expand_paths,
    parse_key,
    read_metadata,
    read_tags,
    validate_edit,
)


def test_parse_key_with_two_families() -> None:
    assert parse_key("EXIF:GPS:GPSLatitude") == ("EXIF", "GPS", "GPSLatitude")


def test_parse_key_with_one_family() -> None:
    assert parse_key("PNG:Comment") == ("PNG", "PNG", "Comment")


def test_read_tags_finds_camera_tags(tagged_jpeg: Path) -> None:
    meta = read_tags(tagged_jpeg)
    assert meta.find("IFD0", "Make").value == "IchnosTest"
    assert meta.find("IFD0", "Model").value == "Fixture"
    assert meta.file_type == "JPEG"


def test_read_tags_finds_gps_tags(tagged_jpeg: Path) -> None:
    meta = read_tags(tagged_jpeg)
    assert meta.find("GPS", "GPSLatitude") is not None
    assert meta.find("GPS", "GPSLongitude") is not None


def test_read_tags_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ExifToolError):
        read_tags(tmp_path / "does_not_exist.jpg")


def test_read_metadata_reports_failures_and_keeps_going(tagged_jpeg: Path, tmp_path: Path) -> None:
    missing = tmp_path / "missing.jpg"
    result = read_metadata([tagged_jpeg, missing])
    assert [meta.path for meta in result.files] == [tagged_jpeg.absolute()]
    assert "not found" in result.failures[missing.absolute()].lower()


def test_non_ascii_file_names_work(tagged_jpeg: Path) -> None:
    greek = tagged_jpeg.with_name("φωτογραφία ηλιοβασίλεμα.jpg")
    shutil.copy(tagged_jpeg, greek)
    assert read_tags(greek).find("IFD0", "Make").value == "IchnosTest"


def test_categories(tagged_jpeg: Path) -> None:
    meta = read_tags(tagged_jpeg)
    assert meta.find("IFD0", "Orientation").category is Category.PROTECTED
    assert meta.find("GPS", "GPSLatitude").category is Category.METADATA
    assert meta.find("System", "FileSize").category is Category.FILE_INFO
    assert meta.find("Composite", "ImageSize").category is Category.FILE_INFO


def test_png_text_is_metadata_but_png_structure_is_protected(tagged_png: Path) -> None:
    meta = read_tags(tagged_png)
    assert meta.find("PNG", "Comment").category is Category.METADATA
    assert meta.find("PNG", "ImageWidth").category is Category.PROTECTED


def test_jpeg_comment_counts_as_metadata() -> None:
    assert Tag("File", "File", "Comment", "hi").category is Category.METADATA
    assert Tag("File", "File", "FileType", "JPEG").category is Category.FILE_INFO


def test_raw_image_structure_and_maker_notes_are_protected() -> None:
    width = Tag("EXIF", "IFD0", "ImageWidth", 6000, "NEF")
    artist = Tag("EXIF", "IFD0", "Artist", "Jane", "NEF")
    maker_notes = Tag("MakerNotes", "Nikon", "ShutterCount", 1234, "NEF")
    assert width.category is Category.PROTECTED
    assert artist.category is Category.METADATA
    assert maker_notes.category is Category.PROTECTED
    assert Tag("MakerNotes", "Nikon", "ShutterCount", 1234, "JPEG").category is Category.METADATA


def test_maker_notes_are_removed_as_one_block() -> None:
    tag = Tag("MakerNotes", "Canon", "SerialNumber", "123", "JPEG")
    assert tag.removal_target == ("MakerNotes", "all")


def test_validate_edit_checks_dates() -> None:
    assert validate_edit("ExifIFD", "DateTimeOriginal", "2026:08:14 20:41:07") is None
    assert validate_edit("ExifIFD", "DateTimeOriginal", "14/08/2026") is not None


def test_validate_edit_rejects_tags_that_are_not_editable() -> None:
    assert validate_edit("GPS", "GPSLatitude", "1") is not None


def test_expand_paths_reads_folders_and_skips_other_files(tmp_path: Path) -> None:
    (tmp_path / "b.jpg").write_bytes(b"x")
    (tmp_path / "a.PNG").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    found = expand_paths([tmp_path])
    assert [p.name for p in found] == ["a.PNG", "b.jpg"]


def test_expand_paths_expands_wildcards_and_removes_duplicates(tmp_path: Path) -> None:
    (tmp_path / "one.jpg").write_bytes(b"x")
    (tmp_path / "two.jpg").write_bytes(b"x")
    found = expand_paths([str(tmp_path / "*.jpg"), tmp_path / "one.jpg"])
    assert [p.name for p in found] == ["one.jpg", "two.jpg"]
