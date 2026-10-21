# SPDX-License-Identifier: GPL-3.0-or-later
"""Write cleaned copies of images.

Safety rules, enforced here rather than in the GUI or CLI:

* The original file is never modified: exiftool writes a new file with -o.
* An existing file is never overwritten.
* After writing, the copy is read back and checked. Any tag that should have
  been removed but is still there is reported, never silently ignored.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ichnos.exiftool import ExifToolError, run_exiftool
from ichnos.metadata import (
    MAKERNOTES_TARGET,
    Category,
    FileMetadata,
    TIFF_TYPES,
    RemovalTarget,
    read_tags,
    validate_edit,
)
from ichnos.presets import Preset, Reason, preset_removals, privacy_reason

DEFAULT_SUFFIX = "_clean"

TagId = tuple[str, str]  # (group, tag name)


@dataclass(frozen=True)
class FilePlan:
    """Everything that will change in one file."""

    removals: dict[RemovalTarget, Reason] = field(default_factory=dict)
    edits: dict[TagId, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.removals and not self.edits


def plan_for_file(
    meta: FileMetadata,
    preset: Preset | None,
    overrides: Mapping[RemovalTarget, bool] | None = None,
    edits: Mapping[TagId, str] | None = None,
) -> FilePlan:
    """Combine a preset, manual remove/keep choices and edits into one plan.

    Overrides only apply to tags the file actually has. An edit to a tag that is
    also being removed is dropped: removal wins.
    """
    removals = dict(preset_removals(meta, preset)) if preset is not None else {}
    present = {tag.removal_target: tag for tag in meta.removable}
    for target, remove in (overrides or {}).items():
        if target not in present:
            continue
        if remove:
            removals.setdefault(target, privacy_reason(present[target]) or Reason.CHOSEN)
        else:
            removals.pop(target, None)

    kept_edits: dict[TagId, str] = {}
    for (group, name), value in (edits or {}).items():
        tag = meta.find(group, name)
        if tag is None or tag.removal_target in removals:
            continue
        value = value.strip()
        if value != tag.display_value:
            kept_edits[(group, name)] = value
    return FilePlan(removals, kept_edits)


def build_write_args(meta: FileMetadata, plan: FilePlan) -> list[str]:
    """Translate a plan into exiftool arguments (without the file names).

    When every tag in a group is being removed, the whole group is deleted with
    -GROUP:all=, which also catches tags exiftool doesn't list individually.
    Otherwise tags are deleted one by one, so protected tags in the same group
    (like Orientation in IFD0) are left alone.
    """
    targets = set(plan.removals)
    args: list[str] = []
    if MAKERNOTES_TARGET in targets:
        args.append("-MakerNotes:all=")

    groups: dict[str, list] = defaultdict(list)
    for tag in meta.tags:
        if tag.family != "MakerNotes":
            groups[tag.group].append(tag)

    for group, tags in groups.items():
        removing = [tag for tag in tags if tag.removal_target in targets]
        if not removing:
            continue
        # Some formats (CR2, for example) refuse to drop a whole EXIF directory,
        # so TIFF-based files always get tag-by-tag deletes.
        tiff_based = tags[0].family == "EXIF" and tags[0].file_type in TIFF_TYPES
        whole_group = (
            not tiff_based
            and len(removing) == len(tags)
            and all(tag.category is Category.METADATA for tag in tags)
        )
        if whole_group:
            args.append(f"-{group}:all=")
        else:
            args.extend(f"-{group}:{tag.name}=" for tag in removing)

    # Photoshop keeps a checksum of the IPTC block. Refresh it when IPTC changes,
    # so other software doesn't treat the remaining IPTC data as out of date.
    iptc_changed = any(
        tag.family == "IPTC" and tag.removal_target in targets for tag in meta.tags
    ) or any(group == "IPTC" for group, _ in plan.edits)
    digest = meta.find("Photoshop", "IPTCDigest")
    if iptc_changed and digest is not None and digest.removal_target not in targets:
        args.append("-Photoshop:IPTCDigest=new")

    for (group, name), value in plan.edits.items():
        problem = validate_edit(group, name, value)
        if problem is not None:
            raise ValueError(problem)
        args.append(f"-{group}:{name}={value}")
    return args


def clean_copy_path(path: Path, suffix: str = DEFAULT_SUFFIX) -> Path:
    """photo.jpg -> photo_clean.jpg, in the same folder."""
    return path.with_stem(f"{path.stem}{suffix}")


def unique_output_path(
    source: Path,
    output_dir: Path | None = None,
    suffix: str = DEFAULT_SUFFIX,
    taken: set[Path] | None = None,
) -> Path:
    """A path for the cleaned copy that doesn't exist yet.

    photo_clean.jpg, then photo_clean-2.jpg, photo_clean-3.jpg and so on.
    `taken` lets a batch reserve names before any file is written.
    """
    folder = output_dir if output_dir is not None else source.parent
    base = folder / clean_copy_path(Path(source.name), suffix)
    candidate = base
    number = 2
    while candidate.exists() or (taken is not None and candidate in taken):
        candidate = base.with_stem(f"{base.stem}-{number}")
        number += 1
    return candidate


@dataclass
class WriteResult:
    source: Path
    destination: Path
    removed: int
    edited: int
    leftovers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return not self.leftovers


def verify_copy(written: FileMetadata, plan: FilePlan) -> list[str]:
    """List every planned change that did not happen in the written copy."""
    problems: list[str] = []
    for tag in written.tags:
        if tag.category is not Category.FILE_INFO and tag.removal_target in plan.removals:
            problems.append(f"{tag.key} is still present")
    for (group, name), value in plan.edits.items():
        tag = written.find(group, name)
        if tag is None or tag.display_value != value:
            problems.append(f"{group}:{name} was not changed")
    return problems


def write_copy(meta: FileMetadata, plan: FilePlan, destination: Path) -> WriteResult:
    """Write a copy of meta.path with the plan applied, then verify it."""
    if destination.exists():
        raise FileExistsError(destination)
    if plan.is_empty:
        raise ValueError("Nothing to change in this file")

    args = build_write_args(meta, plan)
    run = run_exiftool([*args, "-o", str(destination), str(meta.path)])
    if run.returncode != 0 or not destination.exists():
        message = "\n".join(run.errors) or run.stderr.strip() or "exiftool failed"
        if "[minor]" in message:
            message += (
                "\n\nThis file has a small structural problem. Ichnos leaves it "
                "alone rather than risk damaging it further."
            )
        raise ExifToolError(message)

    written = read_tags(destination)
    removed = sum(
        1 for tag in meta.tags
        if tag.category is Category.METADATA and tag.removal_target in plan.removals
    )  # fmt: skip
    return WriteResult(
        source=meta.path,
        destination=destination,
        removed=removed,
        edited=len(plan.edits),
        leftovers=verify_copy(written, plan),
        warnings=run.warnings,
    )
