import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engines.sftp_engine import SftpEngine, SiteConfig, ErrorCode, SSHFerryError

class TestRecursiveDelete(unittest.TestCase):
    def setUp(self):
        self.site = SiteConfig(
            name="test",
            host="localhost",
            port=22,
            username="user",
            auth_method="password",
            remote_root="/sandbox"
        )
        self.engine = SftpEngine(self.site)
        self.engine.ssh_client = MagicMock()
        self.engine._connected = True

    def test_recursive_delete_command(self):
        # Mock ssh channel exit status
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        self.engine.ssh_client.exec_command.return_value = (None, mock_stdout, None)

        self.engine.remove_dir_recursive("/sandbox/folder")
        
        # Verify rm -rf was called
        self.engine.ssh_client.exec_command.assert_called_with("rm -rf '/sandbox/folder'")

    def test_recursive_delete_safety(self):
        # Should raise error for root
        with self.assertRaises(SSHFerryError):
            self.engine.remove_dir_recursive("/")
            
        with self.assertRaises(SSHFerryError):
            self.engine.remove_dir_recursive("/sandbox")

    def test_recursive_delete_failure(self):
        # Mock failure
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 1
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b"Permission denied"
        
        self.engine.ssh_client.exec_command.return_value = (None, mock_stdout, mock_stderr)

        with self.assertRaises(SSHFerryError) as cm:
            self.engine.remove_dir_recursive("/sandbox/folder")
        
        self.assertIn("Recursive delete failed", str(cm.exception))

if __name__ == '__main__':
    unittest.main()
