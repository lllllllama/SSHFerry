"""Task center panel for monitoring transfer tasks."""
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.shared.models import Task


# Maximum tasks to display to prevent UI slowdown
MAX_VISIBLE_TASKS = 50


class TaskCenterPanel(QWidget):
    """Panel for displaying and managing transfer tasks."""
    
    # Signals for task control
    request_pause = Signal(str)
    request_resume = Signal(str)
    request_cancel = Signal(str)
    request_restart = Signal(str)
    request_clear_finished = Signal()

    def __init__(self, parent=None):
        """Initialize task center panel."""
        super().__init__(parent)
        self.tasks: dict[str, Task] = {}
        self._pending_update = False

        self._init_ui()

        # Set up timer to refresh task display (1 second interval to reduce load)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_tasks)
        self.refresh_timer.start(1000)  # Refresh every 1s

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title_label = QLabel("Task Center")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        layout.addWidget(title_label)

        # Task table
        self.table = QTableWidget()
        self.table.setColumnCount(8)  # +1 for checkbox column
        self.table.setHorizontalHeaderLabels([
            "", "ID", "Kind", "Status", "Progress", "Speed", "Source", "Destination"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        # Handle checkbox changes
        self.table.cellChanged.connect(self._on_cell_changed)

        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()

        self.cb_select_all = QCheckBox("Select All")
        self.cb_select_all.toggled.connect(self._on_select_all_toggled)
        btn_layout.addWidget(self.cb_select_all)
        
        # Spacer
        btn_layout.addStretch()

        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        btn_layout.addWidget(self.btn_pause)

        self.btn_resume = QPushButton("▶ Resume")
        self.btn_resume.clicked.connect(self._on_resume_clicked)
        btn_layout.addWidget(self.btn_resume)

        self.btn_cancel = QPushButton("✕ Cancel")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_restart = QPushButton("↻ Restart")
        self.btn_restart.clicked.connect(self._on_restart_clicked)
        btn_layout.addWidget(self.btn_restart)

        self.btn_clear_finished = QPushButton("Clear Finished")
        self.btn_clear_finished.clicked.connect(self._on_clear_finished)
        btn_layout.addWidget(self.btn_clear_finished)

        layout.addLayout(btn_layout)

    def set_tasks(self, tasks: list[Task]):
        """
        Update the task list.
        
        Args:
            tasks: List of Task objects
        """
        self.tasks = {task.task_id: task for task in tasks}
        self.refresh_tasks()

    def refresh_tasks(self):
        """Refresh the task table display with performance optimizations."""
        if not self.tasks:
            self.table.setRowCount(0)
            return

        # Store checked tasks to restore state
        checked_task_ids = self.get_checked_task_ids()
        
        # Store current selection
        selected_task_id = self.get_selected_task_id()

        # Sort tasks: running first, then pending, then finished

        # Sort tasks: running first, then pending, then finished
        def task_sort_key(t):
            if t.status == "running":
                return (0, t.task_id)
            elif t.status == "pending":
                return (1, t.task_id)
            else:
                return (2, t.task_id)
        
        sorted_tasks = sorted(self.tasks.values(), key=task_sort_key)
        
        # Limit visible tasks to prevent UI slowdown
        visible_tasks = sorted_tasks[:MAX_VISIBLE_TASKS]
        hidden_count = len(sorted_tasks) - len(visible_tasks)
        
        # Batch update - disable updates during populate
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(visible_tasks))

        for row, task in enumerate(visible_tasks):
            # Checkbox
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            if task.task_id in checked_task_ids:
                check_item.setCheckState(Qt.Checked)
            else:
                check_item.setCheckState(Qt.Unchecked)
            # Store ID in checkbox item too for easy access
            check_item.setData(Qt.UserRole, task.task_id)
            self.table.setItem(row, 0, check_item)

            # ID (short)
            id_item = QTableWidgetItem(task.task_id[:8])
            self.table.setItem(row, 1, id_item)

            # Kind
            kind_item = QTableWidgetItem(task.kind.upper())
            self.table.setItem(row, 2, kind_item)

            # Status
            status_item = QTableWidgetItem(task.status.upper())
            if task.status == "done":
                status_item.setForeground(Qt.green)
            elif task.status == "failed":
                status_item.setForeground(Qt.red)
            elif task.status == "running":
                status_item.setForeground(Qt.blue)
            elif task.status == "skipped":
                status_item.setForeground(Qt.gray)
            elif task.status == "paused":
                status_item.setForeground(Qt.darkYellow)
            elif task.status == "canceled":
                status_item.setForeground(Qt.darkGray)
            self.table.setItem(row, 3, status_item)

            # Progress - show folder progress if applicable
            if task.kind.startswith("folder_") and task.subtask_count > 0:
                # Folder task: show file progress
                progress_text = f"{task.subtask_done}/{task.subtask_count} files ({task.progress_percent:.1f}%)"
                if task.status == "running" and task.current_file:
                    progress_text += f" - {task.current_file}"
            else:
                progress_text = f"{task.progress_percent:.1f}%"
                if task.bytes_total > 0:
                    progress_text += f" ({self._format_size(task.bytes_done)}/{self._format_size(task.bytes_total)})"
            progress_item = QTableWidgetItem(progress_text)
            progress_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 4, progress_item)

            # Speed
            speed_text = ""
            if task.status == "running" and task.speed > 0:
                speed_mb = task.speed / (1024 * 1024)
                speed_text = f"{speed_mb:.2f} MB/s"
            elif task.is_finished and task.start_time:
                # Calculate average speed for completed tasks
                end_t = task.end_time or time.time()
                elapsed = end_t - task.start_time
                if elapsed > 0 and task.bytes_done > 0:
                    avg_speed = task.bytes_done / elapsed / (1024 * 1024)
                    speed_text = f"~{avg_speed:.2f} MB/s"
            speed_item = QTableWidgetItem(speed_text)
            speed_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 5, speed_item)

            # Source
            src_item = QTableWidgetItem(task.src)
            self.table.setItem(row, 6, src_item)

            # Destination
            dst_item = QTableWidgetItem(task.dst)
            self.table.setItem(row, 7, dst_item)

            # Restore selection if it was the same task
            if selected_task_id == task.task_id:
                self.table.selectRow(row)

        # Re-enable updates and resize
        self.table.setUpdatesEnabled(True)
        self.table.resizeColumnsToContents()

        # Update button states based on checkboxes primarily, fallback to selection if needed?
        # User wants batch control.
        self._update_button_states()

    def _update_button_states(self, selected_task_id: Optional[str] = None):
        """Enable/disable buttons based on CHECKED tasks status."""
        checked_ids = self.get_checked_task_ids()
        
        # If no checkboxes are checked, disabling all is safer, or fallback to selected row?
        # Requirement: "has checkboxes". Users expect checkboxes to drive action.
        # But if user just selects a row without checking? 
        # Let's support both: if checked_ids is empty, use selected_rows?
        # Re-reading requirement: "Task has check button, and select all function".
        # Safe bet: operate on checked items. If none checked, disable?
        # Or if none checked, operate on HIGHLIGHTED item (single selection)?
        # Hybrid approach: checked > selected.
        
        target_ids = checked_ids
        if not target_ids:
            sel_id = self.get_selected_task_id()
            if sel_id:
                target_ids = [sel_id]
        
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_restart.setEnabled(False)

        if not target_ids:
            return

        # Check collective state
        has_running = False
        has_paused = False
        has_active = False # pending, running, paused
        has_terminal = False # done, failed, canceled

        for tid in target_ids:
            if tid not in self.tasks:
                continue
            task = self.tasks[tid]
            
            if task.status == "running":
                has_running = True
            if task.status == "paused":
                has_paused = True
            if task.status in ("pending", "running", "paused"):
                has_active = True
            if task.status in ("done", "failed", "canceled", "skipped"):
                has_terminal = True
        
        # Enable buttons if at least one task qualifies
        if has_running:
            self.btn_pause.setEnabled(True)
        if has_paused:
            self.btn_resume.setEnabled(True)
        if has_active:
            self.btn_cancel.setEnabled(True)
        if has_terminal:
            self.btn_restart.setEnabled(True)

    def get_checked_task_ids(self) -> list[str]:
        """Get IDs of all checked tasks."""
        ids = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                task_id = item.data(Qt.UserRole)
                if task_id:
                    ids.append(task_id)
        return ids

    def _on_cell_changed(self, row, column):
        """Handle cell changes (checkbox toggles)."""
        if column == 0:
            self._update_button_states()

    def _on_select_all_toggled(self, checked: bool):
        """Handle Select All toggle."""
        self.table.blockSignals(True)  # Prevent multiple cellChanged signals
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(state)
        self.table.blockSignals(False)
        self._update_button_states()

    def get_selected_task_id(self) -> Optional[str]:
        """Get the ID of the currently selected task (highlighted row)."""
        selected_rows = self.table.selectedIndexes()
        if not selected_rows:
            return None

        row = selected_rows[0].row()
        # ID is now in column 1 visually, but stored in column 0 item UserRole?
        # Wait, I put ID text in col 1, but CHECKBOX in col 0.
        # Checkbox item (col 0) stores UserRole data (task_id).
        # ID item (col 1) does NOT store data in my new code (only check item does).
        # Let's fix selected row retrieval to look at col 0.
        
        id_item = self.table.item(row, 0)
        if id_item:
            return id_item.data(Qt.UserRole)
        return None

    def _on_selection_changed(self):
        """Handle table selection change."""
        # Just update buttons, logic handles fallback to selection
        self._update_button_states()

    def _on_pause_clicked(self):
        """Handle pause button click (batch)."""
        ids = self.get_checked_task_ids()
        if not ids:
             tid = self.get_selected_task_id()
             if tid: ids = [tid]
        
        for task_id in ids:
            self.request_pause.emit(task_id)

    def _on_resume_clicked(self):
        """Handle resume button click (batch)."""
        ids = self.get_checked_task_ids()
        if not ids:
             tid = self.get_selected_task_id()
             if tid: ids = [tid]

        for task_id in ids:
            self.request_resume.emit(task_id)

    def _on_cancel_clicked(self):
        """Handle cancel button click (batch)."""
        ids = self.get_checked_task_ids()
        if not ids:
             tid = self.get_selected_task_id()
             if tid: ids = [tid]

        for task_id in ids:
            self.request_cancel.emit(task_id)

    def _on_restart_clicked(self):
        """Handle restart button click (batch)."""
        ids = self.get_checked_task_ids()
        if not ids:
             tid = self.get_selected_task_id()
             if tid: ids = [tid]

        for task_id in ids:
            self.request_restart.emit(task_id)

    def _on_clear_finished(self):
        """Handle clear finished button click."""
        self.request_clear_finished.emit()

    @staticmethod
    def _format_size(size: int) -> str:
        """Format file size in human-readable form."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
