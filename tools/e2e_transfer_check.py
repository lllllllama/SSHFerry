"""End-to-end transfer verification against a real SSH server.

Exercises the actual transfer stack (paramiko against sshd): single-file
upload/download, resume from offset in both directions, parallel chunked
transfer, and scheduler-driven folder transfers, verifying data integrity
and progress accounting.

The target account's file system must be locally visible (i.e. localhost),
because integrity checks compare both sides directly.

Environment:
  SSHFERRY_E2E_HOST         default 127.0.0.1
  SSHFERRY_E2E_PORT         default 2222
  SSHFERRY_E2E_USER         default current user
  SSHFERRY_E2E_KEY          path to a private key accepted by the server
  SSHFERRY_E2E_REMOTE_ROOT  writable directory used as the remote sandbox
  SSHFERRY_E2E_WORK_DIR     scratch dir for local test data (default: temp)

Usage:
  python tools/e2e_transfer_check.py
"""
from __future__ import annotations

import getpass
import hashlib
import os
import shutil
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.core.scheduler import TaskScheduler
from src.engines.parallel_sftp_engine import ParallelSftpEngine
from src.engines.sftp_engine import SftpEngine
from src.shared.models import SiteConfig, Task

HOST = os.getenv("SSHFERRY_E2E_HOST", "127.0.0.1")
PORT = int(os.getenv("SSHFERRY_E2E_PORT", "2222"))
USER = os.getenv("SSHFERRY_E2E_USER", getpass.getuser())
KEY_PATH = os.getenv("SSHFERRY_E2E_KEY", "")
REMOTE_ROOT = os.getenv("SSHFERRY_E2E_REMOTE_ROOT", "")
WORK_DIR = os.getenv("SSHFERRY_E2E_WORK_DIR", "") or tempfile.mkdtemp(prefix="sshferry-e2e-")

failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {extra}".rstrip())
    if not cond:
        failures.append(name)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_file(path: str, size: int, seed: int = 0) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        remaining = size
        pattern = bytes([seed % 256]) * 65536
        while remaining > 0:
            block = min(65536, remaining)
            handle.write(os.urandom(block) if seed == 0 else pattern[:block])
            remaining -= block


