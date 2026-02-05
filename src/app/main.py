"""Main application entry point."""
import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


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
