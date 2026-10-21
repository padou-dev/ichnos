# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: file list, tag table, preview and pending changes."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ichnos.exiftool import ExifToolNotFoundError
from ichnos.gui.dialogs import ResultsDialog, ReviewDialog, show_about
from ichnos.gui.file_list import THUMB_SIZE, FileList
from ichnos.gui.side_panel import SidePanel, load_image
from ichnos.gui.tag_tree import TagTree
from ichnos.gui.theme import ThemeManager
from ichnos.gui.worker import Worker
from ichnos.metadata import (
    SUPPORTED_EXTENSIONS,
    FileMetadata,
    Tag,
    expand_paths,
    read_metadata,
    validate_edit,
)
from ichnos.presets import Preset
from ichnos.writer import DEFAULT_SUFFIX, FilePlan, plan_for_file, unique_output_path, write_copy

MULTILINE_TAGS = {"ImageDescription", "Description", "Caption-Abstract", "Comment"}
IMAGE_FILTER = "Images ({});;All files (*)".format(
    " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
)


class MainWindow(QMainWindow):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__()
        self.theme = theme
        self.settings = QSettings()
        self.setWindowTitle("Ichnos")
        self.setAcceptDrops(True)
        self.resize(1360, 820)

        self.files: dict[Path, FileMetadata] = {}
        self.preset = Preset.SHARE_SAFE
        self.overrides: dict[tuple[str, str], bool] = {}
        self.edits: dict[Path, dict[tuple[str, str], str]] = {}
        self.focused: Path | None = None
        self._workers: list[Worker] = []
        self._exiftool_warned = False

        saved = self.settings.value("preset", Preset.SHARE_SAFE.value)
        if saved in {p.value for p in Preset}:
            self.preset = Preset(saved)

        self._build_actions()
        self._build_toolbar()
        self._build_body()
        self._build_status_bar()

        theme.changed.connect(self._apply_theme)
        self._apply_theme()
        self._restore_layout()
        self._refresh()

    # Layout ------------------------------------------------------------------

    def _action(self, text: str, slot, shortcut=None, tip: str = "") -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        if tip:
            action.setStatusTip(tip)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        self.open_files_action = self._action(
            "&Open Files…", self.choose_files, QKeySequence.StandardKey.Open
        )
        self.open_folder_action = self._action("Open &Folder…", self.choose_folder, "Ctrl+Shift+O")
        self.remove_action = self._action(
            "&Remove from List",
            lambda: self.remove_files(self.file_list.selected_paths()),
            "Delete",
        )
        self.remove_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.clear_action = self._action("&Clear List", lambda: self.remove_files(list(self.files)))
        self.quit_action = self._action("&Quit", self.close, QKeySequence.StandardKey.Quit)

        self.select_all_action = self._action(
            "Tick &All Files",
            lambda: self.file_list.set_all_checked(True),
            QKeySequence.StandardKey.SelectAll,
        )
        self.select_none_action = self._action(
            "Untick All Files", lambda: self.file_list.set_all_checked(False), "Ctrl+Shift+A"
        )
        self.edit_tag_action = self._action("&Edit Tag Value…", self._edit_current_tag, "F2")
        self.focus_filter_action = self._action(
            "&Filter Tags", lambda: self.filter_edit.setFocus(), QKeySequence.StandardKey.Find
        )

        self.preset_actions = QActionGroup(self)
        self.preset_actions.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        for number, preset in enumerate(Preset, start=1):
            action = self._action(
                preset.label,
                lambda _checked=False, p=preset: self.set_preset(p),
                f"Ctrl+{number}",
                preset.description,
            )
            action.setCheckable(True)
            self.preset_actions.addAction(action)

        self.review_action = self._action("&Review Changes…", self.review, "Ctrl+R")
        self.write_action = self._action("&Write Copies", self.write_copies, "Ctrl+Return")
        self.about_action = self._action("&About Ichnos", lambda: show_about(self))

        menu = self.menuBar()
        file_menu = menu.addMenu("&File")
        for action in (self.open_files_action, self.open_folder_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.remove_action)
        file_menu.addAction(self.clear_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = menu.addMenu("&Edit")
        for action in (self.select_all_action, self.select_none_action):
            edit_menu.addAction(action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.edit_tag_action)
        edit_menu.addAction(self.focus_filter_action)

        preset_menu = menu.addMenu("&Preset")
        for action in self.preset_actions.actions():
            preset_menu.addAction(action)

        actions_menu = menu.addMenu("&Actions")
        actions_menu.addAction(self.review_action)
        actions_menu.addAction(self.write_action)

        help_menu = menu.addMenu("&Help")
        help_menu.addAction(self.about_action)

    def _build_toolbar(self) -> None:
        bar = QToolBar("Main")
        bar.setMovable(False)
        bar.setObjectName("mainToolbar")
        self.addToolBar(bar)

        name = QLabel("ichnos")
        name.setObjectName("appName")
        name.setContentsMargins(6, 0, 12, 0)
        bar.addWidget(name)
        self.location_label = QLabel()
        self.location_label.setObjectName("dim")
        bar.addWidget(self.location_label)
        self.count_label = QLabel()
        self.count_label.setContentsMargins(12, 0, 0, 0)
        bar.addWidget(self.count_label)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        bar.addWidget(QLabel("Preset "))
        self.preset_buttons: list[QToolButton] = []  # "Custom" means none is checked
        for number, preset in enumerate(Preset, start=1):
            button = QToolButton()
            button.setObjectName("preset")
            button.setText(preset.label)
            button.setCheckable(True)
            button.setToolTip(f"{preset.description}\nShortcut: Ctrl+{number}")
            button.clicked.connect(lambda _checked=False, p=preset: self.set_preset(p))
            self.preset_buttons.append(button)
            bar.addWidget(button)
        self.custom_button = QToolButton()
        self.custom_button.setObjectName("preset")
        self.custom_button.setText("Custom")
        self.custom_button.setCheckable(True)
        self.custom_button.setEnabled(False)
        self.custom_button.setToolTip(
            "Shown when you tick or untick tags by hand. Pick a preset to start over."
        )
        bar.addWidget(self.custom_button)

        bar.addSeparator()
        self.review_button = QPushButton("Review changes")
        self.review_button.clicked.connect(self.review)
        bar.addWidget(self.review_button)
        self.write_button = QPushButton("Write copies")
        self.write_button.setObjectName("primary")
        self.write_button.clicked.connect(self.write_copies)
        bar.addWidget(self.write_button)

    def _build_body(self) -> None:
        self.file_list = FileList()
        self.file_list.focused.connect(self._on_focus)
        self.file_list.selection_changed.connect(self._refresh)
        self.file_list.remove_requested.connect(self.remove_files)
        self.remove_action.setParent(self.file_list)
        self.file_list.addAction(self.remove_action)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 10, 4, 8)
        files_heading = QLabel("FILES")
        files_heading.setObjectName("heading")
        left_layout.addWidget(files_heading)
        left_layout.addWidget(self.file_list)

        # Centre: an empty state until files are opened, then the tag table.
        self.center = QStackedWidget()
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch(1)
        message = QLabel(
            "<h2>Open photos to see what they reveal</h2>"
            "<p>Drop files or folders here, or use the buttons below.</p>"
        )
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(message)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        open_files = QPushButton("Open files…")
        open_files.setObjectName("primary")
        open_files.clicked.connect(self.choose_files)
        open_folder = QPushButton("Open folder…")
        open_folder.clicked.connect(self.choose_folder)
        buttons.addWidget(open_files)
        buttons.addWidget(open_folder)
        buttons.addStretch(1)
        empty_layout.addLayout(buttons)
        empty_layout.addStretch(2)
        self.center.addWidget(empty)

        tags_page = QWidget()
        tags_layout = QVBoxLayout(tags_page)
        tags_layout.setContentsMargins(4, 10, 4, 8)
        header = QHBoxLayout()
        self.file_title = QLabel()
        title_font = self.file_title.font()
        title_font.setBold(True)
        self.file_title.setFont(title_font)
        self.file_subtitle = QLabel()
        self.file_subtitle.setObjectName("dim")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter tags or values")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMaximumWidth(260)
        self.filter_edit.textChanged.connect(lambda text: self.tag_tree.set_filter(text))
        header.addWidget(self.file_title)
        header.addWidget(self.file_subtitle)
        header.addStretch(1)
        header.addWidget(self.filter_edit)
        tags_layout.addLayout(header)

        self.tag_tree = TagTree()
        self.tag_tree.removal_toggled.connect(self._on_removal_toggled)
        self.tag_tree.group_toggled.connect(self._on_group_toggled)
        self.tag_tree.edit_requested.connect(self.edit_tag)
        tags_layout.addWidget(self.tag_tree)
        hint = QLabel("Ticked tags are removed from the copies. Protected tags are always kept.")
        hint.setObjectName("dim")
        tags_layout.addWidget(hint)
        self.center.addWidget(tags_page)

        self.side_panel = SidePanel()

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.center)
        self.splitter.addWidget(self.side_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([270, 760, 320])
        self.setCentralWidget(self.splitter)

    def _build_status_bar(self) -> None:
        status = self.statusBar()
        hints = QLabel(
            "Space: tick tag · F2: edit · Ctrl+1/2/3: preset · Ctrl+R: review · Ctrl+Enter: write"
        )
        hints.setObjectName("dim")
        status.addPermanentWidget(hints)

    def _apply_theme(self) -> None:
        colors = self.theme.colors
        self.tag_tree.set_colors(colors)
        self.side_panel.set_colors(colors)
        self._refresh()

    def _restore_layout(self) -> None:
        geometry = self.settings.value("geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        splitter = self.settings.value("splitter")
        if isinstance(splitter, QByteArray):
            self.splitter.restoreState(splitter)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if any(worker.isRunning() for worker in self._workers):
            QMessageBox.information(
                self, "Still working", "Please wait until Ichnos finishes writing."
            )
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        self.settings.setValue("preset", self.preset.value)
        super().closeEvent(event)

    # Opening files -------------------------------------------------------------

    def choose_files(self) -> None:
        start = str(self.settings.value("last_dir", str(Path.home())))
        names, _ = QFileDialog.getOpenFileNames(self, "Open photos", start, IMAGE_FILTER)
        if names:
            self.settings.setValue("last_dir", str(Path(names[0]).parent))
            self.add_files([Path(name) for name in names])

    def choose_folder(self) -> None:
        start = str(self.settings.value("last_dir", str(Path.home())))
        folder = QFileDialog.getExistingDirectory(self, "Open folder", start)
        if folder:
            self.settings.setValue("last_dir", folder)
            paths = expand_paths([folder])
            if not paths:
                QMessageBox.information(
                    self, "No photos found", f"There are no supported images in\n{folder}"
                )
                return
            self.add_files(paths)

    def add_files(self, paths: list[Path]) -> None:
        new = [p for p in paths if p.absolute() not in self.files]
        if not new:
            if paths:
                self.file_list.focus_path(paths[0].absolute())
            return

        def job(progress):
            result = read_metadata(new, progress=progress)
            thumbnails = {meta.path: load_image(meta.path, THUMB_SIZE * 2) for meta in result.files}
            return result, thumbnails

        self.statusBar().showMessage(f"Reading {len(new)} file{'s' if len(new) != 1 else ''}…")
        worker = self._start(job)
        worker.progressed.connect(
            lambda done, total: self.statusBar().showMessage(f"Reading files… {done} of {total}")
        )
        worker.succeeded.connect(self._files_loaded)

    def _files_loaded(self, payload) -> None:
        result, thumbnails = payload
        first = None
        for meta in result.files:
            self.files[meta.path] = meta
            self.file_list.add(meta, thumbnails.get(meta.path))
            first = first or meta.path
        self.statusBar().showMessage(f"Opened {len(result.files)} files", 4000)
        if result.failures:
            lines = "\n".join(f"{p.name}: {msg}" for p, msg in list(result.failures.items())[:15])
            more = len(result.failures) - 15
            if more > 0:
                lines += f"\n…and {more} more"
            QMessageBox.warning(self, "Some files could not be read", lines)
        if self.focused is None and first is not None:
            self.file_list.focus_path(first)
        self._refresh()

    def remove_files(self, paths: list[Path]) -> None:
        self.file_list.remove(paths)
        for path in paths:
            self.files.pop(path, None)
            self.edits.pop(path, None)
            self.side_panel.forget(path)
        if self.focused in paths:
            self.focused = None
            remaining = self.file_list.paths()
            if remaining:
                self.file_list.focus_path(remaining[0])
            else:
                self._on_focus(None)
        self._refresh()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        local = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        paths = expand_paths(local)
        if paths:
            self.add_files(paths)
            event.acceptProposedAction()

    # Background work ---------------------------------------------------------

    def _start(self, job) -> Worker:
        worker = Worker(job, self)
        worker.failed.connect(self._worker_failed)
        worker.finished.connect(
            lambda: self._workers.remove(worker) if worker in self._workers else None
        )
        worker.finished.connect(worker.deleteLater)
        self._workers.append(worker)
        worker.start()
        return worker

    def _worker_failed(self, error: Exception) -> None:
        self.statusBar().clearMessage()
        if isinstance(error, ExifToolNotFoundError):
            QMessageBox.critical(self, "exiftool not found", str(error))
        else:
            QMessageBox.critical(self, "Something went wrong", str(error))

    # Plans ---------------------------------------------------------------------

    def plan_for(self, path: Path) -> FilePlan:
        return plan_for_file(self.files[path], self.preset, self.overrides, self.edits.get(path))

    def set_preset(self, preset: Preset) -> None:
        self.preset = preset
        self.overrides.clear()
        self._refresh()

    def _on_removal_toggled(self, target, remove: bool) -> None:
        self.overrides[target] = remove
        self._refresh()

    def _on_group_toggled(self, targets, remove: bool) -> None:
        for target in targets:
            self.overrides[target] = remove
        self._refresh()

    def _edit_current_tag(self) -> None:
        tag = self.tag_tree.current_tag()
        if tag is not None and tag.editable:
            self.edit_tag(tag)
        elif self.focused is not None:
            self.statusBar().showMessage(
                "Select an editable tag first (Artist, Copyright, dates, descriptions)", 4000
            )

    def edit_tag(self, tag: Tag) -> None:
        if self.focused is None:
            return
        file_edits = self.edits.setdefault(self.focused, {})
        current = file_edits.get((tag.group, tag.name), tag.display_value)
        label = f"New value for {tag.key}\nApplies to {self.focused.name} only."
        if tag.name in MULTILINE_TAGS:
            value, ok = QInputDialog.getMultiLineText(self, f"Edit {tag.name}", label, current)
        else:
            value, ok = QInputDialog.getText(
                self, f"Edit {tag.name}", label, QLineEdit.EchoMode.Normal, current
            )
        if not ok:
            return
        problem = validate_edit(tag.group, tag.name, value.strip())
        if problem is not None:
            QMessageBox.warning(self, "Can't use that value", problem)
            return
        if value.strip() == tag.display_value:
            file_edits.pop((tag.group, tag.name), None)
        else:
            file_edits[(tag.group, tag.name)] = value.strip()
            self.overrides[tag.removal_target] = False  # editing a tag means keeping it
        self._refresh()

    # Refreshing the view -------------------------------------------------------

    def _on_focus(self, path: Path | None) -> None:
        self.focused = path
        meta = self.files.get(path) if path is not None else None
        plan = self.plan_for(path) if meta is not None else FilePlan()
        self.tag_tree.show_file(meta, plan)
        self._refresh()

    def _refresh(self) -> None:
        """Bring every part of the window up to date with the current state."""
        has_files = bool(self.files)
        self.center.setCurrentIndex(1 if has_files else 0)

        checked = [p for p in self.file_list.checked_paths() if p in self.files]
        changing = [p for p in checked if not self.plan_for(p).is_empty]

        custom = bool(self.overrides)
        for button, preset in zip(self.preset_buttons, Preset):
            button.setChecked(not custom and preset is self.preset)
        for action, preset in zip(self.preset_actions.actions(), Preset):
            action.setChecked(not custom and preset is self.preset)
        self.custom_button.setChecked(custom)

        n = len(changing)
        self.write_button.setText(
            f"Write {n} cop{'y' if n == 1 else 'ies'}" if n else "Write copies"
        )
        for widget in (self.write_button, self.write_action):
            widget.setEnabled(bool(changing))
        self.review_button.setEnabled(bool(checked))
        self.review_action.setEnabled(bool(checked))
        self.count_label.setText(f"{len(checked)} of {len(self.files)} ticked" if has_files else "")

        folders = {p.parent for p in self.files}
        if len(folders) == 1:
            folder = next(iter(folders))
            self.location_label.setText(str(folder).replace(str(Path.home()), "~", 1))
            self.setWindowTitle(f"{folder.name} — Ichnos")
        else:
            self.location_label.setText(f"{len(folders)} folders" if folders else "")
            self.setWindowTitle("Ichnos")

        meta = self.files.get(self.focused) if self.focused is not None else None
        plan = self.plan_for(self.focused) if meta is not None else FilePlan()
        if meta is not None:
            removable = len(meta.removable)
            self.file_title.setText(meta.path.name)
            self.file_subtitle.setText(
                f"{meta.file_type} · {meta.file_size} · {len(meta.embedded)} embedded tags, {removable} removable"
            )
        else:
            self.file_title.setText("")
            self.file_subtitle.setText("")
        self.tag_tree.apply_plan(plan)
        self.side_panel.show_summary(meta, plan, len(checked), len(changing))

    # Writing ---------------------------------------------------------------------

    def _checked_plans(self) -> list[tuple[FileMetadata, FilePlan]]:
        return [
            (self.files[p], self.plan_for(p))
            for p in self.file_list.checked_paths()
            if p in self.files
        ]

    def review(self) -> None:
        items = self._checked_plans()
        if not items:
            return
        if ReviewDialog(items, self).exec():
            self.write_copies()

    def write_copies(self) -> None:
        jobs = [(meta, plan) for meta, plan in self._checked_plans() if not plan.is_empty]
        if not jobs:
            QMessageBox.information(
                self, "Nothing to write", "None of the ticked files has anything to remove or edit."
            )
            return

        def job(progress):
            results, failures, taken = [], {}, set()
            for index, (meta, plan) in enumerate(jobs, start=1):
                destination = unique_output_path(meta.path, None, DEFAULT_SUFFIX, taken)
                taken.add(destination)
                try:
                    results.append(write_copy(meta, plan, destination))
                except Exception as error:  # noqa: BLE001 - reported per file
                    failures[meta.path] = str(error)
                progress(index, len(jobs))
            return results, failures

        dialog = QProgressDialog(self)
        dialog.setWindowTitle("Ichnos")
        dialog.setLabelText("Writing cleaned copies…")
        dialog.setRange(0, len(jobs))
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setValue(0)

        worker = self._start(job)
        worker.progressed.connect(lambda done, _total: dialog.setValue(done))
        worker.succeeded.connect(lambda payload: self._written(payload, dialog))
        worker.failed.connect(lambda _error: dialog.close())

    def _written(self, payload, dialog: QProgressDialog) -> None:
        dialog.close()
        results, failures = payload
        self.statusBar().showMessage(f"Wrote {len(results)} copies", 6000)
        results_dialog = ResultsDialog(results, failures, self)
        results_dialog.exec()
        if results_dialog.inspect_requested:
            self.add_files([r.destination for r in results])
