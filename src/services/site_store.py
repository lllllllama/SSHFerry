"""Site configuration storage."""
import json
import logging
from pathlib import Path
from typing import List, Optional

from src.shared.models import SiteConfig

logger = logging.getLogger(__name__)

# Fields that are safe to persist (no secrets)
_PERSIST_FIELDS = [
    "name", "host", "port", "username", "auth_method", "remote_root",
    "key_path", "proxy_jump", "ssh_config_path", "ssh_options",
]


def _default_store_path() -> Path:
    """Return platform-appropriate config directory."""
    import sys
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "SSHFerry"
    else:
        base = Path.home() / ".config" / "sshferry"
    base.mkdir(parents=True, exist_ok=True)
    return base / "sites.json"


class SiteStore:
    """Load / save SiteConfig list from a JSON file (no passwords persisted)."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or _default_store_path()

    def load(self) -> List[SiteConfig]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            sites = []
            for item in data:
                sites.append(SiteConfig(
                    name=item["name"],
                    host=item["host"],
                    port=item.get("port", 22),
                    username=item["username"],
                    auth_method=item.get("auth_method", "password"),
                    remote_root=item.get("remote_root", "/") or "/",
                    key_path=item.get("key_path"),
                    proxy_jump=item.get("proxy_jump"),
                    ssh_config_path=item.get("ssh_config_path"),
                    ssh_options=item.get("ssh_options", []),
                ))
            logger.info(f"Loaded {len(sites)} sites from {self.path}")
            return sites
        except Exception as exc:
            logger.error(f"Failed to load sites: {exc}")
            return []

    def save(self, sites: list[SiteConfig]) -> None:
        data = []
        for site in sites:
            item = {f: getattr(site, f) for f in _PERSIST_FIELDS}
            data.append(item)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Saved {len(sites)} sites to {self.path}")