def main() -> int:
    if not KEY_PATH or not REMOTE_ROOT:
        print("SSHFERRY_E2E_KEY and SSHFERRY_E2E_REMOTE_ROOT are required", file=sys.stderr)
        return 2

    site = SiteConfig(
        name="e2e",
        host=HOST,
        port=PORT,
        username=USER,
        auth_method="key",
        key_path=KEY_PATH,
        remote_root=REMOTE_ROOT,
    )
    now = time.time

    # 1. Single-connection upload + download (readv-pipelined path).
    src = os.path.join(WORK_DIR, "single_20mb.bin")
    make_file(src, 20 * 1024 * 1024)
    engine = SftpEngine(site)
    engine.connect()
    try:
        engine.upload_file(src, f"{REMOTE_ROOT}/single_20mb.bin")
        dst = os.path.join(WORK_DIR, "single_20mb.down")
        progress: list[tuple[int, int]] = []
        engine.download_file(
            f"{REMOTE_ROOT}/single_20mb.bin", dst,
            callback=lambda done, total: progress.append((done, total)),
        )
        check("single up/down integrity", sha256(src) == sha256(dst))
        check(
            "download progress monotonic and complete",
            bool(progress)
            and progress[-1][0] == 20 * 1024 * 1024
            and all(a[0] <= b[0] for a, b in zip(progress, progress[1:])),
        )

        # 2. Resume download from an offset.
        partial = os.path.join(WORK_DIR, "single_20mb.partial")
        shutil.copyfile(dst, partial)
        with open(partial, "r+b") as handle:
            handle.truncate(7 * 1024 * 1024)
        engine.download_file(f"{REMOTE_ROOT}/single_20mb.bin", partial, offset=7 * 1024 * 1024)
        check("resume download integrity", sha256(src) == sha256(partial))

        # 3. Resume upload from an offset.
        resume_src = os.path.join(WORK_DIR, "resume_up.bin")
        make_file(resume_src, 6 * 1024 * 1024)
        engine.upload_file(resume_src, f"{REMOTE_ROOT}/resume_up.bin")
        os.truncate(os.path.join(REMOTE_ROOT, "resume_up.bin"), 2 * 1024 * 1024)
        engine.upload_file(resume_src, f"{REMOTE_ROOT}/resume_up.bin", offset=2 * 1024 * 1024)
        check("resume upload integrity", sha256(resume_src) == sha256(os.path.join(REMOTE_ROOT, "resume_up.bin")))
    finally:
        engine.disconnect()

    # 4. Parallel chunked upload + download.
    big = os.path.join(WORK_DIR, "big_120mb.bin")
    make_file(big, 120 * 1024 * 1024)
    parallel = ParallelSftpEngine(site, preset_name="medium")
    parallel.upload_file(big, f"{REMOTE_ROOT}/big_120mb.bin")
    parallel_dst = os.path.join(WORK_DIR, "big_120mb.down")
    parallel_progress: list[int] = []
    parallel.download_file(
        f"{REMOTE_ROOT}/big_120mb.bin", parallel_dst,
        callback=lambda done, _total: parallel_progress.append(done),
    )
    check("parallel up/down integrity", sha256(big) == sha256(parallel_dst))
    check(
        "parallel progress within bounds",
        all(value <= 120 * 1024 * 1024 for value in parallel_progress)
        and parallel_progress[-1] == 120 * 1024 * 1024,
    )

    # 5. Folder transfer through the scheduler (persistent worker engines).
    tree = os.path.join(WORK_DIR, "tree")
    shutil.rmtree(tree, ignore_errors=True)
    total_bytes = 0
    for index in range(40):
        rel = f"sub{index % 4}/file_{index:03d}.txt"
        size = 20000 + index * 137
        make_file(os.path.join(tree, rel), size, seed=index + 1)
        total_bytes += size

    scheduler = TaskScheduler(site_config=site)
    upload_task = Task(
        task_id="e2e_folder_up", kind="folder_transfer", engine="sftp",
        src=tree, dst=f"{REMOTE_ROOT}/tree_up", bytes_total=total_bytes,
        subtask_count=40, dst_site_snapshot=site,
    )
    upload_task.start_time = now()
    bootstrap = SftpEngine(site)
    bootstrap.connect()
    try:
        scheduler._upload_dir_recursive(bootstrap, upload_task, tree, f"{REMOTE_ROOT}/tree_up")
    finally:
        bootstrap.disconnect()
    intact = all(
        sha256(os.path.join(tree, f"sub{i % 4}/file_{i:03d}.txt"))
        == sha256(os.path.join(REMOTE_ROOT, "tree_up", f"sub{i % 4}", f"file_{i:03d}.txt"))
        for i in range(40)
    )
    check("folder upload integrity (40 files)", intact)
    check(
        "folder upload progress accounting",
        upload_task.bytes_done == total_bytes and upload_task.subtask_done == 40,
        f"(bytes {upload_task.bytes_done}/{total_bytes}, files {upload_task.subtask_done}/40)",
    )

    download_tree = os.path.join(WORK_DIR, "tree_down")
    shutil.rmtree(download_tree, ignore_errors=True)
    download_task = Task(
        task_id="e2e_folder_down", kind="folder_transfer", engine="sftp",
        src=f"{REMOTE_ROOT}/tree_up", dst=download_tree, bytes_total=total_bytes,
        subtask_count=40, src_site_snapshot=site,
    )
    download_task.start_time = now()
    bootstrap = SftpEngine(site)
    bootstrap.connect()
    try:
        scheduler._download_dir_recursive(bootstrap, download_task, f"{REMOTE_ROOT}/tree_up", download_tree)
    finally:
        bootstrap.disconnect()
    intact = all(
        sha256(os.path.join(tree, f"sub{i % 4}/file_{i:03d}.txt"))
        == sha256(os.path.join(download_tree, f"sub{i % 4}", f"file_{i:03d}.txt"))
        for i in range(40)
    )
    check("folder download integrity (40 files)", intact)
    check(
        "folder download progress accounting",
        download_task.bytes_done == total_bytes and download_task.subtask_done == 40,
        f"(bytes {download_task.bytes_done}/{total_bytes}, files {download_task.subtask_done}/40)",
    )

    print()
    if failures:
        print(f"E2E RESULT: {len(failures)} FAILURES: {failures}")
        return 1
    print("E2E RESULT: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
