"""Task center panel for monitoring transfer tasks."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..shared.models import Task


class TaskCenterPanel(QWidget):
    """Panel for displaying and managing transfer tasks."""
    
    def __init__(self, parent=None):
        """Initialize task center panel."""
        super().__init__(parent)
        self.tasks: dict[str, Task] = {}
        
        self._init_ui()
        
        # Set up timer to refresh task display
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_tasks)
        self.refresh_timer.start(500)  # Refresh every 500ms
    
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
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Kind", "Status", "Progress", "Source", "Destination"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        
        layout.addWidget(self.table)
        
        # Control buttons
        btn_layout = QVBoxLayout()
        
        self.btn_cancel = QPushButton("Cancel Task")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)
        
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
        """Refresh the task table display."""
        # Store current selection
        selected_rows = self.table.selectedIndexes()
        selected_task_id = None
        if selected_rows:
            row = selected_rows[0].row()
            id_item = self.table.item(row, 0)
            if id_item:
                selected_task_id = id_item.data(Qt.UserRole)
        
        # Update table
        self.table.setRowCount(len(self.tasks))
        
        for row, task in enumerate(self.tasks.values()):
            # ID (short)
            id_item = QTableWidgetItem(task.task_id[:8])
            id_item.setData(Qt.UserRole, task.task_id)
            self.table.setItem(row, 0, id_item)
            
            # Kind
            kind_item = QTableWidgetItem(task.kind.upper())
            self.table.setItem(row, 1, kind_item)
            
            # Status
            status_item = QTableWidgetItem(task.status.upper())
            if task.status == "done":
                status_item.setForeground(Qt.green)
            elif task.status == "failed":
                status_item.setForeground(Qt.red)
            elif task.status == "running":
                status_item.setForeground(Qt.blue)
            self.table.setItem(row, 2, status_item)
            
            # Progress
            progress_text = f"{task.progress_percent:.1f}%"
            if task.bytes_total > 0:
                progress_text += f" ({self._format_size(task.bytes_done)}/{self._format_size(task.bytes_total)})"
            progress_item = QTableWidgetItem(progress_text)
            progress_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, progress_item)
            
            # Source
            src_item = QTableWidgetItem(task.src)
            self.table.setItem(row, 4, src_item)
            
            # Destination
            dst_item = QTableWidgetItem(task.dst)
            self.table.setItem(row, 5, dst_item)
            
            # Restore selection if it was the same task
            if selected_task_id == task.task_id:
                self.table.selectRow(row)
        
        # Resize columns
        self.table.resizeColumnsToContents()
    
    def get_selected_task_id(self) -> str | None:
        """Get the ID of the currently selected task."""
        selected_rows = self.table.selectedIndexes()
        if not selected_rows:
            return None
        
        row = selected_rows[0].row()
        id_item = self.table.item(row, 0)
        if id_item:
            return id_item.data(Qt.UserRole)
        return None
    
    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        task_id = self.get_selected_task_id()
        if task_id and hasattr(self.parent(), 'cancel_task'):
            self.parent().cancel_task(task_id)
    
    def _on_clear_finished(self):
        """Handle clear finished button click."""
        if hasattr(self.parent(), 'clear_finished_tasks'):
            self.parent().clear_finished_tasks()
    
    @staticmethod
    def _format_size(size: int) -> str:
        """Format file size in human-readable form."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
