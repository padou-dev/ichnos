# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the command-line interface."""

from pathlib import Path

import pytest

from ichnos import __version__
from ichnos.cli import main
from ichnos.metadata import read_tags


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_show_lists_tags_and_marks_location(
    tagged_jpeg: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["show", str(tagged_jpeg)]) == 0
    out = capsys.readouterr().out
    assert "location present" in out
    assert "GPSLatitude" in out
    assert "[kept]" in out
    assert "FileSize" not in out


def test_show_all_includes_file_info(tagged_jpeg: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["show", "--all", str(tagged_jpeg)])
    assert "FileSize" in capsys.readouterr().out


def test_strip_writes_a_clean_copy(tagged_jpeg: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["strip", "--preset", "location", str(tagged_jpeg)]) == 0
    copy = tagged_jpeg.with_name("sample_clean.jpg")
    assert read_tags(copy).find("GPS", "GPSLatitude") is None
    assert "verified" in capsys.readouterr().out


def test_strip_dry_run_writes_nothing(
    tagged_jpeg: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["strip", "--dry-run", str(tagged_jpeg)]) == 0
    assert not tagged_jpeg.with_name("sample_clean.jpg").exists()
    assert "would remove" in capsys.readouterr().out


def test_strip_output_dir_and_suffix(tagged_jpeg: Path, tmp_path: Path) -> None:
    out = tmp_path / "shared"
    assert main(["strip", "-o", str(out), "-s", "_web", str(tagged_jpeg)]) == 0
    assert (out / "sample_web.jpg").exists()


def test_strip_skips_files_with_nothing_to_remove(
    plain_jpeg: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["strip", str(plain_jpeg)]) == 0
    assert "nothing to remove" in capsys.readouterr().out


def test_missing_file_gives_an_error_exit_code(tmp_path: Path) -> None:
    assert main(["strip", str(tmp_path / "missing.jpg")]) == 1


def test_presets_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["presets"]) == 0
    assert "share-safe" in capsys.readouterr().out
