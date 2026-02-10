"""Tests for metrics service."""
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from src.services.metrics import MetricsCollector, TransferRecord


@pytest.fixture
def temp_metrics_file():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


def test_record_and_get_stats(temp_metrics_file):
    collector = MetricsCollector(store_path=temp_metrics_file)
    
    # Record some transfers
    collector.record(TransferRecord(
        preset="low",
        bytes_transferred=1024*1024,
        duration_seconds=1.0,  # 1 MB/s
        success=True,
        timestamp=time.time()
    ))
    
    collector.record(TransferRecord(
        preset="low",
        bytes_transferred=2*1024*1024,
        duration_seconds=1.0,  # 2 MB/s
        success=True,
        timestamp=time.time()
    ))
    
    stats = collector.get_stats()
    low_stats = stats["low"]
    
    assert low_stats.total_transfers == 2
    assert low_stats.successful_transfers == 2
    assert low_stats.total_bytes == 3*1024*1024
    assert low_stats.avg_speed_mbps == 1.5
    assert low_stats.success_rate == 100.0


def test_recommended_preset_downgrade(temp_metrics_file):
    collector = MetricsCollector(store_path=temp_metrics_file)
    collector.current_preset = "medium"
    
    # Simulate failures
    now = time.time()
    for _ in range(5):
        collector.record(TransferRecord(
            preset="medium",
            bytes_transferred=0,
            duration_seconds=1.0,
            success=False,
            timestamp=now
        ))
        
    # Should recommend downgrade
    recommendation = collector.get_recommended_preset()
    assert recommendation == "low"
    assert collector.current_preset == "low"


def test_recommended_preset_upgrade(temp_metrics_file):
    collector = MetricsCollector(store_path=temp_metrics_file)
    collector.current_preset = "low"
    
    # Simulate success
    now = time.time()
    for _ in range(5):
        collector.record(TransferRecord(
            preset="low",
            bytes_transferred=1024*1024,
            duration_seconds=1.0,
            success=True,
            timestamp=now
        ))
        
    # Should recommend upgrade
    recommendation = collector.get_recommended_preset()
    assert recommendation == "medium"
    assert collector.current_preset == "medium"


def test_cooldown(temp_metrics_file):
    collector = MetricsCollector(store_path=temp_metrics_file)
    collector.current_preset = "medium"
    collector.last_preset_change = time.time()  # Changed just now
    
    # Simulate failures
    for _ in range(5):
        collector.record(TransferRecord(
            preset="medium",
            bytes_transferred=0,
            duration_seconds=1.0,
            success=False,
            timestamp=time.time()
        ))
        
    # Should NOT recommend downgrade due to cooldown
    recommendation = collector.get_recommended_preset()
    assert recommendation == "medium"
