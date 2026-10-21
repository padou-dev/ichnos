# SPDX-License-Identifier: GPL-3.0-or-later
"""Presets: which tags to remove, and why.

Every removal carries a reason, so the GUI and the command line can explain
what is being removed instead of just listing tag names.
"""

from __future__ import annotations

from enum import Enum

from ichnos.metadata import Category, FileMetadata, RemovalTarget, Tag


class Reason(str, Enum):
    LOCATION = "location"
    PERSONAL = "personal info"
    DEVICE = "device ID"
    THUMBNAIL = "thumbnail"
    MAKER_NOTES = "maker notes"
    HISTORY = "edit history"
    OTHER = "metadata"
    CHOSEN = "chosen"


class Preset(str, Enum):
    LOCATION = "location"
    SHARE_SAFE = "share-safe"
    STRIP_ALL = "strip-all"

    @property
    def label(self) -> str:
        return {
            Preset.LOCATION: "Location only",
            Preset.SHARE_SAFE: "Share-safe",
            Preset.STRIP_ALL: "Strip all",
        }[self]

    @property
    def description(self) -> str:
        return {
            Preset.LOCATION: "Remove GPS and place names. Keep everything else.",
            Preset.SHARE_SAFE: (
                "Remove location, personal info, device serial numbers, "
                "thumbnails, maker notes and edit history. Keep date, camera "
                "and exposure details."
            ),
            Preset.STRIP_ALL: (
                "Remove all metadata. Keep only what the image needs to " "display correctly."
            ),
        }[self]


LOCATION_NAMES = frozenset(
    {
        "City", "State", "Country", "CountryCode", "Location", "Sublocation",
        "Sub-location", "Province-State", "Country-PrimaryLocationName",
        "Country-PrimaryLocationCode", "LocationName",
    }
)  # fmt: skip
LOCATION_PREFIXES = ("LocationShown", "LocationCreated")

PERSONAL_NAMES = frozenset(
    {
        "Artist", "Creator", "By-line", "By-lineTitle", "OwnerName",
        "CameraOwnerName", "Writer-Editor", "CaptionWriter", "Author", "Owner",
        "AuthorsPosition", "XPAuthor",
    }
)  # fmt: skip
PERSONAL_PREFIXES = ("CreatorContactInfo",)

DEVICE_NAMES = frozenset(
    {
        "SerialNumber", "BodySerialNumber", "CameraSerialNumber",
        "InternalSerialNumber", "LensSerialNumber", "ImageUniqueID",
        "DocumentID", "InstanceID", "OriginalDocumentID", "HostComputer",
    }
)  # fmt: skip

THUMBNAIL_NAMES = frozenset({"ThumbnailImage", "PreviewImage", "ThumbnailTIFF"})
HISTORY_PREFIXES = ("History", "DerivedFrom", "Ingredients", "Pantry")


def privacy_reason(tag: Tag) -> Reason | None:
    """Why a removable tag can reveal something private, or None."""
    if tag.category is not Category.METADATA:
        return None
    name = tag.name
    if tag.group == "GPS" or "GPS" in name:
        return Reason.LOCATION
    if name in LOCATION_NAMES or name.startswith(LOCATION_PREFIXES):
        return Reason.LOCATION
    if tag.family == "MakerNotes":
        return Reason.MAKER_NOTES
    if tag.group == "IFD1" or name in THUMBNAIL_NAMES:
        return Reason.THUMBNAIL
    if name in DEVICE_NAMES:
        return Reason.DEVICE
    if name in PERSONAL_NAMES or name.startswith(PERSONAL_PREFIXES):
        return Reason.PERSONAL
    if tag.group == "XMP-xmpMM" and name.startswith(HISTORY_PREFIXES):
        return Reason.HISTORY
    if name == "DocumentAncestors":
        return Reason.HISTORY
    return None


def has_location(meta: FileMetadata) -> bool:
    return any(privacy_reason(tag) is Reason.LOCATION for tag in meta.removable)


def preset_removals(meta: FileMetadata, preset: Preset) -> dict[RemovalTarget, Reason]:
    """The tags a preset removes from one file, with the reason for each."""
    removals: dict[RemovalTarget, Reason] = {}
    for tag in meta.removable:
        reason = privacy_reason(tag)
        if preset is Preset.LOCATION:
            wanted = reason is Reason.LOCATION
        elif preset is Preset.SHARE_SAFE:
            wanted = reason is not None
        else:
            wanted = True
        if wanted and tag.removal_target not in removals:
            removals[tag.removal_target] = reason or Reason.OTHER
    return removals
