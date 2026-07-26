"""Site editor dialog for creating and editing SSH site configurations."""
import re
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
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
from src.ui.i18n import tr
from src.ui.theme import TOKENS
from src.ui.widgets.feedback import install_button_feedback


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
        self.setWindowTitle(tr("dialog.site.edit_title") if site_config else tr("dialog.site.new_title"))
        self.setMinimumWidth(500)
        self.setStyleSheet(
            f"QDialog {{ background-color: {TOKENS.bg_surface}; }}"
            "QTextEdit { min-height: 72px; }"
        )

        self._init_ui()

        if site_config:
            self._load_config(site_config)

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)

        # SSH Command Parser Section
        parse_group = QGroupBox(tr("site.group.import"))
        parse_layout = QVBoxLayout()

        self.ssh_command_input = QTextEdit()
        self.ssh_command_input.setPlaceholderText(tr("site.ssh.placeholder"))
        self.ssh_command_input.setMaximumHeight(60)
        parse_layout.addWidget(self.ssh_command_input)

        self.parse_button = QPushButton(tr("site.parse_button"))
        self.parse_button.clicked.connect(self._parse_ssh_command)
        parse_layout.addWidget(self.parse_button)

        parse_group.setLayout(parse_layout)
        layout.addWidget(parse_group)

        # Basic Configuration Section
        basic_group = QGroupBox(tr("site.group.basic"))
        basic_layout = QFormLayout()

        self.name_edit = QLineEdit()
        basic_layout.addRow(tr("site.field.name"), self.name_edit)

        self.host_edit = QLineEdit()
        basic_layout.addRow(tr("site.field.host"), self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        basic_layout.addRow(tr("site.field.port"), self.port_spin)

        self.username_edit = QLineEdit()
        basic_layout.addRow(tr("site.field.username"), self.username_edit)

        self.remote_root_edit = QLineEdit()
        self.remote_root_edit.setPlaceholderText("/")
        basic_layout.addRow(tr("site.field.remote_root"), self.remote_root_edit)

        self.default_protocol_combo = QComboBox()
        self.default_protocol_combo.addItems(["sftp", "scp"])
        basic_layout.addRow(tr("site.field.protocol"), self.default_protocol_combo)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # Authentication Section
        auth_group = QGroupBox(tr("site.group.auth"))
        auth_layout = QFormLayout()

        self.auth_method_combo = QComboBox()
        self.auth_method_combo.addItems(["password", "key"])
        self.auth_method_combo.currentTextChanged.connect(self._on_auth_method_changed)
        auth_layout.addRow(tr("site.field.method"), self.auth_method_combo)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText(tr("site.password.placeholder"))
        auth_layout.addRow(tr("site.field.password"), self.password_edit)

        self.remember_password_check = QCheckBox(tr("site.remember_password"))
        self.remember_password_check.setToolTip(tr("site.remember_password.tooltip"))
        auth_layout.addRow("", self.remember_password_check)

        self.key_path_edit = QLineEdit()
        self.key_path_button = QPushButton(tr("action.browse"))
        self.key_path_button.clicked.connect(self._browse_key_path)
        auth_layout.addRow(tr("site.field.key_path"), self.key_path_edit)
        auth_layout.addRow("", self.key_path_button)

        self.key_passphrase_edit = QLineEdit()
        self.key_passphrase_edit.setEchoMode(QLineEdit.Password)
        self.key_passphrase_edit.setPlaceholderText(tr("site.key_passphrase.placeholder"))
        auth_layout.addRow(tr("site.field.key_passphrase"), self.key_passphrase_edit)

        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)

        # Advanced Section
        advanced_group = QGroupBox(tr("site.group.advanced"))
        advanced_layout = QFormLayout()

        self.proxy_jump_edit = QLineEdit()
        self.proxy_jump_edit.setPlaceholderText(tr("site.jump.placeholder"))
        self.proxy_jump_edit.setToolTip(tr("site.jump.tooltip"))
        advanced_layout.addRow(tr("site.field.jump_host"), self.proxy_jump_edit)

        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._on_auth_method_changed("password")
        install_button_feedback(self)

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
        self.remember_password_check.setVisible(is_password)
        self.key_path_edit.setVisible(not is_password)
        self.key_path_button.setVisible(not is_password)
        self.key_passphrase_edit.setVisible(not is_password)

    def _browse_key_path(self):
        """Browse for SSH key file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.select_key.title"),
            "",
            tr("dialog.select_key.filter")
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
        self.default_protocol_combo.setCurrentText(config.default_transfer_protocol)

        self.auth_method_combo.setCurrentText(config.auth_method)

        if config.password:
            self.password_edit.setText(config.password)
        self.remember_password_check.setChecked(config.remember_password)
        if config.key_path:
            self.key_path_edit.setText(config.key_path)
        if config.key_passphrase:
            self.key_passphrase_edit.setText(config.key_passphrase)
        if config.proxy_jump:
            self.proxy_jump_edit.setText(config.proxy_jump)

    def _save_and_accept(self):
        """Validate and save configuration."""
        # Validate required fields with user feedback
        missing = []
        if not self.name_edit.text().strip():
            missing.append(tr("site.name"))
        if not self.host_edit.text().strip():
            missing.append(tr("site.host"))
        if not self.username_edit.text().strip():
            missing.append(tr("site.username"))

        if missing:
            QMessageBox.warning(
                self,
                tr("dialog.missing.title"),
                tr("dialog.missing.body", fields="\n- ".join(missing)),
            )
            return

        auth_method = self.auth_method_combo.currentText()
        remote_root = self.remote_root_edit.text().strip() or "/"

        # Create configuration
        config = SiteConfig(
            name=self.name_edit.text().strip(),
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
            username=self.username_edit.text().strip(),
            auth_method=auth_method,
            remote_root=remote_root,
            default_transfer_protocol=self.default_protocol_combo.currentText(),
            proxy_jump=self.proxy_jump_edit.text().strip() or None,
        )

        # Add credentials (runtime only)
        if auth_method == "password":
            config.password = self.password_edit.text() or None
            config.remember_password = self.remember_password_check.isChecked()
        else:
            config.key_path = self.key_path_edit.text() or None
            config.key_passphrase = self.key_passphrase_edit.text() or None
            config.remember_password = False

        self.site_saved.emit(config)
        self.accept()

    def get_config(self) -> Optional[SiteConfig]:
        """Get the configured site (after dialog accepted)."""
        return self.site_config
