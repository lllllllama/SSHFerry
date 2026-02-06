"""Site editor dialog for creating and editing SSH site configurations."""
import re
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from src.shared.models import SiteConfig


class SiteEditorDialog(QDialog):
    """Dialog for editing SSH site configuration."""

    site_saved = Signal(SiteConfig)

    def __init__(self, site_config: Optional[SiteConfig] = None, parent=None):
        """
        Initialize site editor dialog.
        
        Args:
            site_config: Existing configuration to edit (None for new site)
            parent: Parent widget
        """
        super().__init__(parent)
        self.site_config = site_config
        self.setWindowTitle("Edit Site" if site_config else "New Site")
        self.setMinimumWidth(500)

        self._init_ui()

        if site_config:
            self._load_config(site_config)

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)

        # SSH Command Parser Section
        parse_group = QGroupBox("Quick Import from SSH Command")
        parse_layout = QVBoxLayout()

        self.ssh_command_input = QTextEdit()
        self.ssh_command_input.setPlaceholderText(
            "Paste SSH command here, e.g.:\nssh -p 16921 root@connect.westb.seetacloud.com"
        )
        self.ssh_command_input.setMaximumHeight(60)
        parse_layout.addWidget(self.ssh_command_input)

        self.parse_button = QPushButton("Parse SSH Command")
        self.parse_button.clicked.connect(self._parse_ssh_command)
        parse_layout.addWidget(self.parse_button)

        parse_group.setLayout(parse_layout)
        layout.addWidget(parse_group)

        # Basic Configuration Section
        basic_group = QGroupBox("Basic Configuration")
        basic_layout = QFormLayout()

        self.name_edit = QLineEdit()
        basic_layout.addRow("Site Name:", self.name_edit)

        self.host_edit = QLineEdit()
        basic_layout.addRow("Host:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        basic_layout.addRow("Port:", self.port_spin)

        self.username_edit = QLineEdit()
        basic_layout.addRow("Username:", self.username_edit)

        self.remote_root_edit = QLineEdit()
        self.remote_root_edit.setPlaceholderText("/root/autodl-tmp")
        basic_layout.addRow("Remote Root (Sandbox):", self.remote_root_edit)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # Authentication Section
        auth_group = QGroupBox("Authentication")
        auth_layout = QFormLayout()

        self.auth_method_combo = QComboBox()
        self.auth_method_combo.addItems(["password", "key"])
        self.auth_method_combo.currentTextChanged.connect(self._on_auth_method_changed)
        auth_layout.addRow("Method:", self.auth_method_combo)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Enter password (not saved to file)")
        auth_layout.addRow("Password:", self.password_edit)

        self.key_path_edit = QLineEdit()
        self.key_path_button = QPushButton("Browse...")
        self.key_path_button.clicked.connect(self._browse_key_path)
        auth_layout.addRow("Key Path:", self.key_path_edit)
        auth_layout.addRow("", self.key_path_button)

        self.key_passphrase_edit = QLineEdit()
        self.key_passphrase_edit.setEchoMode(QLineEdit.Password)
        self.key_passphrase_edit.setPlaceholderText("Key passphrase (if required)")
        auth_layout.addRow("Key Passphrase:", self.key_passphrase_edit)

        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._on_auth_method_changed("password")

    def _parse_ssh_command(self):
        """Parse SSH command and populate fields."""
        command = self.ssh_command_input.toPlainText().strip()

        if not command:
            return

        # Parse SSH command: ssh [-p PORT] [USER@]HOST
        # Pattern: ssh (-p PORT)? (USER@)?HOST
        pattern = r'ssh\s+(?:-p\s+(\d+)\s+)?(?:(\w+)@)?([^\s]+)'
        match = re.search(pattern, command)

        if match:
            port_str, username, host = match.groups()

            if port_str:
                self.port_spin.setValue(int(port_str))

            if username:
                self.username_edit.setText(username)

            if host:
                self.host_edit.setText(host)
                # Auto-generate site name from host
                if not self.name_edit.text():
                    # Use first part of hostname as name
                    name = host.split('.')[0]
                    self.name_edit.setText(name)

    def _on_auth_method_changed(self, method: str):
        """Handle authentication method change."""
        is_password = (method == "password")

        self.password_edit.setVisible(is_password)
        self.key_path_edit.setVisible(not is_password)
        self.key_path_button.setVisible(not is_password)
        self.key_passphrase_edit.setVisible(not is_password)

    def _browse_key_path(self):
        """Browse for SSH key file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SSH Private Key",
            "",
            "All Files (*)"
        )
        if file_path:
            self.key_path_edit.setText(file_path)

    def _load_config(self, config: SiteConfig):
        """Load configuration into UI fields."""
        self.name_edit.setText(config.name)
        self.host_edit.setText(config.host)
        self.port_spin.setValue(config.port)
        self.username_edit.setText(config.username)
        self.remote_root_edit.setText(config.remote_root)

        self.auth_method_combo.setCurrentText(config.auth_method)

        if config.password:
            self.password_edit.setText(config.password)
        if config.key_path:
            self.key_path_edit.setText(config.key_path)
        if config.key_passphrase:
            self.key_passphrase_edit.setText(config.key_passphrase)

    def _save_and_accept(self):
        """Validate and save configuration."""
        # Validate required fields with user feedback
        missing = []
        if not self.name_edit.text().strip():
            missing.append("Site Name")
        if not self.host_edit.text().strip():
            missing.append("Host")
        if not self.username_edit.text().strip():
            missing.append("Username")
        if not self.remote_root_edit.text().strip():
            missing.append("Remote Root (Sandbox)")

        if missing:
            QMessageBox.warning(
                self,
                "Missing Required Fields",
                f"Please fill in the following fields:\n• " + "\n• ".join(missing)
            )
            return

        auth_method = self.auth_method_combo.currentText()

        # Create configuration
        config = SiteConfig(
            name=self.name_edit.text(),
            host=self.host_edit.text(),
            port=self.port_spin.value(),
            username=self.username_edit.text(),
            auth_method=auth_method,
            remote_root=self.remote_root_edit.text(),
        )

        # Add credentials (runtime only)
        if auth_method == "password":
            config.password = self.password_edit.text() or None
        else:
            config.key_path = self.key_path_edit.text() or None
            config.key_passphrase = self.key_passphrase_edit.text() or None

        self.site_saved.emit(config)
        self.accept()

    def get_config(self) -> Optional[SiteConfig]:
        """Get the configured site (after dialog accepted)."""
        return self.site_config
