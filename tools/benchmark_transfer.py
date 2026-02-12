"""Simple transfer benchmark for SSHFerry engines.

Usage examples:
  python tools/benchmark_transfer.py --site my-server --size-mb 512 --iterations 2
  python tools/benchmark_transfer.py --site my-server --modes sftp,parallel:high
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# Ensure project root is on path for "python tools/benchmark_transfer.py".
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engines.parallel_sftp_engine import ParallelSftpEngine
from src.engines.sftp_engine import SftpEngine
from src.services.site_store import SiteStore
from src.shared.models import SiteConfig
from src.shared.paths import join_remote_path


@dataclass
class BenchResult:
    mode: str
    direction: str
    mbps: float
    seconds: float


def _fmt_mib(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MiB"


def _make_progress_callback(
    mode: str,
    direction: str,
    run_idx: int,
    total_runs: int,
    interval_seconds: float = 1.0,
) -> Callable[[int, int], None]:
    last_print = 0.0
    last_bytes = 0

    def _cb(done: int, total: int) -> None:
        nonlocal last_print, last_bytes
        now = time.perf_counter()
        if now - last_print < interval_seconds and done < total:
            return
        dt = max(1e-6, now - last_print) if last_print else 0.0
        delta = max(0, done - last_bytes) if last_print else 0
        inst_speed = (delta / (1024 * 1024)) / dt if dt > 0 else 0.0
        pct = (done * 100.0 / total) if total else 0.0
        print(
            f"[{mode}][{direction}] run {run_idx}/{total_runs} "
            f"{pct:6.2f}% ({_fmt_mib(done)}/{_fmt_mib(total)}) "
            f"inst {inst_speed:.2f} MiB/s"
        )
        last_print = now
        last_bytes = done

    return _cb


def _parse_modes(raw: str) -> list[str]:
    values = [v.strip() for v in raw.split(",") if v.strip()]
    return values or ["sftp", "parallel:high"]


def _load_site(site_name: str) -> SiteConfig:
    sites = SiteStore().load()
    for site in sites:
        if site.name == site_name:
            return site
    raise ValueError(f"Site '{site_name}' not found in SiteStore")


def _ensure_auth(site: SiteConfig) -> None:
    if site.auth_method == "password" and not site.password:
        site.password = getpass.getpass(
            f"Password for {site.username}@{site.host}:{site.port}: "
        )


def _create_local_blob(path: Path, size_bytes: int) -> None:
    chunk = os.urandom(1024 * 1024)
    written = 0
    with open(path, "wb") as f:
        while written < size_bytes:
            n = min(len(chunk), size_bytes - written)
            f.write(chunk[:n])
            written += n


def _run_once(
    site: SiteConfig,
    mode: str,
    direction: str,
    local_src: Path,
    local_dst: Path,
    remote_path: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> BenchResult:
    started = time.perf_counter()
    size_bytes = local_src.stat().st_size

    if mode == "sftp":
        with SftpEngine(site) as engine:
            if direction == "upload":
                engine.upload_file(str(local_src), remote_path, callback=progress_cb)
            else:
                engine.download_file(remote_path, str(local_dst), callback=progress_cb)
    else:
        # mode format: parallel:<preset>
        parts = mode.split(":", 1)
        preset = parts[1] if len(parts) == 2 else "high"
        engine = ParallelSftpEngine(site, preset_name=preset)
        if direction == "upload":
            engine.upload_file(str(local_src), remote_path, callback=progress_cb)
        else:
            engine.download_file(remote_path, str(local_dst), callback=progress_cb)

    elapsed = max(0.001, time.perf_counter() - started)
    mbps = (size_bytes / (1024 * 1024)) / elapsed
    return BenchResult(mode=mode, direction=direction, mbps=mbps, seconds=elapsed)


def _cleanup_remote(site: SiteConfig, remote_dir: str) -> None:
    try:
        with SftpEngine(site) as engine:
            try:
                engine.remove_dir_recursive(remote_dir)
            except Exception:
                pass
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark SSHFerry transfer modes.")
    parser.add_argument("--site", required=True, help="Site name from SiteStore")
    parser.add_argument("--size-mb", type=int, default=256, help="Benchmark file size in MB")
    parser.add_argument("--iterations", type=int, default=2, help="Iterations per mode/direction")
    parser.add_argument(
        "--modes",
        default="sftp,parallel:high,parallel:medium",
        help="Comma-separated modes: sftp or parallel:<preset>",
    )
    parser.add_argument(
        "--direction",
        choices=["upload", "download", "both"],
        default="both",
        help="Transfer direction",
    )
    parser.add_argument(
        "--progress-interval",
        type=float,
        default=1.0,
        help="Progress print interval in seconds (default: 1.0)",
    )
    args = parser.parse_args()

    site = _load_site(args.site)
    _ensure_auth(site)
    modes = _parse_modes(args.modes)
    size_bytes = max(1, args.size_mb) * 1024 * 1024
    run_id = int(time.time())
    remote_dir = join_remote_path(site.remote_root or "/", f".sshferry-bench-{run_id}")
    remote_file = join_remote_path(remote_dir, "blob.bin")

    results: list[BenchResult] = []
    with tempfile.TemporaryDirectory(prefix="sshferry-bench-") as td:
        td_path = Path(td)
        local_src = td_path / "source.bin"
        local_dst = td_path / "downloaded.bin"
        print(f"Preparing local file: {local_src} ({args.size_mb} MB)")
        _create_local_blob(local_src, size_bytes)

        # Ensure remote work dir exists.
        print(f"Creating remote benchmark dir: {remote_dir}")
        with SftpEngine(site) as init_engine:
            try:
                init_engine.mkdir(remote_dir)
            except Exception:
                pass

        directions = ["upload", "download"] if args.direction == "both" else [args.direction]
        for mode in modes:
            for direction in directions:
                samples: list[BenchResult] = []
                for i in range(args.iterations):
                    if local_dst.exists():
                        local_dst.unlink()
                    print(f"Starting run: mode={mode}, direction={direction}, iteration={i + 1}/{args.iterations}")
                    progress_cb = _make_progress_callback(
                        mode=mode,
                        direction=direction,
                        run_idx=i + 1,
                        total_runs=args.iterations,
                        interval_seconds=max(0.1, args.progress_interval),
                    )
                    result = _run_once(
                        site=site,
                        mode=mode,
                        direction=direction,
                        local_src=local_src,
                        local_dst=local_dst,
                        remote_path=remote_file,
                        progress_cb=progress_cb,
                    )
                    samples.append(result)
                    print(
                        f"[{mode}][{direction}] run {i + 1}/{args.iterations}: "
                        f"{result.mbps:.2f} MB/s ({result.seconds:.2f}s)"
                    )
                avg_mbps = sum(s.mbps for s in samples) / len(samples)
                avg_sec = sum(s.seconds for s in samples) / len(samples)
                results.append(
                    BenchResult(mode=mode, direction=direction, mbps=avg_mbps, seconds=avg_sec)
                )

    _cleanup_remote(site, remote_dir)

    print("\n=== Average Results ===")
    print("Mode\tDirection\tMB/s\tSeconds")
    for r in sorted(results, key=lambda x: (x.direction, -x.mbps)):
        print(f"{r.mode}\t{r.direction}\t{r.mbps:.2f}\t{r.seconds:.2f}")


if __name__ == "__main__":
    main()
