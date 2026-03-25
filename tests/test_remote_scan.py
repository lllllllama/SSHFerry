import types

from src.shared.remote_scan import (
    _REMOTE_SCAN_SCRIPT,
    RemoteScanEntry,
    scan_remote_tree_via_shell,
    summarize_remote_tree_via_shell,
)


class _FakeStdout:
    def __init__(self, text: str, exit_code: int = 0):
        self._payload = text.encode("utf-8")
        self.channel = types.SimpleNamespace(recv_exit_status=lambda: exit_code)

    def read(self):
        return self._payload


class _FakeStderr:
    def __init__(self, text: str = ""):
        self._payload = text.encode("utf-8")

    def read(self):
        return self._payload


class _FakeSshClient:
    def __init__(self, stdout_text: str, exit_code: int = 0, stderr_text: str = ""):
        self.stdout_text = stdout_text
        self.exit_code = exit_code
        self.stderr_text = stderr_text

    def exec_command(self, _command: str):
        return None, _FakeStdout(self.stdout_text, self.exit_code), _FakeStderr(self.stderr_text)


def test_scan_remote_tree_via_shell_parses_entries():
    engine = types.SimpleNamespace(
        ssh_client=_FakeSshClient("D\t0\tnested\nF\t12\tnested/a.jpg\nF\t8\troot.png\n"),
    )

    entries = scan_remote_tree_via_shell(engine, "/remote/root")

    assert entries == [
        RemoteScanEntry(rel_path="nested", is_dir=True, size=0),
        RemoteScanEntry(rel_path="nested/a.jpg", is_dir=False, size=12),
        RemoteScanEntry(rel_path="root.png", is_dir=False, size=8),
    ]


def test_summarize_remote_tree_via_shell_counts_only_files():
    engine = types.SimpleNamespace(
        ssh_client=_FakeSshClient("D\t0\tnested\nF\t12\tnested/a.jpg\nF\t8\troot.png\n"),
    )

    summary = summarize_remote_tree_via_shell(engine, "/remote/root")

    assert summary == (2, 20)


def test_scan_remote_tree_via_shell_falls_back_when_empty_result_is_suspicious():
    engine = types.SimpleNamespace(
        ssh_client=_FakeSshClient(""),
        list_dir=lambda _path: [object()],
    )

    entries = scan_remote_tree_via_shell(engine, "/remote/root")

    assert entries is None


def test_scan_remote_tree_via_shell_falls_back_on_remote_scan_error():
    engine = types.SimpleNamespace(
        ssh_client=_FakeSshClient("", exit_code=1, stderr_text="scan_root_failed\t/remote/root\tpermission denied"),
    )

    entries = scan_remote_tree_via_shell(engine, "/remote/root")

    assert entries is None


class _StreamingChannel:
    def __init__(self, stdout_chunks: list[bytes], stderr_chunks: list[bytes] | None = None, exit_code: int = 0):
        self._stdout_chunks = list(stdout_chunks)
        self._stderr_chunks = list(stderr_chunks or [])
        self._exit_code = exit_code

    def recv_ready(self):
        return bool(self._stdout_chunks)

    def recv(self, _size: int):
        return self._stdout_chunks.pop(0)

    def recv_stderr_ready(self):
        return bool(self._stderr_chunks)

    def recv_stderr(self, _size: int):
        return self._stderr_chunks.pop(0)

    def exit_status_ready(self):
        return not self._stdout_chunks and not self._stderr_chunks

    def recv_exit_status(self):
        if self._stdout_chunks or self._stderr_chunks:
            raise AssertionError("exit status requested before channel output was drained")
        return self._exit_code


class _StreamingPipe:
    def __init__(self, channel: _StreamingChannel):
        self.channel = channel


class _StreamingSshClient:
    def __init__(self, channel: _StreamingChannel):
        self.channel = channel

    def exec_command(self, _command: str):
        pipe = _StreamingPipe(self.channel)
        return None, pipe, pipe


def test_scan_remote_tree_via_shell_drains_channel_output_before_exit_status():
    channel = _StreamingChannel([b"F\t12\tnested/a.jpg\n", b"F\t8\troot.png\n"])
    engine = types.SimpleNamespace(ssh_client=_StreamingSshClient(channel))

    entries = scan_remote_tree_via_shell(engine, "/remote/root")

    assert entries == [
        RemoteScanEntry(rel_path="nested/a.jpg", is_dir=False, size=12),
        RemoteScanEntry(rel_path="root.png", is_dir=False, size=8),
    ]


def test_remote_scan_script_does_not_follow_symlink_targets():
    assert "follow_symlinks=True" not in _REMOTE_SCAN_SCRIPT
    assert "follow_symlinks=False" in _REMOTE_SCAN_SCRIPT
