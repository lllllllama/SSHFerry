"""Generate docs/assets/hero.png from the real desktop UI with demo data.

Runs the PySide6 main window offscreen, seeds representative sites,
sessions, remote listings, and transfer tasks, and saves a screenshot.

Usage:
  python tools/generate_hero_screenshot.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_DATA_DIR = tempfile.mkdtemp(prefix="sshferry-hero-")
os.environ["SSHFERRY_DATA_DIR"] = _DATA_DIR

WINDOW_SIZE = (1680, 1090)
PRETTY_LOCAL_ROOT = "~/workspace/sshferry-release"
OUTPUT_PATH = Path(_ROOT) / "docs" / "assets" / "hero.png"

DAY = 86400.0


def _make_local_demo_tree() -> str:
    root = Path(_DATA_DIR) / "workspace" / "sshferry-release"
    (root / "dist").mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir(exist_ok=True)
    files = {
        "README.md": 4_210,
        "CHANGELOG.md": 12_804,
        "sshferry-2.1.0-linux.tar.gz": 48_312_842,
        "sshferry-2.1.0-windows.zip": 52_071_115,
        "checksums.sha256": 512,
        "dist/app.js": 406_388,
        "configs/sites.example.json": 2_048,
    }
    for rel_path, size in files.items():
        target = root / rel_path
        target.write_bytes(b"0" * min(size, 4096))
        os.truncate(target, size)
    return str(root)


def main() -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    from src.ui.theme import apply_theme

    apply_theme(app)

    from src.shared.models import RemoteEntry, SiteConfig, Task
    from src.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(*WINDOW_SIZE)
    window.scheduler.stop()

    now = time.time()

    sites = [
        SiteConfig(name="prod-web-01", host="203.0.113.24", port=22, username="deploy",
                   auth_method="key", key_path="~/.ssh/id_ed25519", remote_root="/var/www"),
        SiteConfig(name="gpu-cluster", host="gpu.lab.internal", port=2222, username="research",
                   auth_method="key", key_path="~/.ssh/id_ed25519", remote_root="/data"),
        SiteConfig(name="backup-nas", host="192.168.1.40", port=22, username="backup",
                   auth_method="password", password="demo", remote_root="/volume1"),
    ]
    for site in sites:
        window.sites.append(site)
        window.site_list.addItem(site.name)
    window.site_list.setCurrentRow(0)
    window._refresh_session_selectors()

    def entry(parent: str, name: str, *, is_dir: bool = False, size: int = 0, age_days: float = 1.0) -> RemoteEntry:
        return RemoteEntry(
            name=name,
            path=f"{parent.rstrip('/')}/{name}",
            is_dir=is_dir,
            size=size,
            mtime=now - age_days * DAY,
        )

    prod_session = window.sessions[window._create_session(sites[0])]
    prod_session.connected = True
    prod_session.status_label.setText("Connected: prod-web-01")
    prod_session.panel.set_path("/var/www")
    prod_session.panel.set_root_entries([
        entry("/var/www", "releases", is_dir=True, age_days=0.2),
        entry("/var/www", "shared", is_dir=True, age_days=3.0),
        entry("/var/www", "static", is_dir=True, age_days=1.4),
        entry("/var/www", "current -> releases/2.1.0", is_dir=True, age_days=0.2),
        entry("/var/www", "app.log", size=8_364_211, age_days=0.05),
        entry("/var/www", "nginx.conf", size=3_120, age_days=12.0),
        entry("/var/www", "deploy.lock", size=64, age_days=0.01),
    ])

    gpu_session = window.sessions[window._create_session(sites[1])]
    gpu_session.connected = True
    gpu_session.status_label.setText("Connected: gpu-cluster")
    gpu_session.panel.set_path("/data")
    gpu_session.panel.set_root_entries([
        entry("/data", "datasets", is_dir=True, age_days=6.0),
        entry("/data", "checkpoints", is_dir=True, age_days=0.5),
        entry("/data", "experiments", is_dir=True, age_days=1.1),
        entry("/data", "train_2026q3.tar", size=9_663_676_416, age_days=0.5),
        entry("/data", "eval-results.parquet", size=182_452_224, age_days=0.9),
        entry("/data", "notes.md", size=9_612, age_days=2.2),
    ])

    window._set_active_session(prod_session.session_id)

    local_root = _make_local_demo_tree()
    window.local_panel._navigate_to(local_root)

    def task(task_id: str, kind: str, engine: str, src: str, dst: str, total: int, done: int,
             status: str, *, speed: float = 0.0, sub_total: int = 0, sub_done: int = 0,
             current_file: str = "") -> Task:
        item = Task(
            task_id=task_id, kind=kind, engine=engine, src=src, dst=dst,
            bytes_total=total, bytes_done=done, status=status, speed=speed,
            subtask_count=sub_total, subtask_done=sub_done, current_file=current_file,
        )
        item.start_time = now - 42.0
        if status == "done":
            item.end_time = now - 5.0
            item.avg_speed = speed
        return item

    demo_tasks = [
        task("hero-up", "file_transfer", "parallel",
             f"{PRETTY_LOCAL_ROOT}/sshferry-2.1.0-linux.tar.gz", "/var/www/releases/2.1.0/sshferry.tar.gz",
             48_312_842, 31_002_213, "running", speed=24.8 * 1024 * 1024),
        task("hero-folder", "folder_transfer", "sftp",
             "/data/checkpoints", f"{PRETTY_LOCAL_ROOT}/checkpoints",
             2_147_483_648, 903_872_512, "running", speed=11.2 * 1024 * 1024,
             sub_total=128, sub_done=54, current_file="epoch_054.ckpt"),
        task("hero-r2r", "file_transfer", "dualpath",
             "/data/train_2026q3.tar", "/volume1/archive/train_2026q3.tar",
             9_663_676_416, 9_663_676_416, "done", speed=38.4 * 1024 * 1024),
        task("hero-dl", "file_transfer", "sftp",
             "/var/www/app.log", f"{PRETTY_LOCAL_ROOT}/app.log",
             8_364_211, 0, "pending"),
    ]
    for item in demo_tasks:
        item.src_endpoint_type = "remote" if not item.src.startswith("~") else "local"
        item.dst_endpoint_type = "remote" if not item.dst.startswith("~") else "local"
        window.scheduler.tasks[item.task_id] = item
    window.task_center.set_tasks(demo_tasks)
    window._update_site_action_buttons()
    window._log("Queued release upload to prod-web-01 (parallel, 10 connections)")
    window._log("checkpoints: 54/128 files done, resuming from byte offsets")

    window.show()

    # Give the task table enough height to show all demo rows.
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter

    for splitter in window.findChildren(QSplitter):
        if splitter.orientation() == Qt.Vertical and splitter.count() == 2:
            splitter.setSizes([620, 400])

    # Let QFileSystemModel finish loading the local directory listing.
    loop = QEventLoop()
    window.local_panel.fs_model.directoryLoaded.connect(lambda _path: loop.quit())
    QTimer.singleShot(1500, loop.quit)
    loop.exec()
    for _ in range(5):
        app.processEvents()

    pixmap = window.grab()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(OUTPUT_PATH), "PNG")
    print(f"Wrote {OUTPUT_PATH} ({pixmap.width()}x{pixmap.height()})")

    window.scheduler.stop()
    window.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
