# SPDX-License-Identifier: GPL-3.0-or-later
"""The tag table: one row per tag, grouped, with a remove checkbox on each."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QKeyEvent
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTreeWidget, QTreeWidgetItem

from ichnos.metadata import Category, FileMetadata, Tag
from ichnos.theme_colors import ThemeColors
from ichnos.writer import FilePlan

TAG_ROLE = Qt.ItemDataRole.UserRole
FILE_INFO_LABEL = "File info (not stored in the image)"
COL_TAG, COL_VALUE, COL_STATUS = 0, 1, 2


class TagTree(QTreeWidget):
    """Shows one file's tags and reports the user's remove/edit choices."""

    removal_toggled = Signal(object, bool)  # removal target, remove?
    group_toggled = Signal(object, bool)  # list of removal targets, remove?
    edit_requested = Signal(object)  # Tag

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Tag", "Value", "Status"])
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_TAG, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_VALUE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        self.setColumnWidth(COL_TAG, 260)
        self.setIndentation(16)

        self._colors: ThemeColors | None = None
        self._meta: FileMetadata | None = None
        self._plan = FilePlan()
        self._updating = False
        self._filter = ""

        self.itemChanged.connect(self._on_item_changed)
        self.itemDoubleClicked.connect(self._on_double_click)

    # Building -------------------------------------------------------------

    def set_colors(self, colors: ThemeColors) -> None:
        self._colors = colors
        self.apply_plan(self._plan)

    def show_file(self, meta: FileMetadata | None, plan: FilePlan) -> None:
        """Rebuild the table for a different file."""
        self._updating = True
        self.clear()
        self._meta = meta
        self._plan = plan
        if meta is not None:
            self._build(meta)
        self._updating = False
        self.apply_plan(plan)
        self.set_filter(self._filter)

    def _build(self, meta: FileMetadata) -> None:
        embedded: dict[str, list[Tag]] = defaultdict(list)
        file_info: dict[str, list[Tag]] = defaultdict(list)
        for tag in meta.tags:
            target = file_info if tag.category is Category.FILE_INFO else embedded
            target[tag.group_label].append(tag)

        for label, tags in embedded.items():
            group = QTreeWidgetItem(self, [label, "", ""])
            self._style_group(group)
            for tag in tags:
                self._add_tag(group, tag)
            # Groups with nothing removable (colour profile, image structure)
            # start collapsed, so the table opens on what can actually change.
            group.setExpanded(any(t.category is Category.METADATA for t in tags))

        if file_info:
            outer = QTreeWidgetItem(self, [FILE_INFO_LABEL, "", ""])
            self._style_group(outer)
            outer.setToolTip(
                COL_TAG,
                "Details from your file system and values exiftool calculates. "
                "They are not inside the image, so there is nothing to remove.",
            )
            for label, tags in file_info.items():
                group = QTreeWidgetItem(outer, [label, "", ""])
                self._style_group(group)
                for tag in tags:
                    self._add_tag(group, tag)
                group.setExpanded(True)
            outer.setExpanded(False)

    def _style_group(self, item: QTreeWidgetItem) -> None:
        font = QFont(self.font())  # an item's own font() is the system default, not ours
        font.setBold(True)
        item.setFont(COL_TAG, font)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)

    def _add_tag(self, parent: QTreeWidgetItem, tag: Tag) -> None:
        value = " ".join(tag.display_value.split())
        item = QTreeWidgetItem(parent, [tag.name, value, ""])
        item.setData(COL_TAG, TAG_ROLE, tag)
        item.setToolTip(COL_VALUE, tag.display_value)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if tag.category is Category.METADATA:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
            item.setCheckState(COL_TAG, Qt.CheckState.Unchecked)
            hint = "Tick to remove this tag."
            if tag.editable:
                hint += " Double-click or press F2 to edit it."
            item.setToolTip(COL_TAG, f"{tag.key}\n{hint}")
        elif tag.category is Category.PROTECTED:
            item.setToolTip(COL_TAG, f"{tag.key}\nKept: {tag.protected_reason}.")
        item.setFlags(flags)

    # Updating ---------------------------------------------------------------

    def _tag_items(self):
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            tag = item.data(COL_TAG, TAG_ROLE)
            if tag is not None:
                yield item, tag
            stack.extend(item.child(i) for i in range(item.childCount()))

    def _group_items(self):
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.data(COL_TAG, TAG_ROLE) is None:
                yield item
                stack.extend(item.child(i) for i in range(item.childCount()))

    def apply_plan(self, plan: FilePlan) -> None:
        """Update checkboxes, strike-through and status text without rebuilding."""
        self._plan = plan
        if self._colors is None or self._meta is None:
            return
        c = self._colors
        self._updating = True
        for item, tag in self._tag_items():
            removed = tag.removal_target in plan.removals
            edit = plan.edits.get((tag.group, tag.name))
            font = QFont(self.font())
            font.setStrikeOut(removed)
            item.setFont(COL_VALUE, font)

            if tag.category is Category.FILE_INFO:
                self._paint(item, c.dim, c.dim, "", c.dim)
                continue
            if tag.category is Category.PROTECTED:
                self._paint(item, c.foreground, c.foreground, "protected", c.success)
                continue

            item.setCheckState(
                COL_TAG, Qt.CheckState.Checked if removed else Qt.CheckState.Unchecked
            )
            if removed:
                reason = plan.removals[tag.removal_target].value
                item.setText(COL_VALUE, " ".join(tag.display_value.split()))
                self._paint(item, c.foreground, c.dim, f"remove · {reason}", c.warning)
            elif edit is not None:
                item.setText(COL_VALUE, " ".join(edit.split()))
                self._paint(item, c.foreground, c.accent, "edited", c.accent)
            else:
                item.setText(COL_VALUE, " ".join(tag.display_value.split()))
                self._paint(item, c.foreground, c.foreground, "", c.foreground)

        for group in self._group_items():
            self._update_group(group)
        self._updating = False

    @staticmethod
    def _paint(item, name_color: str, value_color: str, status: str, status_color: str) -> None:
        item.setForeground(COL_TAG, QBrush(QColor(name_color)))
        item.setForeground(COL_VALUE, QBrush(QColor(value_color)))
        item.setText(COL_STATUS, status)
        item.setForeground(COL_STATUS, QBrush(QColor(status_color)))

    def _update_group(self, group: QTreeWidgetItem) -> None:
        tags = [
            group.child(i).data(COL_TAG, TAG_ROLE)
            for i in range(group.childCount())
            if group.child(i).data(COL_TAG, TAG_ROLE) is not None
        ]
        if not tags:
            return
        removable = [t for t in tags if t.category is Category.METADATA]
        removed = [t for t in removable if t.removal_target in self._plan.removals]
        c = self._colors
        for column in (COL_TAG, COL_VALUE, COL_STATUS):
            group.setBackground(column, QBrush(QColor(c.surface)))
        if tags[0].category is Category.FILE_INFO:
            group.setText(COL_STATUS, "not in the image")
            group.setForeground(COL_STATUS, QBrush(QColor(c.dim)))
            group.setForeground(COL_TAG, QBrush(QColor(c.dim)))
            return
        if removable:
            group.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            if not removed:
                state = Qt.CheckState.Unchecked
            elif len(removed) == len(removable):
                state = Qt.CheckState.Checked
            else:
                state = Qt.CheckState.PartiallyChecked
            group.setCheckState(COL_TAG, state)
        noun = "tag" if len(tags) == 1 else "tags"
        if removed:
            status, color = f"{len(removed)} of {len(tags)} removed", c.warning
        elif not removable:
            status, color = f"{len(tags)} {noun} · kept", c.success
        else:
            status, color = f"{len(tags)} {noun}", c.dim
        group.setText(COL_STATUS, status)
        group.setForeground(COL_STATUS, QBrush(QColor(color)))
        group.setForeground(COL_TAG, QBrush(QColor(c.accent)))

    # Filtering -------------------------------------------------------------

    def set_filter(self, text: str) -> None:
        self._filter = text.strip().lower()
        for i in range(self.topLevelItemCount()):
            self._filter_item(self.topLevelItem(i))

    def _filter_item(self, item: QTreeWidgetItem) -> bool:
        """Hide rows that don't match. Returns True if the item stays visible."""
        tag = item.data(COL_TAG, TAG_ROLE)
        if tag is not None:
            haystack = f"{tag.group} {tag.name} {tag.display_value}".lower()
            visible = not self._filter or self._filter in haystack
        else:
            children = [self._filter_item(item.child(i)) for i in range(item.childCount())]
            visible = any(children)
            if self._filter and visible:
                item.setExpanded(True)
        item.setHidden(not visible)
        return visible

    # User actions ----------------------------------------------------------

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != COL_TAG:
            return
        checked = item.checkState(COL_TAG) == Qt.CheckState.Checked
        tag = item.data(COL_TAG, TAG_ROLE)
        if tag is not None:
            if tag.category is Category.METADATA:
                self.removal_toggled.emit(tag.removal_target, checked)
            return
        targets = []
        for i in range(item.childCount()):
            child_tag = item.child(i).data(COL_TAG, TAG_ROLE)
            if child_tag is not None and child_tag.category is Category.METADATA:
                if child_tag.removal_target not in targets:
                    targets.append(child_tag.removal_target)
        if targets:
            self.group_toggled.emit(targets, checked)

    def current_tag(self) -> Tag | None:
        item = self.currentItem()
        return item.data(COL_TAG, TAG_ROLE) if item is not None else None

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        tag = item.data(COL_TAG, TAG_ROLE)
        if tag is not None and tag.editable:
            self.edit_requested.emit(tag)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_F2:
            tag = self.current_tag()
            if tag is not None and tag.editable:
                self.edit_requested.emit(tag)
                return
        super().keyPressEvent(event)
