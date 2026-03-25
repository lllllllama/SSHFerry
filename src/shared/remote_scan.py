"""Helpers for accelerating remote tree scans via a single SSH shell command."""
from dataclasses import dataclass
import shlex
import time
from typing import Any


_REMOTE_SCAN_SCRIPT = """
import os
import sys

def fail(message):
    sys.stderr.write(message + "\\n")
    raise SystemExit(1)

root = sys.argv[1]
seen = set()
stack = [(root, "")]
while stack:
    current_root, rel_root = stack.pop()
    try:
        current_real = os.path.realpath(current_root)
    except OSError:
        current_real = current_root
    if current_real in seen:
        continue
    seen.add(current_real)
    try:
        scanned = list(os.scandir(current_root))
    except OSError as exc:
        fail(f"scan_root_failed\\t{current_root}\\t{exc}")

    dirs = []
    files = []
    for entry in scanned:
        rel_path = entry.name if not rel_root else rel_root + "/" + entry.name
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError as exc:
            fail(f"scan_type_failed\\t{rel_path}\\t{exc}")
        if is_dir:
            dirs.append((entry.path, rel_path))
            continue
        try:
            size = entry.stat(follow_symlinks=False).st_size
        except OSError as exc:
            fail(f"scan_stat_failed\\t{rel_path}\\t{exc}")
        files.append((rel_path, size))

    dirs.sort(key=lambda item: item[1])
    files.sort(key=lambda item: item[0])
    for _dir_path, dir_rel_path in dirs:
        sys.stdout.write(f"D\\t0\\t{dir_rel_path}\\n")
    for file_rel_path, file_size in files:
        sys.stdout.write(f"F\\t{file_size}\\t{file_rel_path}\\n")
    for dir_path, dir_rel_path in reversed(dirs):
        stack.append((dir_path, dir_rel_path))
"""


@dataclass(frozen=True)
class RemoteScanEntry:
    rel_path: str
    is_dir: bool
    size: int


def _collect_exec_output(stdout: Any, stderr: Any) -> tuple[int, str, str]:
    """Drain stdout/stderr before waiting for the remote command exit status."""
    channel = getattr(stdout, "channel", None)
    if channel is None:
        return (
            0,
            stdout.read().decode("utf-8", errors="replace"),
            stderr.read().decode("utf-8", errors="replace").strip(),
        )

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    recv = getattr(channel, "recv", None)
    recv_ready = getattr(channel, "recv_ready", None)
    recv_stderr = getattr(channel, "recv_stderr", None)
    recv_stderr_ready = getattr(channel, "recv_stderr_ready", None)
    exit_status_ready = getattr(channel, "exit_status_ready", None)

    if not all(callable(fn) for fn in (recv, recv_ready, recv_stderr, recv_stderr_ready, exit_status_ready)):
        return (
            channel.recv_exit_status(),
            stdout.read().decode("utf-8", errors="replace"),
            stderr.read().decode("utf-8", errors="replace").strip(),
        )

    while True:
        progressed = False
        while channel.recv_ready():
            stdout_chunks.append(channel.recv(32768))
            progressed = True
        while channel.recv_stderr_ready():
            stderr_chunks.append(channel.recv_stderr(32768))
            progressed = True
        if channel.exit_status_ready():
            while channel.recv_ready():
                stdout_chunks.append(channel.recv(32768))
            while channel.recv_stderr_ready():
                stderr_chunks.append(channel.recv_stderr(32768))
            break
        if not progressed:
            time.sleep(0.01)

    return (
        channel.recv_exit_status(),
        b"".join(stdout_chunks).decode("utf-8", errors="replace"),
        b"".join(stderr_chunks).decode("utf-8", errors="replace").strip(),
    )


def _build_remote_scan_command(remote_root: str) -> str:
    shell = (
        "if command -v python3 >/dev/null 2>&1; then PY=python3; "
        "elif command -v python >/dev/null 2>&1; then PY=python; "
        "else exit 127; fi; "
        f'$PY -c {shlex.quote(_REMOTE_SCAN_SCRIPT)} -- {shlex.quote(remote_root)}'
    )
    return "sh -lc " + shlex.quote(shell)


def scan_remote_tree_via_shell(engine: Any, remote_root: str) -> list[RemoteScanEntry] | None:
    """Return remote tree entries using one remote shell traversal when available."""
    ssh_client = getattr(engine, "ssh_client", None)
    if ssh_client is None:
        return None
    try:
        _stdin, stdout, stderr = ssh_client.exec_command(_build_remote_scan_command(remote_root))
        exit_code, output, error_output = _collect_exec_output(stdout, stderr)
        if exit_code != 0:
            return None
    except Exception:
        return None

    entries: list[RemoteScanEntry] = []
    for raw_line in output.splitlines():
        line = raw_line.strip("\r")
        if not line:
            continue
        try:
            entry_type, size_text, rel_path = line.split("\t", 2)
            normalized_rel = rel_path.strip().replace("\\", "/")
            if normalized_rel.startswith("./"):
                normalized_rel = normalized_rel[2:]
            if not normalized_rel:
                continue
            entries.append(
                RemoteScanEntry(
                    rel_path=normalized_rel,
                    is_dir=entry_type == "D",
                    size=int(size_text),
                )
            )
        except (ValueError, TypeError):
            return None

    if not entries:
        try:
            if getattr(engine, "list_dir")(remote_root):
                return None
        except Exception:
            return None

    if error_output:
        # Ignore stderr chatter from remote shells as long as the scan completed.
        return entries
    return entries


def summarize_remote_tree_via_shell(engine: Any, remote_root: str) -> tuple[int, int] | None:
    entries = scan_remote_tree_via_shell(engine, remote_root)
    if entries is None:
        return None
    total_files = 0
    total_bytes = 0
    for entry in entries:
        if entry.is_dir:
            continue
        total_files += 1
        total_bytes += entry.size
    return total_files, total_bytes
