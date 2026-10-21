# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for what each preset removes and keeps."""

from pathlib import Path

from ichnos.metadata import Category, read_tags
from ichnos.presets import Preset, Reason, has_location, preset_removals


def removed_keys(path: Path, preset: Preset) -> set[str]:
    meta = read_tags(path)
    removals = preset_removals(meta, preset)
    return {tag.key for tag in meta.removable if tag.removal_target in removals}


def test_location_preset_removes_every_kind_of_location(tagged_jpeg: Path) -> None:
    removed = removed_keys(tagged_jpeg, Preset.LOCATION)
    assert {"GPS:GPSLatitude", "GPS:GPSLongitude"} <= removed
    assert "XMP-exif:GPSLatitude" in removed
    assert "XMP-photoshop:City" in removed


def test_location_preset_keeps_everything_else(tagged_jpeg: Path) -> None:
    removed = removed_keys(tagged_jpeg, Preset.LOCATION)
    assert "IFD0:Artist" not in removed
    assert "ExifIFD:SerialNumber" not in removed


def test_share_safe_removes_personal_and_device_ids(tagged_jpeg: Path) -> None:
    removed = removed_keys(tagged_jpeg, Preset.SHARE_SAFE)
    assert {"IFD0:Artist", "ExifIFD:SerialNumber", "ExifIFD:ImageUniqueID"} <= removed
    assert "GPS:GPSLatitude" in removed


def test_share_safe_keeps_camera_date_and_copyright(tagged_jpeg: Path) -> None:
    removed = removed_keys(tagged_jpeg, Preset.SHARE_SAFE)
    for kept in ("IFD0:Make", "IFD0:Model", "ExifIFD:DateTimeOriginal", "IFD0:Copyright"):
        assert kept not in removed


def test_strip_all_removes_every_removable_tag(tagged_jpeg: Path) -> None:
    meta = read_tags(tagged_jpeg)
    removals = preset_removals(meta, Preset.STRIP_ALL)
    assert all(tag.removal_target in removals for tag in meta.removable)


def test_no_preset_ever_removes_protected_tags(tagged_jpeg: Path) -> None:
    meta = read_tags(tagged_jpeg)
    protected = {t.removal_target for t in meta.tags if t.category is Category.PROTECTED}
    assert protected
    for preset in Preset:
        assert not protected & set(preset_removals(meta, preset))


def test_reasons_are_recorded(tagged_jpeg: Path) -> None:
    removals = preset_removals(read_tags(tagged_jpeg), Preset.SHARE_SAFE)
    assert removals[("GPS", "GPSLatitude")] is Reason.LOCATION
    assert removals[("IFD0", "Artist")] is Reason.PERSONAL
    assert removals[("ExifIFD", "SerialNumber")] is Reason.DEVICE


def test_has_location(tagged_jpeg: Path, plain_jpeg: Path) -> None:
    assert has_location(read_tags(tagged_jpeg))
    assert not has_location(read_tags(plain_jpeg))
