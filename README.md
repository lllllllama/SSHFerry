# SSHFerry

[中文](README_zh.md) | English

**SSHFerry** is a professional, high-performance GUI tool for SSH/SFTP file management and transfer, built with Python and PySide6. Designed for efficiency and security, it streamlines your remote file operations with a modern interface and smart transfer logic.

---

## ✨ Key Features

### 🚀 Smart Transfer System
- **Intelligent Skipping**: Automatically detects if a file already exists with the same size and skips the transfer to save time.
- **Auto-Resolution**: Handles file conflicts smartly by automatically renaming new files (e.g., `data_1.csv`) if a different version exists, preventing accidental overwrites.
- **Recursive Operations**: Seamlessly uploads and downloads entire folder structures.

### 💻 robust Site Management
- **Profile Manager**: Organize and save multiple server connections with ease.
- **Instant Import**: Quickly add sites by pasting standard SSH commands (e.g., `ssh -p 22 user@hostname`).
- **Connection Doctor**: Built-in self-check tool that validates 5 critical points (TCP, SSH, SFTP, Read/Write permissions) to diagnose connection issues instantly.

### 🛡️ Sandbox Security
- **Root Locking**: Restricts all file operations to a specified `remote_root` directory. This "sandbox" ensures you never accidentally modify or delete critical system files outside your designated workspace.

### ⚡ Performance & Engines
- **Standard SFTP**: Reliable, compliant transfer using the Paramiko implementation.
- **MSCP Ready**: Support for the MSCP acceleration engine for high-bandwidth environments (requires separate binary).

### 📊 Task Control Center
- **Visual Monitoring**: Track progress, transfer speeds, and completion status in real-time.
- **Queue System**: Multi-threaded scheduler manages concurrent uploads and downloads efficiently.

---

## 🛠️ Requirements

- **Python**: 3.11+
- **Core Libraries**:
  - `PySide6` (6.6.0+) for the GUI
  - `Paramiko` (3.4.0+) for SSH/SFTP protocols

## 📦 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/SSHFerry.git
   cd SSHFerry
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## 🚀 Usage

### Starting the Application

**Windows**
```powershell
./run.bat
# Or directly via Python
python -m src.app.main
```

**Linux / macOS**
```bash
chmod +x run.sh
./run.sh
# Or directly via Python
python3 -m src.app.main
```

### Quick Start
1. **Add a Source**: Click "New Site" or paste an SSH command string.
2. **Connect**: Double-click the site profile. The "Connection Doctor" will verify access.
3. **Transfer**:
   - **Upload**: Drag files from your OS file explorer into the SSHFerry window (coming soon) or use the "Upload" button.
   - **Download**: Right-click remote files and select "Download".
4. **Monitor**: Watch the "Task Center" tab for progress details.

---

## 🏗️ Project Structure

```
SSHFerry/
├── src/
│   ├── app/           # Entry point & Config
│   ├── core/          # Scheduler & Task Logic
│   ├── engines/       # Transfer Engines (SFTP, MSCP)
│   ├── shared/        # Utils, Logging, Constants
│   └── ui/            # PySide6 Widgets & Windows
├── tests/             # Pytest Unit Tests
└── run.bat / run.sh   # Launch Scripts
```

## 📜 License

This project is intended for educational and personal use.
