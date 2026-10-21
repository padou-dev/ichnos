# SPDX-License-Identifier: GPL-3.0-or-later
"""Read colours from an Omarchy theme. Pure Python, no Qt, so it can be tested.

Omarchy 4 keeps the active theme in ~/.local/state/omarchy/current/theme
(Omarchy 3 used ~/.config/omarchy/current/theme; both are checked). Every
Omarchy 4 theme has a colors.toml with named colours. For older or third-party
themes, Ichnos falls back to the Alacritty, Ghostty or Kitty terminal colours.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

THEME_DIR_ENV = "ICHNOS_THEME_DIR"
OMARCHY_THEME_DIRS = (
    ".local/state/omarchy/current/theme",  # Omarchy 4
    ".config/omarchy/current/theme",  # Omarchy 3
)
HEX = re.compile(r"^(?:#|0x)?([0-9a-fA-F]{6})$")


@dataclass(frozen=True)
class ThemeColors:
    background: str
    foreground: str
    accent: str
    warning: str
    success: str
    error: str
    source: str = ""
    panel_color: str = ""  # used instead of the calculated shade when a theme names one
    surface_color: str = ""

    @property
    def is_dark(self) -> bool:
        return luminance(self.background) < 0.5

    @property
    def panel(self) -> str:
        """Lists and tables: a little darker in dark themes, lighter in light ones."""
        if self.panel_color:
            return self.panel_color
        if self.is_dark:
            return mix(self.background, "#000000", 0.18)
        return mix(self.background, "#ffffff", 0.6)

    @property
    def surface(self) -> str:
        if self.surface_color:
            return self.surface_color
        return mix(self.background, self.foreground, 0.08)

    @property
    def border(self) -> str:
        return mix(self.background, self.foreground, 0.18)

    @property
    def dim(self) -> str:
        return mix(self.foreground, self.background, 0.35)

    @property
    def accent_text(self) -> str:
        return "#000000" if luminance(self.accent) > 0.5 else "#ffffff"


# Ichnos's own colours, used when there is no Omarchy theme. The dark one is
# the palette from the original design mockup.
DEFAULT_DARK = ThemeColors(
    background="#1a1b26",
    foreground="#c0caf5",
    accent="#7aa2f7",
    warning="#ff9e64",
    success="#9ece6a",
    error="#f7768e",
    source="Ichnos dark",
)
DEFAULT_LIGHT = ThemeColors(
    background="#eef0f5",
    foreground="#24283b",
    accent="#2e59c7",
    warning="#a84f00",
    success="#2e7d32",
    error="#c62828",
    source="Ichnos light",
)


def normalise_hex(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = HEX.match(value.strip().strip("'\""))
    return f"#{match.group(1).lower()}" if match else None


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def luminance(color: str) -> float:
    r, g, b = _rgb(color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def mix(a: str, b: str, amount: float) -> str:
    """Blend colour a towards colour b by amount (0 to 1)."""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    blend = [round(x + (y - x) * amount) for x, y in ((ra, rb), (ga, gb), (ba, bb))]
    return "#{:02x}{:02x}{:02x}".format(*blend)


def _build(found: dict[str, str], source: str) -> ThemeColors | None:
    background = found.get("background")
    foreground = found.get("foreground")
    if background is None or foreground is None:
        return None
    return ThemeColors(
        background=background,
        foreground=foreground,
        accent=found.get("accent") or found.get("color4") or found.get("blue") or foreground,
        warning=found.get("orange") or found.get("color3") or found.get("yellow") or "#e0a040",
        success=found.get("color2") or found.get("green") or "#60b060",
        error=found.get("color1") or found.get("red") or "#e05050",
        source=source,
        panel_color=found.get("dark_background", ""),
        surface_color=found.get("lighter_background", ""),
    )


def _flatten(table: dict, found: dict[str, str]) -> None:
    for key, value in table.items():
        if isinstance(value, dict):
            _flatten(value, found)
        else:
            color = normalise_hex(value)
            if color is not None:
                found.setdefault(str(key).lower(), color)


def from_colors_toml(path: Path) -> ThemeColors | None:
    found: dict[str, str] = {}
    _flatten(tomllib.loads(path.read_text(encoding="utf-8")), found)
    found.setdefault("background", found.get("bg", ""))
    found.setdefault("foreground", found.get("fg", ""))
    return _build({k: v for k, v in found.items() if v}, path.name)


def from_alacritty(path: Path) -> ThemeColors | None:
    data = tomllib.loads(path.read_text(encoding="utf-8")).get("colors", {})
    found: dict[str, str] = {}
    for section in ("primary", "normal"):
        for key, value in data.get(section, {}).items():
            color = normalise_hex(value)
            if color is not None:
                found.setdefault(key.lower(), color)
    return _build(found, path.name)


def from_ghostty(path: Path) -> ThemeColors | None:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        key, value = key.strip().lower(), value.strip()
        if key == "palette":
            number, _, color = value.partition("=")
            if normalise_hex(color):
                found[f"color{number.strip()}"] = normalise_hex(color)
        elif normalise_hex(value):
            found[key] = normalise_hex(value)
    return _build(found, path.name)


def from_kitty(path: Path) -> ThemeColors | None:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and normalise_hex(parts[1]):
            found[parts[0].lower()] = normalise_hex(parts[1])
    return _build(found, path.name)


READERS = (
    ("colors.toml", from_colors_toml),
    ("alacritty.toml", from_alacritty),
    ("ghostty.conf", from_ghostty),
    ("kitty.conf", from_kitty),
)


def omarchy_theme_dir() -> Path | None:
    """The active Omarchy theme folder, if there is one."""
    override = os.environ.get(THEME_DIR_ENV)
    if override:
        return Path(override)
    if sys.platform in ("win32", "darwin"):
        return None
    for folder in OMARCHY_THEME_DIRS:
        path = Path.home() / folder
        if path.is_dir():
            return path
    return None


def load_theme_colors(folder: Path | None) -> ThemeColors | None:
    if folder is None or not folder.is_dir():
        return None
    for name, reader in READERS:
        path = folder / name
        if not path.is_file():
            continue
        try:
            colors = reader(path)
        except (OSError, ValueError, tomllib.TOMLDecodeError):
            continue
        if colors is not None:
            return colors
    return None
