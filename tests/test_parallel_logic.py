import os
import math
import threading
from unittest.mock import MagicMock, patch, ANY
import pytest
from src.engines.parallel_sftp_engine import ParallelSftpEngine
from src.shared.models import SiteConfig

# Mock classes to simulate file operations
class MockFileHandle:
    def __init__(self, data_store, path):
        self.store = data_store
        self.path = path
        self.pos = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def seek(self, offset):
        self.pos = offset

    def read(self, size):
        data = self.store.get(self.path, b'')
        if self.pos >= len(data):
            return b''
        return data[self.pos:self.pos+size]

    def write(self, data):
        # The whole read-modify-write must be atomic: concurrent workers
        # write disjoint offsets of the same path.
        with store_lock:
            mock_write_sizes.setdefault(self.path, []).append(len(data))
            existing = bytearray(self.store.get(self.path, b''))
            end_pos = self.pos + len(data)
            if len(existing) < end_pos:
                existing.extend(b'\0' * (end_pos - len(existing)))
            existing[self.pos:end_pos] = data
            self.store[self.path] = bytes(existing)
        self.pos += len(data)
        
    def truncate(self, size):
        existing = bytearray(self.store.get(self.path, b''))
        if len(existing) > size:
            self.store[self.path] = bytes(existing[:size])
        elif len(existing) < size:
            existing.extend(b'\0' * (size - len(existing)))
            self.store[self.path] = bytes(existing)

    def set_pipelined(self, val):
        pass

class MockSftpClient:
    def __init__(self, data_store):
        self.data_store = data_store

    def open(self, path, mode='r'):
        return MockFileHandle(self.data_store, path)

# Global store for mock tests
mock_data_store = {}
mock_write_sizes = {}
store_lock = threading.Lock()

@pytest.fixture
def mock_sftp_engine(monkeypatch):
    mock_data_store.clear()
    mock_write_sizes.clear()
    
    class MockSftpEngine:
        def __init__(self, *args, **kwargs):
            self.sftp_client = MockSftpClient(mock_data_store)
            
        def connect(self):
            pass
            
        def disconnect(self):
            pass
            
        def stat(self, path):
            size = len(mock_data_store.get(path, b''))
            mock_stat = MagicMock()
            mock_stat.size = size
            return mock_stat

    monkeypatch.setattr("src.engines.parallel_sftp_engine.SftpEngine", MockSftpEngine)
    return mock_data_store

def test_parallel_upload(tmp_path, mock_sftp_engine):
    # Setup local file
    local_path = tmp_path / "large_file.bin"
    file_size = 5 * 1024 * 1024  # 5MB
    chunk_size = 1024 * 1024     # 1MB
    
    expected_data = os.urandom(file_size)
    local_path.write_bytes(expected_data)
    
    config = SiteConfig(
        name="test",
        host="mock", 
        port=22,
        username="user", 
        auth_method="password",
        remote_root="/"
    )
    engine = ParallelSftpEngine(config, max_workers=2, chunk_size=chunk_size)
    
    remote_path = "/remote/uploaded.bin"
    
    # Execute
    engine.upload_file(str(local_path), remote_path)
    
    # Verify
    assert mock_sftp_engine[remote_path] == expected_data

def test_parallel_download(tmp_path, mock_sftp_engine):
    # Setup remote file
    remote_path = "/remote/download.bin"
    file_size = 5 * 1024 * 1024
    chunk_size = 1024 * 1024
    
    expected_data = os.urandom(file_size)
    mock_sftp_engine[remote_path] = expected_data
    
    # Mock stat
    # The fixture already mocks stat 
    
    config = SiteConfig(
        name="test",
        host="mock", 
        port=22,
        username="user", 
        auth_method="password",
        remote_root="/"
    )
    engine = ParallelSftpEngine(config, max_workers=2, chunk_size=chunk_size)
    
    local_path = tmp_path / "downloaded.bin"
    
    # Execute
    engine.download_file(remote_path, str(local_path))
    
    # Verify
    assert local_path.read_bytes() == expected_data


def test_parallel_engine_warmup_starts_gradually(monkeypatch):
    config = SiteConfig(
        name="test",
        host="mock",
        port=22,
        username="user",
        auth_method="password",
        remote_root="/"
    )
    engine = ParallelSftpEngine(config, max_workers=4, chunk_size=1024 * 1024)
    engine.initial_workers = 1
    engine.worker_ramp_step = 1
    engine.warmup_delay_seconds = 0.01

    submitted: list[int] = []
    sleeps: list[float] = []

    class FakeExecutor:
        def submit(self, worker):
            submitted.append(len(submitted) + 1)
            return MagicMock()

    lock = threading.Lock()

    monkeypatch.setattr("src.engines.parallel_sftp_engine.time.sleep", lambda value: sleeps.append(value))

    futures = engine._launch_workers_adaptively(
        FakeExecutor(),
        lambda: None,
        4,
        lock,
        lambda: 0,
    )

    assert len(futures) == 4
    assert submitted == [1, 2, 3, 4]
    assert len(sleeps) == 3


def test_parallel_download_worker_does_not_log_paused_interrupt(tmp_path, monkeypatch):
    remote_path = "/remote/download.bin"
    expected_data = os.urandom(2 * 1024 * 1024)
    mock_data_store[remote_path] = expected_data

    class MockSftpEngine:
        def __init__(self, *args, **kwargs):
            self.sftp_client = MockSftpClient(mock_data_store)

        def connect(self):
            pass

        def disconnect(self):
            pass

        def stat(self, path):
            mock_stat = MagicMock()
            mock_stat.size = len(mock_data_store.get(path, b""))
            return mock_stat

    monkeypatch.setattr("src.engines.parallel_sftp_engine.SftpEngine", MockSftpEngine)

    config = SiteConfig(
        name="test",
        host="mock",
        port=22,
        username="user",
        auth_method="password",
        remote_root="/"
    )
    logger = MagicMock()
    engine = ParallelSftpEngine(config, logger=logger, max_workers=2, chunk_size=1024 * 1024)

    with pytest.raises(InterruptedError):
        engine.download_file(remote_path, str(tmp_path / "dl.bin"), check_interrupt=lambda: (_ for _ in ()).throw(InterruptedError("Task paused")))

    logger.error.assert_not_called()


def test_parallel_upload_uses_io_block_bytes_separately_from_progress_reporting(tmp_path, mock_sftp_engine):
    local_path = tmp_path / "large_file.bin"
    file_size = 8 * 1024 * 1024
    expected_data = os.urandom(file_size)
    local_path.write_bytes(expected_data)

    config = SiteConfig(
        name="test",
        host="mock",
        port=22,
        username="user",
        auth_method="password",
        remote_root="/"
    )
    engine = ParallelSftpEngine(config, max_workers=1, chunk_size=file_size)
    engine.io_block_bytes = 4 * 1024 * 1024
    engine.progress_report_bytes = 1024 * 1024

    remote_path = "/remote/uploaded-io-block.bin"
    progress_updates: list[int] = []

    engine.upload_file(
        str(local_path),
        remote_path,
        callback=lambda done, _total: progress_updates.append(done),
    )

    assert mock_sftp_engine[remote_path] == expected_data
    assert mock_write_sizes[remote_path] == [4 * 1024 * 1024, 4 * 1024 * 1024]
    assert progress_updates == [4 * 1024 * 1024, 8 * 1024 * 1024]
