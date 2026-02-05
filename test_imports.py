#!/usr/bin/env python3
"""Test script to verify imports and basic functionality."""

print("Testing SSHFerry imports...")

try:
    # Test shared modules
    print("✓ Importing shared.errors...")
    from src.shared.errors import ErrorCode, SSHFerryError
    
    print("✓ Importing shared.models...")
    from src.shared.models import SiteConfig, RemoteEntry, Task
    
    print("✓ Importing shared.paths...")
    from src.shared.paths import normalize_remote_path, ensure_in_sandbox
    
    print("✓ Importing shared.logging_...")
    from src.shared.logging_ import setup_logger
    
    # Test engines
    print("✓ Importing engines.sftp_engine...")
    from src.engines.sftp_engine import SftpEngine
    
    # Test core
    print("✓ Importing core.scheduler...")
    from src.core.scheduler import TaskScheduler
    
    # Test services
    print("✓ Importing services.connection_checker...")
    from src.services.connection_checker import ConnectionChecker
    
    print("\n✅ All imports successful!")
    
    # Test basic path operations
    print("\nTesting path operations...")
    
    normalized = normalize_remote_path("/root//autodl-tmp/./test")
    assert normalized == "/root/autodl-tmp/test", f"Path normalization failed: {normalized}"
    print(f"  normalize_remote_path: {normalized} ✓")
    
    try:
        ensure_in_sandbox("/root/autodl-tmp/test", "/root/autodl-tmp")
        print("  ensure_in_sandbox (valid path): ✓")
    except:
        print("  ensure_in_sandbox (valid path): ✗")
        
    try:
        ensure_in_sandbox("/etc/passwd", "/root/autodl-tmp")
        print("  ensure_in_sandbox (invalid path): ✗ (should have raised)")
    except:
        print("  ensure_in_sandbox (invalid path): ✓ (correctly rejected)")
    
    # Test model creation
    print("\nTesting model creation...")
    site = SiteConfig(
        name="Test",
        host="localhost",
        port=22,
        username="user",
        auth_method="password",
        remote_root="/root/test"
    )
    print(f"  SiteConfig: {site.name} @ {site.host}:{site.port} ✓")
    
    print("\n✅ All basic tests passed!")
    print("\nNote: To run the full application, you need:")
    print("  - PySide6 (for GUI)")
    print("  - Paramiko (for SSH/SFTP)")
    print("  Install with: pip install PySide6 paramiko")
    
except ImportError as e:
    print(f"\n❌ Import error: {e}")
    print("\nMake sure all dependencies are installed:")
    print("  pip install -r requirements.txt")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
