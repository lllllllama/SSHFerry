"""Connection self-check utility for SSH/SFTP connections."""
import socket
from dataclasses import dataclass
from typing import Optional

from src.engines.sftp_engine import SftpEngine
from src.shared.errors import SSHFerryError
from src.shared.models import SiteConfig


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

        engine = SftpEngine(self.site_config)
        try:
            engine.connect()

            # Check 2: SSH handshake
            self.results.append(self._check_ssh(engine))
            if not self.results[-1].passed:
                return self.results

            # Check 3: SFTP subsystem
            self.results.append(self._check_sftp(engine))
            if not self.results[-1].passed:
                return self.results

            # Check 4: Remote root readable
            self.results.append(self._check_remote_root_readable(engine))

            # Check 5: Remote root writable
            self.results.append(self._check_remote_root_writable(engine))
        except SSHFerryError as e:
            self.results.append(
                CheckResult(
                    name="SSH Handshake",
                    passed=False,
                    message=f"SSH error: {e.message}",
                    error=e,
                )
            )
        except Exception as e:
            self.results.append(
                CheckResult(
                    name="SSH Handshake",
                    passed=False,
                    message=f"Unexpected error: {e}",
                    error=e,
                )
            )
        finally:
            try:
                engine.disconnect()
            except Exception:
                pass

        return self.results

    def _check_tcp(self) -> CheckResult:
        """Check if TCP connection can be established."""
        try:
            # create_connection resolves both IPv4 and IPv6 addresses.
            with socket.create_connection(
                (self.site_config.host, self.site_config.port), timeout=5
            ):
                pass
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

    def _check_ssh(self, engine: Optional[SftpEngine] = None) -> CheckResult:
        """Check if SSH handshake succeeds."""
        try:
            if engine is not None:
                if engine.is_connected():
                    return CheckResult(
                        name="SSH Handshake",
                        passed=True,
                        message="SSH authentication successful"
                    )
                return CheckResult(
                    name="SSH Handshake",
                    passed=False,
                    message="Failed to establish SSH connection"
                )

            with SftpEngine(self.site_config) as local_engine:
                if local_engine.is_connected():
                    return CheckResult(
                        name="SSH Handshake",
                        passed=True,
                        message="SSH authentication successful"
                    )
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

    def _check_sftp(self, engine: Optional[SftpEngine] = None) -> CheckResult:
        """Check if SFTP subsystem is available."""
        try:
            if engine is not None:
                if engine.sftp_client:
                    return CheckResult(
                        name="SFTP Subsystem",
                        passed=True,
                        message="SFTP subsystem is available"
                    )
                return CheckResult(
                    name="SFTP Subsystem",
                    passed=False,
                    message="SFTP subsystem not available"
                )

            with SftpEngine(self.site_config) as local_engine:
                if local_engine.sftp_client:
                    return CheckResult(
                        name="SFTP Subsystem",
                        passed=True,
                        message="SFTP subsystem is available"
                    )
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

    def _check_remote_root_readable(self, engine: Optional[SftpEngine] = None) -> CheckResult:
        """Check if remote_root directory is readable."""
        try:
            if engine is not None:
                is_readable = engine.check_path_readable(self.site_config.remote_root)
            else:
                with SftpEngine(self.site_config) as local_engine:
                    is_readable = local_engine.check_path_readable(self.site_config.remote_root)

            if is_readable:
                return CheckResult(
                    name="Remote Root Readable",
                    passed=True,
                    message=f"Can read {self.site_config.remote_root}"
                )
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

    def _check_remote_root_writable(self, engine: Optional[SftpEngine] = None) -> CheckResult:
        """Check if remote_root directory is writable."""
        try:
            if engine is not None:
                is_writable = engine.check_path_writable(self.site_config.remote_root)
            else:
                with SftpEngine(self.site_config) as local_engine:
                    is_writable = local_engine.check_path_writable(self.site_config.remote_root)

            if is_writable:
                return CheckResult(
                    name="Remote Root Writable",
                    passed=True,
                    message=f"Can write to {self.site_config.remote_root}"
                )
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
            status = "PASS" if result.passed else "FAIL"
            lines.append(f"{status} {result.name}: {result.message}")
        return "\n".join(lines)
