# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke tests for the window, run without a screen (Qt's "offscreen" platform).

They build the real widgets and drive them the way a user would, without
opening anything on your desktop. Skipped when PySide6 isn't installed.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtCore = pytest.importorskip("PySide6.QtCore")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from ichnos.gui.dialogs import ResultsDialog, ReviewDialog  # noqa: E402
from ichnos.gui.main_window import MainWindow  # noqa: E402
from ichnos.gui.tag_tree import TAG_ROLE  # noqa: E402
from ichnos.gui.theme import ThemeManager  # noqa: E402
from ichnos.metadata import read_metadata  # noqa: E402
from ichnos.presets import Preset  # noqa: E402
from ichnos.writer import unique_output_path, write_copy  # noqa: E402

Qt = QtCore.Qt


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ICHNOS_THEME_DIR", str(tmp_path / "no-theme"))
    settings_dir = tmp_path / "settings"
    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    QtCore.QSettings.setPath(
        QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, str(settings_dir)
    )
    QtWidgets.QApplication.setOrganizationName("IchnosTests")
    QtWidgets.QApplication.setApplicationName("IchnosTests")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(app, tagged_jpeg: Path, plain_jpeg: Path):
    theme = ThemeManager(app)
    theme.apply()
    win = MainWindow(theme)
    win.preset = Preset.SHARE_SAFE
    win.show()
    result = read_metadata([tagged_jpeg, plain_jpeg])
    win._files_loaded((result, {}))  # what the background reader delivers
    yield win
    win.close()


def tag_item(win: MainWindow, key: str):
    for item, tag in win.tag_tree._tag_items():
        if tag.key == key:
            return item
    raise AssertionError(f"{key} not in the table")


def test_files_are_listed_and_the_first_is_shown(window: MainWindow, tagged_jpeg: Path) -> None:
    assert window.file_list.count() == 2
    assert window.focused == tagged_jpeg.absolute()
    assert window.center.currentIndex() == 1
    assert "sample.jpg" in window.file_title.text()


def test_share_safe_ticks_private_tags_and_protects_orientation(window: MainWindow) -> None:
    gps = tag_item(window, "GPS:GPSLatitude")
    make = tag_item(window, "IFD0:Make")
    orientation = tag_item(window, "IFD0:Orientation")
    assert gps.checkState(0) == Qt.CheckState.Checked
    assert make.checkState(0) == Qt.CheckState.Unchecked
    assert orientation.text(2) == "protected"
    assert not (orientation.flags() & Qt.ItemFlag.ItemIsUserCheckable)


def test_only_files_with_changes_count_towards_writing(window: MainWindow) -> None:
    # plain.jpg has nothing to remove, so only one copy will be written
    assert window.write_button.text() == "Write 1 copy"
    assert window.write_button.isEnabled()


def test_presets_change_what_is_ticked(window: MainWindow) -> None:
    window.set_preset(Preset.LOCATION)
    assert tag_item(window, "IFD0:Artist").checkState(0) == Qt.CheckState.Unchecked
    window.set_preset(Preset.STRIP_ALL)
    assert tag_item(window, "IFD0:Make").checkState(0) == Qt.CheckState.Checked


def test_ticking_a_tag_by_hand_switches_to_custom(window: MainWindow, tagged_jpeg: Path) -> None:
    tag_item(window, "IFD0:Make").setCheckState(0, Qt.CheckState.Checked)
    assert window.custom_button.isChecked()
    assert ("IFD0", "Make") in window.plan_for(tagged_jpeg.absolute()).removals
    window.set_preset(Preset.SHARE_SAFE)
    assert not window.custom_button.isChecked()


def test_group_checkbox_ticks_the_whole_group(window: MainWindow) -> None:
    window.set_preset(Preset.LOCATION)
    group = tag_item(window, "IFD0:Make").parent()
    group.setCheckState(0, Qt.CheckState.Checked)
    assert tag_item(window, "IFD0:Artist").checkState(0) == Qt.CheckState.Checked
    assert tag_item(window, "IFD0:Orientation").text(2) == "protected"


def test_unticking_a_file_leaves_it_out(window: MainWindow) -> None:
    window.file_list.set_all_checked(False)
    assert not window.write_button.isEnabled()
    assert window._checked_plans() == []


def test_filter_hides_rows(window: MainWindow) -> None:
    window.filter_edit.setText("GPSLat")
    assert not tag_item(window, "GPS:GPSLatitude").isHidden()
    assert tag_item(window, "IFD0:Make").isHidden()


def test_removing_a_file_from_the_list(window: MainWindow, plain_jpeg: Path) -> None:
    window.remove_files([plain_jpeg.absolute()])
    assert window.file_list.count() == 1
    assert plain_jpeg.absolute() not in window.files


def test_dialogs_build(window: MainWindow, tagged_jpeg: Path) -> None:
    items = window._checked_plans()
    review = ReviewDialog(items, window)
    review.close()
    meta, plan = items[0]
    result = write_copy(meta, plan, unique_output_path(meta.path))
    results = ResultsDialog([result], {Path("broken.jpg"): "could not read"}, window)
    results.close()
    assert result.verified


def test_tag_data_survives_in_items(window: MainWindow) -> None:
    item = tag_item(window, "GPS:GPSLatitude")
    assert item.data(0, TAG_ROLE).group == "GPS"


def test_omarchy_theme_is_applied(app, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    theme_dir = tmp_path / "omarchy"
    theme_dir.mkdir()
    (theme_dir / "alacritty.toml").write_text(
        "[colors.primary]\nbackground = '#1a1b26'\nforeground = '#c0caf5'\n"
        "[colors.normal]\nblue = '#7aa2f7'\n"
    )
    monkeypatch.setenv("ICHNOS_THEME_DIR", str(theme_dir))
    theme = ThemeManager(app)
    theme.apply()
    try:
        assert theme.from_omarchy
        window_color = app.palette().color(app.palette().ColorRole.Window).name()
        assert window_color == "#1a1b26"
    finally:
        monkeypatch.setenv("ICHNOS_THEME_DIR", str(tmp_path / "none"))
        theme.apply()


def test_ichnos_palette_is_used_without_omarchy(window: MainWindow, app) -> None:
    from ichnos.theme_colors import DEFAULT_DARK, DEFAULT_LIGHT

    assert not window.theme.from_omarchy
    background = app.palette().color(app.palette().ColorRole.Window).name()
    assert background in (DEFAULT_DARK.background, DEFAULT_LIGHT.background)


def test_groups_with_nothing_removable_start_collapsed(window: MainWindow) -> None:
    window.file_list.focus_path(window.file_list.paths()[1])  # plain.jpg: only JFIF
    jfif = window.tag_tree.topLevelItem(0)
    assert jfif.text(0) == "JFIF"
    assert not jfif.isExpanded()
    assert "kept" in jfif.text(2)
    window.file_list.focus_path(window.file_list.paths()[0])
    assert tag_item(window, "GPS:GPSLatitude").parent().isExpanded()
