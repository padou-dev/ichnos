# SPDX-License-Identifier: GPL-3.0-or-later
"""Read image metadata and sort every tag into a category.

exiftool reports three very different kinds of information, and Ichnos treats
them differently:

* METADATA   - embedded in the file and safe to remove (EXIF, GPS, XMP, IPTC,
               maker notes, PNG text chunks, JPEG comments).
* PROTECTED  - embedded, but needed to display the image correctly
               (orientation, colour profile, image structure). Never removed.
* FILE_INFO  - not stored in the image at all: file-system details and values
               exiftool calculates (System, File, Composite, ExifTool).
"""

from __future__ import annotations

import glob
import json
import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ichnos.exiftool import ExifToolError, run_exiftool

SUPPORTED_EXTENSIONS = frozenset(
    {
        ".jpg", ".jpeg", ".jpe", ".png", ".webp", ".heic", ".heif", ".avif",
        ".tif", ".tiff", ".dng", ".cr2", ".cr3", ".nef", ".nrw", ".arw",
        ".raf", ".rw2", ".orf", ".pef", ".srw",
    }
)  # fmt: skip

FILE_INFO_FAMILIES = frozenset({"ExifTool", "File", "Composite"})
METADATA_FAMILIES = frozenset(
    {"EXIF", "XMP", "IPTC", "Photoshop", "MakerNotes", "Ducky", "PrintIM", "FlashPix"}
)

# IFD0 tags the EXIF standard requires whenever IFD0 exists (it always does,
# because Orientation is kept).
EXIF_REQUIRED_IFD0 = frozenset({"XResolution", "YResolution", "ResolutionUnit", "YCbCrPositioning"})

# Tags in the PNG family that describe the image itself rather than text chunks.
PNG_STRUCTURE = frozenset(
    {
        "ImageWidth", "ImageHeight", "BitDepth", "ColorType", "Compression",
        "Filter", "Interlace", "BackgroundColor", "Gamma", "SRGBRendering",
        "WhitePointX", "WhitePointY", "RedX", "RedY", "GreenX", "GreenY",
        "BlueX", "BlueY", "PixelsPerUnitX", "PixelsPerUnitY", "PixelUnits",
        "Palette", "Transparency", "SignificantBits", "ProfileName",
        "ICCProfileName", "AnimationFrames", "AnimationPlays",
    }
)  # fmt: skip

# Tags a user may edit, by (family 1 group, tag name).
EDITABLE_TAGS = frozenset(
    {
        ("IFD0", "Artist"), ("IFD0", "Copyright"), ("IFD0", "ImageDescription"),
        ("IFD0", "ModifyDate"), ("ExifIFD", "DateTimeOriginal"),
        ("ExifIFD", "CreateDate"), ("XMP-dc", "Title"), ("XMP-dc", "Description"),
        ("XMP-dc", "Rights"), ("XMP-dc", "Creator"), ("IPTC", "Caption-Abstract"),
        ("IPTC", "By-line"), ("IPTC", "ObjectName"), ("IPTC", "CopyrightNotice"),
        ("PNG", "Comment"), ("PNG", "Author"), ("PNG", "Title"),
        ("PNG", "Description"), ("PNG", "Copyright"), ("File", "Comment"),
    }
)  # fmt: skip

# File types whose main image lives in TIFF-style EXIF directories. Their IFD0
# and SubIFD tags describe the image data itself, so only clearly descriptive
# tags there may be removed.
RAW_TYPES = frozenset(
    {
        "DNG", "NEF", "NRW", "CR2", "CR3", "CRW", "ARW", "SR2", "SRF", "RAF",
        "RW2", "ORF", "PEF", "SRW", "3FR", "IIQ", "ERF", "MEF", "MOS", "RWL",
    }
)  # fmt: skip
TIFF_TYPES = RAW_TYPES | {"TIFF", "BTF"}
TIFF_DESCRIPTIVE = frozenset(
    {
        "Artist", "Copyright", "ImageDescription", "Software", "ModifyDate",
        "HostComputer", "DocumentName", "PageName", "XPTitle", "XPComment",
        "XPAuthor", "XPKeywords", "XPSubject", "CameraSerialNumber",
        "OwnerName", "Rating", "RatingPercent",
    }
)  # fmt: skip
EXIF_SIDE_GROUPS = frozenset({"ExifIFD", "GPS", "InteropIFD"})

