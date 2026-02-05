"""Remote file panel for displaying remote directory contents."""
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..shared.models import RemoteEntry


class RemotePanel(QWidget):
    """Panel for displaying and navigating remote directory contents."""
    
    path_changed = Signal(str)  # Emitted when current path changes
    entry_activated = Signal(RemoteEntry)  # Emitted when entry is double-clicked
    
    def __init__(self, parent=None):
        """Initialize remote panel."""
        super().__init__(parent)
        self.current_path = "/"
        self.entries: list[RemoteEntry] = []
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Path label
        self.path_label = QLabel("Remote: /")
        self.path_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.path_label)
        
        # File table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        layout.addWidget(self.table)
    
    def set_path(self, path: str):
        """Set current path."""
        self.current_path = path
        self.path_label.setText(f"Remote: {path}")
        self.path_changed.emit(path)
    
    def set_entries(self, entries: list[RemoteEntry]):
        """
        Display directory entries in the table.
        
        Args:
            entries: List of RemoteEntry objects
        """
        self.entries = entries
        self.table.setRowCount(len(entries))
        
        for row, entry in enumerate(entries):
            # Name
            name_item = QTableWidgetItem(entry.name)
            if entry.is_dir:
                name_item.setData(Qt.UserRole, entry)
                # Make directories bold
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            else:
                name_item.setData(Qt.UserRole, entry)
            self.table.setItem(row, 0, name_item)
            
            # Type
            type_item = QTableWidgetItem("DIR" if entry.is_dir else "FILE")
            self.table.setItem(row, 1, type_item)
            
            # Size
            size_str = self._format_size(entry.size) if not entry.is_dir else ""
            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, size_item)
            
            # Modified time
            mtime_str = entry.mtime_datetime.strftime("%Y-%m-%d %H:%M:%S")
            mtime_item = QTableWidgetItem(mtime_str)
            self.table.setItem(row, 3, mtime_item)
        
        # Resize columns to content
        self.table.resizeColumnsToContents()
    
    def clear(self):
        """Clear the table."""
        self.table.setRowCount(0)
        self.entries = []
    
    def get_selected_entry(self) -> Optional[RemoteEntry]:
        """Get the currently selected entry."""
        selected_rows = self.table.selectedIndexes()
        if not selected_rows:
            return None
        
        row = selected_rows[0].row()
        name_item = self.table.item(row, 0)
        if name_item:
            return name_item.data(Qt.UserRole)
        return None
    
    def _on_item_double_clicked(self, item: QTableWidgetItem):
        """Handle double-click on an item."""
        row = item.row()
        name_item = self.table.item(row, 0)
        if name_item:
            entry = name_item.data(Qt.UserRole)
            if entry:
                self.entry_activated.emit(entry)
    
    @staticmethod
    def _format_size(size: int) -> str:
        """Format file size in human-readable form."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
