"""Metrics service for tracking transfer statistics and adaptive preset selection.

This module implements session-level adaptive strategy per agent.md Milestone 5:
- Records transfer statistics (speed, duration, success rate) per preset
- Provides recommendations for optimal preset based on historical data
- Persists metrics to JSON for cross-session learning
"""
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TransferRecord:
    """Record of a single transfer for metrics collection."""
    preset: str           # "low" / "medium" / "high"
    bytes_transferred: int
    duration_seconds: float
    success: bool
    timestamp: float      # Unix timestamp
    
    @property
    def speed_mbps(self) -> float:
        """Calculate speed in MB/s."""
        if self.duration_seconds <= 0:
            return 0.0
        return (self.bytes_transferred / (1024 * 1024)) / self.duration_seconds


@dataclass
class PresetStats:
    """Aggregated statistics for a single preset."""
    preset: str
    total_transfers: int = 0
    successful_transfers: int = 0
    total_bytes: int = 0
    total_duration: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Success rate as a percentage (0-100)."""
        if self.total_transfers == 0:
            return 0.0
        return (self.successful_transfers / self.total_transfers) * 100.0
    
    @property
    def avg_speed_mbps(self) -> float:
        """Average speed in MB/s."""
        if self.total_duration <= 0:
            return 0.0
        return (self.total_bytes / (1024 * 1024)) / self.total_duration


def _default_metrics_path() -> Path:
    """Return platform-appropriate metrics storage path."""
    import sys
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "SSHFerry"
    else:
        base = Path.home() / ".config" / "sshferry"
    base.mkdir(parents=True, exist_ok=True)
    return base / "metrics.json"


class MetricsCollector:
    """
    Collects transfer metrics and provides adaptive preset recommendations.
    
    Adaptive Strategy (per agent.md):
    - Tracks recent N transfers per preset
    - Recommends downgrade if failure rate > 20%
    - Recommends upgrade if success rate > 95% and speed stable
    - Uses cooldown period to avoid frequent changes
    """
    
    # Configuration
    MAX_RECORDS = 100           # Maximum records to keep
    SAMPLE_WINDOW = 10          # Recent transfers to consider for decisions
    FAILURE_THRESHOLD = 0.20    # 20% failure rate triggers downgrade
    SUCCESS_THRESHOLD = 0.95    # 95% success rate allows upgrade consideration
    COOLDOWN_SECONDS = 300      # 5 minutes between preset changes
    
    PRESET_ORDER = ["low", "medium", "high"]
    
    def __init__(self, store_path: Optional[Path] = None):
        """
        Initialize metrics collector.
        
        Args:
            store_path: Path to JSON storage file. Uses default if None.
        """
        self.store_path = store_path or _default_metrics_path()
        self.records: List[TransferRecord] = []
        self.last_preset_change: float = 0.0
        self.current_preset: str = "low"
        self._load()
    
    def record(self, record: TransferRecord) -> None:
        """
        Record a transfer result.
        
        Args:
            record: TransferRecord with transfer details
        """
        self.records.append(record)
        
        # Keep only recent records
        if len(self.records) > self.MAX_RECORDS:
            self.records = self.records[-self.MAX_RECORDS:]
        
        self._save()
        logger.debug(f"Recorded transfer: {record.preset}, "
                     f"{record.bytes_transferred} bytes, "
                     f"success={record.success}")
    
    def get_recommended_preset(self) -> str:
        """
        Get recommended preset based on recent transfer history.
        
        Returns:
            Recommended preset name ("low", "medium", or "high")
        """
        if not self.records:
            return "low"  # Default to safe preset
        
        # Check cooldown
        now = time.time()
        if now - self.last_preset_change < self.COOLDOWN_SECONDS:
            return self.current_preset
        
        # Analyze recent transfers for current preset
        recent = [r for r in self.records[-self.SAMPLE_WINDOW:] 
                  if r.preset == self.current_preset]
        
        if len(recent) < 3:
            # Not enough data, stay with current
            return self.current_preset
        
        # Calculate success rate
        success_count = sum(1 for r in recent if r.success)
        success_rate = success_count / len(recent)
        
        current_idx = self.PRESET_ORDER.index(self.current_preset)
        
        # Check for downgrade
        if success_rate < (1 - self.FAILURE_THRESHOLD):
            if current_idx > 0:
                new_preset = self.PRESET_ORDER[current_idx - 1]
                self.current_preset = new_preset
                self.last_preset_change = now
                logger.info(f"Adaptive: Downgrading preset to {new_preset} "
                           f"(success rate {success_rate:.1%})")
                self._save()
                return new_preset
        
        # Check for upgrade
        if success_rate >= self.SUCCESS_THRESHOLD:
            if current_idx < len(self.PRESET_ORDER) - 1:
                new_preset = self.PRESET_ORDER[current_idx + 1]
                self.current_preset = new_preset
                self.last_preset_change = now
                logger.info(f"Adaptive: Upgrading preset to {new_preset} "
                           f"(success rate {success_rate:.1%})")
                self._save()
                return new_preset
        
        return self.current_preset
    
    def get_stats(self) -> Dict[str, PresetStats]:
        """
        Get aggregated statistics per preset.
        
        Returns:
            Dictionary mapping preset name to PresetStats
        """
        stats: Dict[str, PresetStats] = {}
        
        for preset in self.PRESET_ORDER:
            preset_records = [r for r in self.records if r.preset == preset]
            
            stats[preset] = PresetStats(
                preset=preset,
                total_transfers=len(preset_records),
                successful_transfers=sum(1 for r in preset_records if r.success),
                total_bytes=sum(r.bytes_transferred for r in preset_records),
                total_duration=sum(r.duration_seconds for r in preset_records),
            )
        
        return stats
    
    def _load(self) -> None:
        """Load metrics from storage."""
        if not self.store_path.exists():
            return
        
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.records = [
                TransferRecord(**r) for r in data.get("records", [])
            ]
            self.current_preset = data.get("current_preset", "low")
            self.last_preset_change = data.get("last_preset_change", 0.0)
            logger.info(f"Loaded {len(self.records)} metric records from {self.store_path}")
        except Exception as e:
            logger.warning(f"Failed to load metrics: {e}")
            self.records = []
    
    def _save(self) -> None:
        """Save metrics to storage."""
        try:
            data = {
                "records": [asdict(r) for r in self.records],
                "current_preset": self.current_preset,
                "last_preset_change": self.last_preset_change,
            }
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self.store_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
