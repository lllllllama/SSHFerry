"""Main application entry point."""
import os
import sys

# Ensure src/ is on path when running directly
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, os.path.dirname(_src_dir))

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


class WindowManager:
    """Manages multiple MainWindow instances."""
    
    _instance = None
    
    def __init__(self):
        self.windows: list[MainWindow] = []
    
    @classmethod
    def instance(cls):
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = WindowManager()
        return cls._instance
    
    def create_window(self) -> MainWindow:
        """Create and show a new window."""
        window = MainWindow()
        window.window_manager = self
        self.windows.append(window)
        window.destroyed.connect(lambda: self._on_window_destroyed(window))
        window.show()
        return window
    
    def _on_window_destroyed(self, window: MainWindow):
        """Handle window destruction."""
        if window in self.windows:
            self.windows.remove(window)
    
    def window_count(self) -> int:
        """Get the number of open windows."""
        return len(self.windows)


def main():
    """Run the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("SSHFerry")
    app.setOrganizationName("SSHFerry")
    
    # Create first window via manager
    manager = WindowManager.instance()
    manager.create_window()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

