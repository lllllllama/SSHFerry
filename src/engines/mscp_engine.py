"""MSCP engine – wraps the external mscp binary for accelerated transfers."""
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.models import SiteConfig

# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MscpPreset:
    """Parameter preset for mscp invocation."""
    name: str
    nr_connections: int   # -n
    nr_ahead: int         # -a
    max_startups: int     # -u
    interval: float       # -I (seconds)


PRESETS: Dict[str, MscpPreset] = {
    "low":    MscpPreset("low",    nr_connections=4,  nr_ahead=32, max_startups=8, interval=0),
    "medium": MscpPreset("medium", nr_connections=8,  nr_ahead=32, max_startups=8, interval=0.1),
    "high":   MscpPreset("high",   nr_connections=16, nr_ahead=64, max_startups=8, interval=0.2),
}

DEFAULT_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class MscpEngine:
    """
    Wraps the external *mscp* binary (subprocess).

    Responsibilities:
    - Build command line from SiteConfig + preset
    - Launch / monitor / cancel the process
    - Support checkpoint save (-W) and restore (-R)
    """

    def __init__(
        self,
        site_config: SiteConfig,
        preset_name: str = "low",
        logger: Optional[logging.Logger] = None,
    ):
        self.site_config = site_config
        self.preset = PRESETS.get(preset_name, PRESETS["low"])
        self.logger = logger or logging.getLogger(__name__)
        self._process: Optional[subprocess.Popen] = None
        self._mscp_path = self._resolve_mscp_path()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if mscp binary is found."""
        return self._mscp_path is not None

    def upload(
        self,
        local_path: str,
        remote_path: str,
        checkpoint_dir: Optional[str] = None,
    ) -> int:
        """
        Upload *local_path* to *remote_path* using mscp.

        Returns the process exit code.
        """
        remote_spec = self._remote_spec(remote_path)
        return self._run(local_path, remote_spec, checkpoint_dir=checkpoint_dir)

    def download(
        self,
        remote_path: str,
        local_path: str,
        checkpoint_dir: Optional[str] = None,
    ) -> int:
        """Download *remote_path* to *local_path* using mscp."""
        remote_spec = self._remote_spec(remote_path)
        return self._run(remote_spec, local_path, checkpoint_dir=checkpoint_dir)

    def resume(self, checkpoint_path: str) -> int:
        """Resume a transfer from a checkpoint file (-R)."""
        if not self._mscp_path:
            raise SSHFerryError(ErrorCode.MSCP_NOT_FOUND, "mscp binary not found")
        cmd = [self._mscp_path, "-R", checkpoint_path]
        self.logger.info(f"mscp resume: {' '.join(cmd)}")
        return self._exec(cmd, cwd=str(Path(checkpoint_path).parent))

    def cancel(self):
        """Kill a running mscp process."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self.logger.info("mscp process terminated")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _remote_spec(self, path: str) -> str:
        """Build the user@host:path spec for mscp."""
        cfg = self.site_config
        return f"{cfg.username}@{cfg.host}:{path}"

    def _run(self, src: str, dst: str, checkpoint_dir: Optional[str] = None) -> int:
        if not self._mscp_path:
            raise SSHFerryError(ErrorCode.MSCP_NOT_FOUND, "mscp binary not found")

        cmd = self._build_cmd(src, dst, checkpoint_dir)
        self.logger.info(f"mscp: {' '.join(cmd)}")
        return self._exec(cmd)

    def _build_cmd(self, src: str, dst: str, checkpoint_dir: Optional[str] = None) -> List[str]:
        p = self.preset
        cfg = self.site_config

        cmd: List[str] = [self._mscp_path]
        cmd += ["-n", str(p.nr_connections)]
        cmd += ["-a", str(p.nr_ahead)]
        cmd += ["-u", str(p.max_startups)]
        if p.interval > 0:
            cmd += ["-I", str(p.interval)]
        cmd += ["-P", str(cfg.port)]

        # SSH options
        if cfg.key_path:
            cmd += ["-i", cfg.key_path]
        if cfg.proxy_jump:
            cmd += ["-J", cfg.proxy_jump]
        if cfg.ssh_config_path:
            cmd += ["-F", cfg.ssh_config_path]
        for opt in cfg.ssh_options:
            cmd += ["-o", opt]

        # Checkpoint save
        if checkpoint_dir:
            os.makedirs(checkpoint_dir, exist_ok=True)
            cmd += ["-W", checkpoint_dir]

        cmd += [src, dst]
        return cmd

    def _exec(self, cmd: List[str], cwd: Optional[str] = None) -> int:
        env = os.environ.copy()
        # Inject password for mscp via env var (if password-based auth)
        if self.site_config.auth_method == "password" and self.site_config.password:
            env["MSCP_SSH_AUTH_PASSWORD"] = self.site_config.password

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=cwd,
        )
        stdout, _ = self._process.communicate()
        rc = self._process.returncode

        if rc != 0:
            output = stdout.decode(errors="replace") if stdout else ""
            self.logger.error(f"mscp exit {rc}: {output[:500]}")

        self._process = None
        return rc

    def _resolve_mscp_path(self) -> Optional[str]:
        """Find the mscp binary."""
        # 1. Explicit config
        if self.site_config.mscp_path and os.path.isfile(self.site_config.mscp_path):
            return self.site_config.mscp_path

        # 2. Bundled under tools/mscp/<platform>/
        import sys
        plat = {"win32": "win", "darwin": "mac", "linux": "linux"}.get(sys.platform, "")
        bundled = Path(__file__).resolve().parent.parent.parent / "tools" / "mscp" / plat / "mscp"
        if bundled.exists():
            return str(bundled)
        # Windows .exe
        if (bundled.with_suffix(".exe")).exists():
            return str(bundled.with_suffix(".exe"))

        # 3. System PATH
        found = shutil.which("mscp")
        return found
