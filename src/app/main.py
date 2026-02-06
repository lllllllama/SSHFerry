"""Main application entry point."""
import os
import sys

# Ensure src/ is on path when running directly
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, os.path.dirname(_src_dir))

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def main():
    """Run the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("SSHFerry")
    app.setOrganizationName("SSHFerry")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