EXIF_DATE_TAGS = frozenset({"ModifyDate", "DateTimeOriginal", "CreateDate"})
EXIF_DATE_PATTERN = re.compile(r"^\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}$")

MAKERNOTES_TARGET = ("MakerNotes", "all")

# A removal target names what gets deleted: (group, tag name), or
# ("MakerNotes", "all") for a whole maker-notes block.
RemovalTarget = tuple[str, str]


class Category(Enum):
    METADATA = "metadata"
    PROTECTED = "protected"
    FILE_INFO = "file info"


@dataclass(frozen=True)
class Tag:
    family: str  # exiftool family 0 group, e.g. "EXIF"
    group: str  # exiftool family 1 group, e.g. "GPS"
    name: str
    value: object
    file_type: str = ""  # File:FileType of the file this tag came from

    @property
    def key(self) -> str:
        return f"{self.group}:{self.name}"

    @property
    def group_label(self) -> str:
        if self.family == self.group:
            return self.group
        return f"{self.family} · {self.group}"

    @property
    def display_value(self) -> str:
        return format_value(self.value)

    @property
    def category(self) -> Category:
        if self.family == "File" and self.name == "Comment":
            return Category.METADATA  # a JPEG COM segment, really in the file
        if self.family in FILE_INFO_FAMILIES:
            return Category.FILE_INFO
        if self.protected_reason is not None:
            return Category.PROTECTED
        return Category.METADATA

    @property
    def protected_reason(self) -> str | None:
        """Why this tag must be kept, or None if it may be removed."""
        if self.family in FILE_INFO_FAMILIES:
            return None
        if self.family == "EXIF" and self.group == "IFD0":
            if self.name == "Orientation":
                return "keeps the photo the right way up"
            if self.name in EXIF_REQUIRED_IFD0:
                return "required by the EXIF standard"
        if self.family == "MakerNotes" and self.file_type in RAW_TYPES:
            return "needed to develop this RAW file"
        if (
            self.family == "EXIF"
            and self.file_type in TIFF_TYPES
            and self.group not in EXIF_SIDE_GROUPS
            and self.name not in TIFF_DESCRIPTIVE
        ):
            return "part of the image data in this file type"
        if self.family == "ICC_Profile":
            return "colour profile; removing it can change the colours"
        if self.family == "PNG":
            if self.name in PNG_STRUCTURE or self.group != "PNG":
                return "image structure"
            return None
        if self.family in METADATA_FAMILIES:
            return None
        if "GPS" in self.name:
            return None  # location stored in a container, e.g. QuickTime
        return "image structure"

    @property
    def removal_target(self) -> RemovalTarget:
        if self.family == "MakerNotes":
            return MAKERNOTES_TARGET
        return (self.group, self.name)

    @property
    def editable(self) -> bool:
        return (self.group, self.name) in EDITABLE_TAGS


@dataclass
class FileMetadata:
    path: Path
    tags: list[Tag]
    warnings: list[str] = field(default_factory=list)

    def _file_value(self, name: str) -> str:
        for tag in self.tags:
            if tag.family == "File" and tag.name == name:
                return tag.display_value
        return ""

    @property
    def file_type(self) -> str:
        return self._file_value("FileType")

    @property
    def file_size(self) -> str:
        return self._file_value("FileSize")

    @property
    def embedded(self) -> list[Tag]:
        return [tag for tag in self.tags if tag.category is not Category.FILE_INFO]

    @property
    def removable(self) -> list[Tag]:
        return [tag for tag in self.tags if tag.category is Category.METADATA]

    def find(self, group: str, name: str) -> Tag | None:
        for tag in self.tags:
            if tag.group == group and tag.name == name:
                return tag
        return None


@dataclass
class ReadResult:
    files: list[FileMetadata] = field(default_factory=list)
    failures: dict[Path, str] = field(default_factory=dict)


class _Pairs(list):
    """A JSON object kept as (key, value) pairs, so duplicate keys survive."""


