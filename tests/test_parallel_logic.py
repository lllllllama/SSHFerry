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
store_lock = threading.Lock()

@pytest.fixture
def mock_sftp_engine(monkeypatch):
    mock_data_store.clear()
    
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
