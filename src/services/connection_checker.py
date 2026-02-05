"""Connection self-check utility for SSH/SFTP connections."""
from dataclasses import dataclass
from typing import Optional

from ..engines.sftp_engine import SftpEngine
from ..shared.errors import SSHFerryError
from ..shared.models import SiteConfig


@dataclass
class CheckResult:
    """Result of a single connection check."""
    
    name: str
    passed: bool
    message: str
    error: Optional[Exception] = None


class ConnectionChecker:
    """Performs comprehensive connection checks for SSH sites."""
    
    def __init__(self, site_config: SiteConfig):
        """
        Initialize connection checker.
        
        Args:
            site_config: Site configuration to check
        """
        self.site_config = site_config
        self.results: list[CheckResult] = []
    
    def run_all_checks(self) -> list[CheckResult]:
        """
        Run all connection checks.
        
        Returns:
            List of check results
        """
        self.results = []
        
        # Check 1: TCP connection
        self.results.append(self._check_tcp())
        if not self.results[-1].passed:
            return self.results
        
        # Check 2: SSH handshake
        self.results.append(self._check_ssh())
        if not self.results[-1].passed:
            return self.results
        
        # Check 3: SFTP subsystem
        self.results.append(self._check_sftp())
        if not self.results[-1].passed:
            return self.results
        
        # Check 4: Remote root readable
        self.results.append(self._check_remote_root_readable())
        
        # Check 5: Remote root writable
        self.results.append(self._check_remote_root_writable())
        
        return self.results
    
    def _check_tcp(self) -> CheckResult:
        """Check if TCP connection can be established."""
        import socket
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.site_config.host, self.site_config.port))
            sock.close()
            return CheckResult(
                name="TCP Connection",
                passed=True,
                message=f"Successfully connected to {self.site_config.host}:{self.site_config.port}"
            )
        except Exception as e:
            return CheckResult(
                name="TCP Connection",
                passed=False,
                message=f"Failed to connect: {e}",
                error=e
            )
    
    def _check_ssh(self) -> CheckResult:
        """Check if SSH handshake succeeds."""
        try:
            engine = SftpEngine(self.site_config)
            engine.connect()
            
            # Just check if connected
            if engine.is_connected():
                engine.disconnect()
                return CheckResult(
                    name="SSH Handshake",
                    passed=True,
                    message="SSH authentication successful"
                )
            else:
                return CheckResult(
                    name="SSH Handshake",
                    passed=False,
                    message="Failed to establish SSH connection"
                )
        except SSHFerryError as e:
            return CheckResult(
                name="SSH Handshake",
                passed=False,
                message=f"SSH error: {e.message}",
                error=e
            )
        except Exception as e:
            return CheckResult(
                name="SSH Handshake",
                passed=False,
                message=f"Unexpected error: {e}",
                error=e
            )
    
    def _check_sftp(self) -> CheckResult:
        """Check if SFTP subsystem is available."""
        try:
            engine = SftpEngine(self.site_config)
            engine.connect()
            
            if engine.sftp_client:
                engine.disconnect()
                return CheckResult(
                    name="SFTP Subsystem",
                    passed=True,
                    message="SFTP subsystem is available"
                )
            else:
                engine.disconnect()
                return CheckResult(
                    name="SFTP Subsystem",
                    passed=False,
                    message="SFTP subsystem not available"
                )
        except Exception as e:
            return CheckResult(
                name="SFTP Subsystem",
                passed=False,
                message=f"SFTP error: {e}",
                error=e
            )
    
    def _check_remote_root_readable(self) -> CheckResult:
        """Check if remote_root directory is readable."""
        try:
            engine = SftpEngine(self.site_config)
            engine.connect()
            
            is_readable = engine.check_path_readable(self.site_config.remote_root)
            engine.disconnect()
            
            if is_readable:
                return CheckResult(
                    name="Remote Root Readable",
                    passed=True,
                    message=f"Can read {self.site_config.remote_root}"
                )
            else:
                return CheckResult(
                    name="Remote Root Readable",
                    passed=False,
                    message=f"Cannot read {self.site_config.remote_root}"
                )
        except Exception as e:
            return CheckResult(
                name="Remote Root Readable",
                passed=False,
                message=f"Error checking readability: {e}",
                error=e
            )
    
    def _check_remote_root_writable(self) -> CheckResult:
        """Check if remote_root directory is writable."""
        try:
            engine = SftpEngine(self.site_config)
            engine.connect()
            
            is_writable = engine.check_path_writable(self.site_config.remote_root)
            engine.disconnect()
            
            if is_writable:
                return CheckResult(
                    name="Remote Root Writable",
                    passed=True,
                    message=f"Can write to {self.site_config.remote_root}"
                )
            else:
                return CheckResult(
                    name="Remote Root Writable",
                    passed=False,
                    message=f"Cannot write to {self.site_config.remote_root}"
                )
        except Exception as e:
            return CheckResult(
                name="Remote Root Writable",
                passed=False,
                message=f"Error checking writability: {e}",
                error=e
            )
    
    def all_passed(self) -> bool:
        """Check if all tests passed."""
        return all(result.passed for result in self.results)
    
    def get_summary(self) -> str:
        """Get a summary of all check results."""
        lines = []
        for result in self.results:
            status = "✓" if result.passed else "✗"
            lines.append(f"{status} {result.name}: {result.message}")
        return "\n".join(lines)