def format_value(value: object) -> str:
    if isinstance(value, _Pairs):
        return ", ".join(f"{k}: {format_value(v)}" for k, v in value)
    if isinstance(value, list):
        return ", ".join(format_value(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _plain(value: object) -> object:
    """Turn nested _Pairs (XMP structures) into ordinary dicts."""
    if isinstance(value, _Pairs):
        return {k: _plain(v) for k, v in value}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _error_for(path: Path, messages: list[str]) -> str:
    """Find exiftool's error about one file: 'Error: File not found - C:/a/b.jpg'.

    exiftool writes Windows paths with forward slashes, so paths are compared
    after normalising rather than as plain text.
    """
    for message in messages:
        text, _, named = message.removeprefix("Error:").strip().rpartition(" - ")
        if text and _normalise(named) == _normalise(path):
            return text
    return "exiftool could not read this file"


def parse_key(key: str) -> tuple[str, str, str] | None:
    """Split 'EXIF:GPS:GPSLatitude' into family 0, family 1 and tag name."""
    parts = key.split(":")
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:  # family 0 and 1 have the same name, e.g. 'PNG:Comment'
        return parts[0], parts[0], parts[1]
    return None


def _normalise(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _parse_entry(entry: _Pairs) -> tuple[str, list[Tag], list[str], str | None]:
    source = ""
    tags: list[Tag] = []
    warnings: list[str] = []
    error: str | None = None
    for key, value in entry:
        if key == "SourceFile":
            source = str(value)
            continue
        parsed = parse_key(key)
        if parsed is None:
            continue
        family, group, name = parsed
        if family == "ExifTool" and name == "Error":
            error = format_value(value)
        elif family == "ExifTool" and name == "Warning":
            warnings.append(format_value(value))
        tags.append(Tag(family, group, name, _plain(value)))
    file_type = next(
        (t.display_value for t in tags if t.family == "File" and t.name == "FileType"),
        "",
    )
    if file_type:
        tags = [Tag(t.family, t.group, t.name, t.value, file_type) for t in tags]
    return source, tags, warnings, error


def read_metadata(
    paths: Sequence[Path],
    progress: Callable[[int, int], None] | None = None,
    chunk_size: int = 50,
) -> ReadResult:
    """Read every tag from each file, running exiftool once per chunk of files."""
    result = ReadResult()
    absolute = [Path(path).absolute() for path in paths]
    for start in range(0, len(absolute), chunk_size):
        chunk = absolute[start : start + chunk_size]
        run = run_exiftool(["-json", "-G0:1", "-a", *[str(p) for p in chunk]])
        try:
            entries = json.loads(run.stdout, object_pairs_hook=_Pairs) if run.stdout.strip() else []
        except json.JSONDecodeError as error:
            raise ExifToolError(f"Could not understand exiftool's output: {error}") from error

        by_source = {}
        for entry in entries:
            source, tags, warnings, error = _parse_entry(entry)
            by_source[_normalise(source)] = (tags, warnings, error)

        messages = run.errors
        for path in chunk:
            found = by_source.get(_normalise(path))
            if found is None:
                result.failures[path] = _error_for(path, messages)
                continue
            tags, warnings, error = found
            if error is not None:
                result.failures[path] = error
                continue
            result.files.append(FileMetadata(path, tags, warnings))
        if progress is not None:
            progress(min(start + chunk_size, len(absolute)), len(absolute))
    return result


def read_tags(path: Path) -> FileMetadata:
    """Read a single file, raising ExifToolError if it can't be read."""
    result = read_metadata([path])
    if result.failures:
        raise ExifToolError(next(iter(result.failures.values())))
    return result.files[0]


def validate_edit(group: str, name: str, value: str) -> str | None:
    """Return a problem with a new tag value, or None if it is acceptable."""
    if (group, name) not in EDITABLE_TAGS:
        return f"{group}:{name} can't be edited"
    if name in EXIF_DATE_TAGS and value and not EXIF_DATE_PATTERN.match(value):
        return "Dates must look like 2026:08:14 20:41:07 (YYYY:MM:DD HH:MM:SS)"
    return None


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def expand_paths(items: Iterable[str | Path], recursive: bool = False) -> list[Path]:
    """Turn files, folders and wildcard patterns into a list of files.

    Folders contribute the supported images inside them. Wildcards are expanded
    here because Windows shells pass them through unexpanded.
    """
    found: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = _normalise(path.absolute())
        if key not in seen:
            seen.add(key)
            found.append(path)

    for item in items:
        path = Path(item)
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in sorted(path.glob(pattern)):
                if child.is_file() and is_supported(child):
                    add(child)
        elif not path.exists() and glob.has_magic(str(item)):
            for match in sorted(glob.glob(str(item), recursive=recursive)):
                if Path(match).is_file():
                    add(Path(match))
        else:
            add(path)
    return found
