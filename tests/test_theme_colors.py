# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for reading Omarchy theme colours. These need no exiftool and no Qt."""

from pathlib import Path

import pytest

from ichnos.theme_colors import load_theme_colors, mix, normalise_hex, omarchy_theme_dir


@pytest.fixture(autouse=True)
def _require_exiftool() -> None:
    """Override the exiftool check from conftest: these tests don't need it."""


def test_normalise_hex() -> None:
    assert normalise_hex("#1A1B26") == "#1a1b26"
    assert normalise_hex("0x1a1b26") == "#1a1b26"
    assert normalise_hex("'#1a1b26'") == "#1a1b26"
    assert normalise_hex("blue") is None


def test_mix() -> None:
    assert mix("#000000", "#ffffff", 0.5) == "#808080"


def test_reads_alacritty(tmp_path: Path) -> None:
    (tmp_path / "alacritty.toml").write_text(
        "[colors.primary]\nbackground = '#1a1b26'\nforeground = '#a9b1d6'\n"
        "[colors.normal]\nblue = '#7aa2f7'\nyellow = '#e0af68'\ngreen = '#9ece6a'\nred = '#f7768e'\n"
    )
    colors = load_theme_colors(tmp_path)
    assert colors.background == "#1a1b26"
    assert colors.accent == "#7aa2f7"
    assert colors.warning == "#e0af68"
    assert colors.is_dark


def test_reads_ghostty(tmp_path: Path) -> None:
    (tmp_path / "ghostty.conf").write_text(
        "background = 1b1220\nforeground = f5dceb\npalette = 4=#ff5fae\npalette = 3=#ffb86b\n"
    )
    colors = load_theme_colors(tmp_path)
    assert colors.background == "#1b1220"
    assert colors.accent == "#ff5fae"


def test_colors_toml_wins_and_accent_is_used(tmp_path: Path) -> None:
    (tmp_path / "colors.toml").write_text(
        'background = "#fafafa"\nforeground = "#202020"\naccent = "#ff5fae"\n'
    )
    (tmp_path / "alacritty.toml").write_text(
        "[colors.primary]\nbackground = '#000000'\nforeground = '#ffffff'\n"
    )
    colors = load_theme_colors(tmp_path)
    assert colors.accent == "#ff5fae"
    assert not colors.is_dark


def test_broken_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "colors.toml").write_text("this is [not toml")
    (tmp_path / "kitty.conf").write_text("background #101010\nforeground #eeeeee\ncolor4 #3366ff\n")
    assert load_theme_colors(tmp_path).accent == "#3366ff"


def test_no_theme_folder_means_no_colours(tmp_path: Path) -> None:
    assert load_theme_colors(None) is None
    assert load_theme_colors(tmp_path / "missing") is None


def test_theme_dir_can_be_overridden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_THEME_DIR", str(tmp_path))
    assert omarchy_theme_dir() == tmp_path
