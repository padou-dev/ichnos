# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for writing cleaned copies. These are the safety guarantees."""

from pathlib import Path

import pytest

from ichnos.metadata import read_tags
from ichnos.presets import Preset
from ichnos.writer import (
    FilePlan,
    clean_copy_path,
    plan_for_file,
    unique_output_path,
    write_copy,
)


def clean(path: Path, preset: Preset, **plan_options):
    meta = read_tags(path)
    plan = plan_for_file(meta, preset, **plan_options)
    destination = unique_output_path(path)
    return write_copy(meta, plan, destination)


@pytest.mark.parametrize("preset", list(Preset))
def test_every_preset_writes_a_verified_copy(tagged_jpeg: Path, preset: Preset) -> None:
    result = clean(tagged_jpeg, preset)
    assert result.verified, result.leftovers
    assert result.destination.exists()


@pytest.mark.parametrize("preset", list(Preset))
def test_original_is_never_modified(tagged_jpeg: Path, preset: Preset) -> None:
    before = tagged_jpeg.read_bytes()
    clean(tagged_jpeg, preset)
    assert tagged_jpeg.read_bytes() == before


@pytest.mark.parametrize("preset", list(Preset))
def test_orientation_always_survives(tagged_jpeg: Path, preset: Preset) -> None:
    result = clean(tagged_jpeg, preset)
    copy = read_tags(result.destination)
    assert copy.find("IFD0", "Orientation").value == "Rotate 90 CW"


def test_location_is_gone_from_the_copy(tagged_jpeg: Path) -> None:
    copy = read_tags(clean(tagged_jpeg, Preset.LOCATION).destination)
    assert not any(tag.group == "GPS" for tag in copy.tags)
    assert copy.find("XMP-exif", "GPSLatitude") is None
    assert copy.find("XMP-photoshop", "City") is None
    assert copy.find("IFD0", "Make").value == "IchnosTest"


def test_strip_all_leaves_no_removable_tags(tagged_jpeg: Path) -> None:
    copy = read_tags(clean(tagged_jpeg, Preset.STRIP_ALL).destination)
    assert copy.removable == []


def test_png_text_chunks_are_removed(tagged_png: Path) -> None:
    copy = read_tags(clean(tagged_png, Preset.STRIP_ALL).destination)
    assert copy.find("PNG", "Comment") is None
    assert copy.find("PNG", "ImageWidth").value == 64


def test_refuses_to_overwrite(tagged_jpeg: Path) -> None:
    meta = read_tags(tagged_jpeg)
    destination = clean_copy_path(tagged_jpeg)
    destination.write_bytes(b"precious existing file")
    with pytest.raises(FileExistsError):
        write_copy(meta, plan_for_file(meta, Preset.STRIP_ALL), destination)
    assert destination.read_bytes() == b"precious existing file"


def test_empty_plan_is_refused(tagged_jpeg: Path) -> None:
    meta = read_tags(tagged_jpeg)
    with pytest.raises(ValueError):
        write_copy(meta, FilePlan(), clean_copy_path(tagged_jpeg))


def test_unique_output_path_numbers_copies(tagged_jpeg: Path) -> None:
    first = unique_output_path(tagged_jpeg)
    assert first.name == "sample_clean.jpg"
    first.write_bytes(b"x")
    assert unique_output_path(tagged_jpeg).name == "sample_clean-2.jpg"
    taken = {unique_output_path(tagged_jpeg)}
    assert unique_output_path(tagged_jpeg, taken=taken).name == "sample_clean-3.jpg"


def test_unique_output_path_can_use_another_folder(tagged_jpeg: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert unique_output_path(tagged_jpeg, out) == out / "sample_clean.jpg"


def test_override_can_keep_a_tag(tagged_jpeg: Path) -> None:
    result = clean(tagged_jpeg, Preset.SHARE_SAFE, overrides={("IFD0", "Artist"): False})
    assert read_tags(result.destination).find("IFD0", "Artist").value == "Jane Example"


def test_override_can_remove_a_tag(tagged_jpeg: Path) -> None:
    result = clean(tagged_jpeg, Preset.LOCATION, overrides={("IFD0", "Make"): True})
    assert read_tags(result.destination).find("IFD0", "Make") is None


def test_edits_are_written(tagged_jpeg: Path) -> None:
    edits = {
        ("IFD0", "Artist"): "Πάνος",
        ("XMP-dc", "Description"): "Line one\nLine two",
        ("ExifIFD", "DateTimeOriginal"): "2020:01:02 03:04:05",
    }
    result = clean(tagged_jpeg, Preset.LOCATION, edits=edits)
    assert result.verified, result.leftovers
    copy = read_tags(result.destination)
    assert copy.find("IFD0", "Artist").value == "Πάνος"
    assert copy.find("XMP-dc", "Description").value == "Line one\nLine two"
    assert copy.find("ExifIFD", "DateTimeOriginal").value == "2020:01:02 03:04:05"


def test_removal_wins_over_an_edit(tagged_jpeg: Path) -> None:
    meta = read_tags(tagged_jpeg)
    plan = plan_for_file(meta, Preset.SHARE_SAFE, edits={("IFD0", "Artist"): "Someone"})
    assert ("IFD0", "Artist") not in plan.edits


def test_bad_date_edit_is_rejected_before_writing(tagged_jpeg: Path) -> None:
    meta = read_tags(tagged_jpeg)
    plan = plan_for_file(meta, None, edits={("ExifIFD", "DateTimeOriginal"): "yesterday"})
    destination = clean_copy_path(tagged_jpeg)
    with pytest.raises(ValueError):
        write_copy(meta, plan, destination)
    assert not destination.exists()
