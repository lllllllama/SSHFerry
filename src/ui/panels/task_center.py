"""Task center panel for monitoring transfer tasks."""

import time
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.shared.models import Task
from src.ui.theme import TOKENS


MAX_VISIBLE_TASKS = 50


class TaskCenterPanel(QWidget):
    """Panel for displaying and managing transfer tasks."""

    request_pause = Signal(str)
    request_resume = Signal(str)
    request_cancel = Signal(str)
    request_restart = Signal(str)
    request_clear_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks: dict[str, Task] = {}
        self._last_signature: tuple = ()
        self._last_row_count = 0
        self._visible_task_ids: tuple[str, ...] = ()
        self._refresh_count = 0
        self._column_widths = {
            0: 38,
            1: 72,
            2: 108,
            3: 92,
            4: 170,
            5: 96,
            6: 280,
            7: 360,
        }
        self._column_min_widths = {
            0: 38,
            1: 72,
            2: 90,
            3: 92,
            4: 170,
            5: 96,
            6: 220,
            7: 320,
        }
        self._column_max_widths = {
            0: 48,
            1: 120,
            2: 180,
            3: 120,
            4: 260,
            5: 140,
            6: 520,
            7: 900,
        }
        self._resizing_header = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(TOKENS.spacing_lg, TOKENS.spacing_lg, TOKENS.spacing_lg, TOKENS.spacing_lg)
        layout.setSpacing(TOKENS.spacing_sm)

        header_card = QFrame()
        header_card.setObjectName("toolbarCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(TOKENS.spacing_md, TOKENS.spacing_sm, TOKENS.spacing_md, TOKENS.spacing_sm)
        header_layout.setSpacing(2)

        title_label = QLabel("Task Center")
        title_label.setObjectName("sectionTitle")
        header_layout.addWidget(title_label)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("summaryLabel")
        header_layout.addWidget(self.summary_label)
        layout.addWidget(header_card)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["", "ID", "Kind", "Status", "Progress", "Speed", "Source", "Destination"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(False)
        header.sectionResized.connect(self._on_header_section_resized)
        for column, width in self._column_widths.items():
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            self.table.setColumnWidth(column, width)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.cb_select_all = QCheckBox("Select All")
        self.cb_select_all.toggled.connect(self._on_select_all_toggled)
        btn_layout.addWidget(self.cb_select_all)
        btn_layout.addStretch()

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setProperty("variant", "ghost")
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        btn_layout.addWidget(self.btn_pause)

        self.btn_resume = QPushButton("Resume")
        self.btn_resume.setProperty("variant", "ghost")
        self.btn_resume.clicked.connect(self._on_resume_clicked)
        btn_layout.addWidget(self.btn_resume)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setProperty("variant", "danger")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_restart = QPushButton("Restart")
        self.btn_restart.setProperty("variant", "primary")
        self.btn_restart.clicked.connect(self._on_restart_clicked)
        btn_layout.addWidget(self.btn_restart)

        self.btn_clear_finished = QPushButton("Clear Finished")
        self.btn_clear_finished.setProperty("variant", "ghost")
        self.btn_clear_finished.clicked.connect(self._on_clear_finished)
        btn_layout.addWidget(self.btn_clear_finished)

        layout.addLayout(btn_layout)

    def set_tasks(self, tasks: list[Task]):
        self.tasks = {task.task_id: task for task in tasks}
        self.refresh_tasks()

    def refresh_tasks(self):
        if not self.tasks:
            self.summary_label.setText("No tasks")
            self._last_signature = ()
            self._visible_task_ids = ()
            self.table.setRowCount(0)
            self._update_button_states()
            return

        checked_task_ids = self.get_checked_task_ids()
        selected_task_id = self.get_selected_task_id()

        def task_sort_key(task: Task):
            if task.status == "running":
                return (0, task.task_id)
            if task.status == "pending":
                return (1, task.task_id)
            if task.status == "paused":
                return (2, task.task_id)
            return (3, task.task_id)

        sorted_tasks = sorted(self.tasks.values(), key=task_sort_key)
        visible_tasks = sorted_tasks[:MAX_VISIBLE_TASKS]
        hidden_count = len(sorted_tasks) - len(visible_tasks)
        self.summary_label.setText(
            f"Showing {len(visible_tasks)} / {len(sorted_tasks)} tasks"
            + (f" ({hidden_count} hidden)" if hidden_count > 0 else "")
        )

        signature = tuple(
            (
                task.task_id,
                task.status,
                int(task.progress_percent * 10),
                int(task.speed / (128 * 1024)),
                task.subtask_done,
                task.subtask_count,
                task.current_file,
            )
            for task in visible_tasks
        )
        if signature == self._last_signature:
            return
        self._last_signature = signature
        self._refresh_count += 1
        visible_task_ids = tuple(task.task_id for task in visible_tasks)
        full_rebuild = visible_task_ids != self._visible_task_ids or self._last_row_count != len(visible_tasks)

        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        if full_rebuild:
            self.table.setRowCount(len(visible_tasks))

        for row, task in enumerate(visible_tasks):
            self._apply_task_row(
                row,
                task,
                checked=(task.task_id in checked_task_ids),
                selected_task_id=selected_task_id,
                full_rebuild=full_rebuild,
            )

            if task.preparing and task.current_file:
                progress_text = task.current_file
            elif task.kind.startswith("folder_") and task.subtask_count > 0:
                progress_text = f"{task.subtask_done}/{task.subtask_count} files ({task.progress_percent:.1f}%)"
                if task.status == "running" and task.current_file:
                    progress_text += f" - {task.current_file}"
            else:
                progress_text = f"{task.progress_percent:.1f}%"
                if task.bytes_total > 0:
                    progress_text += f" ({self._format_size(task.bytes_done)}/{self._format_size(task.bytes_total)})"
            self._set_text_item(row, 4, progress_text, alignment=Qt.AlignRight | Qt.AlignVCenter)

            speed_text = ""
            if task.status == "running" and task.speed > 0:
                speed_text = f"{task.speed / (1024 * 1024):.1f} MB/s"
            elif task.status == "running":
                avg_speed = self._running_avg_speed(task)
                speed_text = f"~{avg_speed / (1024 * 1024):.1f} MB/s" if avg_speed > 0 else "0.0 MB/s"
            elif task.is_finished and (task.avg_speed > 0 or task.start_time):
                avg_speed = task.avg_speed
                if avg_speed <= 0 and task.start_time:
                    end_t = task.end_time or time.time()
                    elapsed = end_t - task.start_time
                    if elapsed > 0 and task.bytes_done > 0:
                        avg_speed = task.bytes_done / elapsed
                if avg_speed > 0:
                    speed_text = f"~{avg_speed / (1024 * 1024):.1f} MB/s"
            self._set_text_item(row, 5, speed_text, alignment=Qt.AlignRight | Qt.AlignVCenter)
            self._set_text_item(row, 6, self._elide_middle(task.src, 70), tooltip=task.src)
            self._set_text_item(row, 7, self._elide_middle(task.dst, 70), tooltip=task.dst)

        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self._visible_task_ids = visible_task_ids
        self._last_row_count = len(visible_tasks)
        if full_rebuild:
            self._rebalance_destination_width()
        self._update_button_states()

    def _apply_task_row(
        self,
        row: int,
        task: Task,
        *,
        checked: bool,
        selected_task_id: Optional[str],
        full_rebuild: bool,
    ) -> None:
        if full_rebuild or self.table.cellWidget(row, 0) is None:
            self.table.setCellWidget(row, 0, self._build_checkbox_cell(task.task_id, checked))
            check_item = QTableWidgetItem()
            check_item.setData(Qt.UserRole, task.task_id)
            check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 0, check_item)
        else:
            checkbox = self._checkbox_for_row(row)
            if checkbox and checkbox.property("task_id") != task.task_id:
                checkbox.setProperty("task_id", task.task_id)
            if checkbox and checkbox.isChecked() != checked:
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
            check_item = self.table.item(row, 0)
            if check_item is not None:
                check_item.setData(Qt.UserRole, task.task_id)

        self._set_text_item(row, 1, task.task_id[:8])
        self._set_text_item(row, 2, task.kind.upper())
        fg, bg = self._status_colors(task.status)
        self._set_text_item(
            row,
            3,
            task.status.upper(),
            alignment=Qt.AlignCenter,
            foreground=fg,
            background=bg,
        )
        if selected_task_id == task.task_id:
            self.table.selectRow(row)

    def _set_text_item(
        self,
        row: int,
        column: int,
        text: str,
        *,
        tooltip: str | None = None,
        alignment: Qt.AlignmentFlag | Qt.Alignment | None = None,
        foreground: QColor | None = None,
        background: QColor | None = None,
    ) -> None:
        item = self.table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, column, item)
        item.setText(text)
        item.setToolTip(tooltip or "")
        if alignment is not None:
            item.setTextAlignment(alignment)
        if foreground is not None:
            item.setForeground(foreground)
        if background is not None:
            item.setBackground(background)

    def _update_button_states(self, selected_task_id: Optional[str] = None):
        checked_ids = self.get_checked_task_ids()
        target_ids = checked_ids
        if not target_ids:
            sel_id = selected_task_id or self.get_selected_task_id()
            if sel_id:
                target_ids = [sel_id]

        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_restart.setEnabled(False)

        if not target_ids:
            return

        has_running = False
        has_paused = False
        has_active = False
        has_terminal = False
        for task_id in target_ids:
            task = self.tasks.get(task_id)
            if not task:
                continue
            if task.status == "running":
                has_running = True
            if task.status == "paused":
                has_paused = True
            if task.status in ("pending", "running", "paused"):
                has_active = True
            if task.status in ("done", "failed", "canceled", "skipped"):
                has_terminal = True

        self.btn_pause.setEnabled(has_running)
        self.btn_resume.setEnabled(has_paused)
        self.btn_cancel.setEnabled(has_active)
        self.btn_restart.setEnabled(has_terminal)

    def get_checked_task_ids(self) -> list[str]:
        ids: list[str] = []
        for row in range(self.table.rowCount()):
            checkbox = self._checkbox_for_row(row)
            if checkbox and checkbox.isChecked():
                task_id = checkbox.property("task_id")
                if task_id:
                    ids.append(task_id)
        return ids

    def _on_cell_changed(self, row, column):
        if column == 0:
            self._update_button_states()

    def _on_select_all_toggled(self, checked: bool):
        for row in range(self.table.rowCount()):
            checkbox = self._checkbox_for_row(row)
            if checkbox:
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
        self._update_button_states()

    def get_selected_task_id(self) -> Optional[str]:
        selected_rows = self.table.selectedIndexes()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        id_item = self.table.item(row, 0)
        if id_item:
            return id_item.data(Qt.UserRole)
        return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebalance_destination_width()

    def _on_selection_changed(self):
        self._update_button_states()

    def _on_pause_clicked(self):
        for task_id in self._action_target_ids():
            self.request_pause.emit(task_id)

    def _on_resume_clicked(self):
        for task_id in self._action_target_ids():
            self.request_resume.emit(task_id)

    def _on_cancel_clicked(self):
        for task_id in self._action_target_ids():
            self.request_cancel.emit(task_id)

    def _on_restart_clicked(self):
        for task_id in self._action_target_ids():
            self.request_restart.emit(task_id)

    def _on_clear_finished(self):
        self.request_clear_finished.emit()

    def _action_target_ids(self) -> list[str]:
        ids = self.get_checked_task_ids()
        if ids:
            return ids
        selected_id = self.get_selected_task_id()
        return [selected_id] if selected_id else []

    def _build_checkbox_cell(self, task_id: str, checked: bool) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        checkbox = QCheckBox()
        checkbox.setObjectName("taskRowCheckbox")
        checkbox.setProperty("task_id", task_id)
        checkbox.setChecked(checked)
        checkbox.toggled.connect(lambda _state: self._update_button_states())
        layout.addWidget(checkbox)
        return container

    def _checkbox_for_row(self, row: int) -> Optional[QCheckBox]:
        widget = self.table.cellWidget(row, 0)
        if not widget:
            return None
        return widget.findChild(QCheckBox, "taskRowCheckbox")

    def _on_header_section_resized(self, logical_index: int, _old_size: int, new_size: int) -> None:
        if self._resizing_header:
            return
        clamped_size = self._clamped_column_width(logical_index, new_size)
        self._resizing_header = True
        try:
            if clamped_size != new_size:
                self.table.setColumnWidth(logical_index, clamped_size)
            self._column_widths[logical_index] = clamped_size
            if logical_index != 7:
                self._rebalance_destination_width()
        finally:
            self._resizing_header = False

    def _rebalance_destination_width(self) -> None:
        if self.table.columnCount() < 8:
            return
        viewport_width = self.table.viewport().width()
        if viewport_width <= 0:
            return
        occupied = sum(self.table.columnWidth(index) for index in range(7))
        destination_width = max(
            self._column_min_widths.get(7, 320),
            min(self._column_max_widths.get(7, 900), max(self._column_widths.get(7, 360), viewport_width - occupied - 4)),
        )
        self.table.setColumnWidth(7, destination_width)
        self._column_widths[7] = destination_width

    def _clamped_column_width(self, logical_index: int, proposed_size: int) -> int:
        min_width = self._column_min_widths.get(logical_index, 60)
        max_width = self._column_max_widths.get(logical_index, 900)
        proposed = max(min_width, min(max_width, proposed_size))
        if logical_index == 7:
            return proposed
        viewport_width = self.table.viewport().width()
        if viewport_width <= 0:
            return proposed
        other_min_total = sum(
            self._column_min_widths.get(index, 60)
            for index in range(self.table.columnCount())
            if index != logical_index
        )
        max_allowed = max(min_width, viewport_width - other_min_total - 4)
        return min(proposed, max_allowed)

    @staticmethod
    def _running_avg_speed(task: Task) -> float:
        if not task.start_time or task.bytes_done <= 0:
            return 0.0
        elapsed = max(0.001, time.time() - task.start_time)
        return task.bytes_done / elapsed

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["Byte", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    @staticmethod
    def _elide_middle(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        keep = max(8, (max_len - 3) // 2)
        return f"{text[:keep]}...{text[-keep:]}"

    @staticmethod
    def _status_colors(status: str) -> tuple[QColor, QColor]:
        def tint(color: str, alpha: float) -> QColor:
            qcolor = QColor(color)
            qcolor.setAlphaF(alpha)
            return qcolor

        palette = {
            "done": (QColor(TOKENS.success), QColor(TOKENS.success_soft)),
            "failed": (QColor(TOKENS.danger), QColor(TOKENS.danger_soft)),
            "running": (QColor(TOKENS.accent), QColor(TOKENS.accent_soft)),
            "paused": (QColor(TOKENS.warning), QColor(TOKENS.warning_soft)),
            "skipped": (QColor(TOKENS.text_muted), tint(TOKENS.text_muted, 0.14)),
            "canceled": (QColor(TOKENS.text_soft), tint(TOKENS.text_muted, 0.12)),
        }
        return palette.get(status, (QColor(TOKENS.text_main), tint(TOKENS.text_muted, 0.10)))
