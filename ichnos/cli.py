# SPDX-License-Identifier: GPL-3.0-or-later
"""The command-line interface: `ichnos show` and `ichnos strip`."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ichnos import __version__
from ichnos.exiftool import IchnosError
from ichnos.metadata import Category, FileMetadata, Tag, expand_paths, read_metadata
from ichnos.presets import Preset, has_location, privacy_reason
from ichnos.writer import DEFAULT_SUFFIX, plan_for_file, unique_output_path, write_copy

COMMANDS = ("open", "show", "strip", "presets")
VALUE_WIDTH = 60


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ichnos",
        description="View, edit and remove photo metadata, safely.",
        epilog="Run without a command to open the app: ichnos [FILE ...]",
    )
    parser.add_argument("--version", action="version", version=f"ichnos {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    open_cmd = commands.add_parser("open", help="open files in the app (the default)")
    open_cmd.add_argument("files", nargs="*", metavar="FILE")

    show = commands.add_parser("show", help="list the metadata in files")
    show.add_argument("files", nargs="+", metavar="FILE")
    show.add_argument(
        "-a", "--all", action="store_true",
        help="also list file-system details and values exiftool calculates",
    )  # fmt: skip
    show.add_argument("-r", "--recursive", action="store_true", help="look inside subfolders")

    strip = commands.add_parser(
        "strip",
        help="write cleaned copies of files",
        description="Write a cleaned copy of each file. Originals are never modified.",
    )
    strip.add_argument("files", nargs="+", metavar="FILE")
    strip.add_argument(
        "-p", "--preset", choices=[p.value for p in Preset], default=Preset.SHARE_SAFE.value,
        help="what to remove (default: share-safe). See `ichnos presets`.",
    )  # fmt: skip
    strip.add_argument(
        "-o", "--output-dir", type=Path, help="write copies here instead of next to the originals"
    )
    strip.add_argument(
        "-s",
        "--suffix",
        default=DEFAULT_SUFFIX,
        help=f"added to copy names (default: {DEFAULT_SUFFIX})",
    )
    strip.add_argument(
        "-n", "--dry-run", action="store_true", help="show what would be removed, write nothing"
    )
    strip.add_argument("-r", "--recursive", action="store_true", help="look inside subfolders")

    commands.add_parser("presets", help="describe the presets")
    return parser


def _one_line(text: str, width: int = VALUE_WIDTH) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _marker(tag: Tag) -> str:
    if tag.category is Category.PROTECTED:
        return "[kept]"
    reason = privacy_reason(tag)
    return f"[{reason.value}]" if reason is not None else ""


def _summary(meta: FileMetadata) -> str:
    parts = [
        meta.file_type or "unknown type",
        meta.file_size,
        f"{len(meta.embedded)} embedded tags",
    ]
    if has_location(meta):
        parts.append("location present")
    return " · ".join(part for part in parts if part)


def show_file(meta: FileMetadata, include_file_info: bool) -> None:
    print(f"{meta.path}  ({_summary(meta)})")
    groups: dict[str, list[Tag]] = defaultdict(list)
    for tag in meta.tags:
        if tag.category is Category.FILE_INFO and not include_file_info:
            continue
        groups[tag.group_label].append(tag)
    if not groups:
        print("  No embedded metadata.")
    shown = [tag for tags in groups.values() for tag in tags]
    name_width = min(max((len(t.name) for t in shown), default=0), 32)
    value_width = min(max((len(_one_line(t.display_value)) for t in shown), default=0), VALUE_WIDTH)
    for label, tags in groups.items():
        print(f"  {label}")
        for tag in tags:
            value = _one_line(tag.display_value)
            line = f"    {tag.name:<{name_width}}  {value:<{value_width}}  {_marker(tag)}"
            print(line.rstrip())
    for warning in meta.warnings:
        print(f"  Warning: {warning}")
    print()


def _reason_counts(meta: FileMetadata, removals: dict) -> str:
    counts = Counter(
        reason.value for target, reason in removals.items()
        for tag in meta.removable if tag.removal_target == target
    )  # fmt: skip
    return ", ".join(f"{name} {count}" for name, count in counts.most_common())


def command_show(args: argparse.Namespace) -> int:
    paths = expand_paths(args.files, recursive=args.recursive)
    if not paths:
        print("No files found.", file=sys.stderr)
        return 1
    result = read_metadata(paths)
    for meta in result.files:
        show_file(meta, args.all)
    for path, message in result.failures.items():
        print(f"{path}: {message}", file=sys.stderr)
    return 1 if result.failures else 0


def command_strip(args: argparse.Namespace) -> int:
    paths = expand_paths(args.files, recursive=args.recursive)
    if not paths:
        print("No files found.", file=sys.stderr)
        return 1
    if args.output_dir is not None and not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    preset = Preset(args.preset)
    result = read_metadata(paths)
    written = skipped = failed = 0
    taken: set[Path] = set()

    for path, message in result.failures.items():
        print(f"{path}: error: {message}", file=sys.stderr)
        failed += 1

    for meta in result.files:
        plan = plan_for_file(meta, preset)
        if plan.is_empty:
            print(f"{meta.path}: nothing to remove, skipped")
            skipped += 1
            continue
        count = sum(1 for tag in meta.removable if tag.removal_target in plan.removals)
        if args.dry_run:
            print(f"{meta.path}: would remove {count} tags ({_reason_counts(meta, plan.removals)})")
            for tag in meta.removable:
                if tag.removal_target in plan.removals:
                    reason = plan.removals[tag.removal_target].value
                    print(f"    {tag.key:<40} {reason}")
            continue

        destination = unique_output_path(meta.path, args.output_dir, args.suffix, taken)
        taken.add(destination)
        try:
            outcome = write_copy(meta, plan, destination)
        except (IchnosError, OSError, ValueError) as error:
            print(f"{meta.path}: error: {error}", file=sys.stderr)
            failed += 1
            continue
        written += 1
        status = "verified" if outcome.verified else "NOT fully cleaned"
        print(
            f"{meta.path} -> {destination.name}: removed {count} tags "
            f"({_reason_counts(meta, plan.removals)}), {status}"
        )
        for problem in outcome.leftovers:
            print(f"    warning: {problem}", file=sys.stderr)
        if not outcome.verified:
            failed += 1

    if not args.dry_run:
        print(f"\n{written} written, {skipped} skipped, {failed} with problems.")
    return 1 if failed else 0


def command_presets() -> int:
    for preset in Preset:
        print(f"{preset.value:<12} {preset.description}")
    print("\nAlways kept: orientation, colour profile and image structure.")
    return 0


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    args = build_parser().parse_args(argv)
    try:
        if args.command == "show":
            return command_show(args)
        if args.command == "strip":
            return command_strip(args)
        if args.command == "presets":
            return command_presets()
    except IchnosError as error:
        print(f"ichnos: {error}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # Output was piped into something like `head` that stopped reading.
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        return 0

    from ichnos.gui.app import run  # "open", or no command at all

    return run(getattr(args, "files", None) or [])
