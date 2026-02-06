"""Tests for path utilities and sandbox validation."""
import pytest

from src.shared.errors import ValidationError
from src.shared.paths import (
    ensure_in_sandbox,
    get_remote_basename,
    get_remote_parent,
    join_remote_path,
    normalize_remote_path,
)


class TestNormalizeRemotePath:
    """Tests for normalize_remote_path function."""

    def test_absolute_path(self):
        """Test normalization of absolute paths."""
        assert normalize_remote_path("/root/autodl-tmp") == "/root/autodl-tmp"
        assert normalize_remote_path("/root/autodl-tmp/") == "/root/autodl-tmp"

    def test_relative_path_converted(self):
        """Test that relative paths are converted to absolute."""
        assert normalize_remote_path("root/autodl-tmp") == "/root/autodl-tmp"
        assert normalize_remote_path("test") == "/test"

    def test_dot_components(self):
        """Test resolution of . and .. components."""
        assert normalize_remote_path("/root/./autodl-tmp") == "/root/autodl-tmp"
        assert normalize_remote_path("/root/test/../autodl-tmp") == "/root/autodl-tmp"

    def test_double_slashes(self):
        """Test removal of duplicate slashes."""
        assert normalize_remote_path("/root//autodl-tmp") == "/root/autodl-tmp"
        assert normalize_remote_path("///root///autodl-tmp///") == "/root/autodl-tmp"

    def test_complex_path(self):
        """Test complex path with multiple issues."""
        assert normalize_remote_path("//root/./test/../autodl-tmp//") == "/root/autodl-tmp"


class TestEnsureInSandbox:
    """Tests for ensure_in_sandbox function."""

    def test_exact_root_allowed(self):
        """Test that exact root path is allowed."""
        ensure_in_sandbox("/root/autodl-tmp", "/root/autodl-tmp")  # Should not raise

    def test_path_inside_sandbox_allowed(self):
        """Test that paths inside sandbox are allowed."""
        ensure_in_sandbox("/root/autodl-tmp/test", "/root/autodl-tmp")  # Should not raise
        ensure_in_sandbox("/root/autodl-tmp/a/b/c", "/root/autodl-tmp")  # Should not raise

    def test_path_outside_sandbox_rejected(self):
        """Test that paths outside sandbox are rejected."""
        with pytest.raises(ValidationError):
            ensure_in_sandbox("/root/other", "/root/autodl-tmp")

        with pytest.raises(ValidationError):
            ensure_in_sandbox("/etc/passwd", "/root/autodl-tmp")

        with pytest.raises(ValidationError):
            ensure_in_sandbox("/", "/root/autodl-tmp")

    def test_dotdot_escape_rejected(self):
        """Test that .. escape attempts are rejected."""
        with pytest.raises(ValidationError):
            ensure_in_sandbox("/root/autodl-tmp/../other", "/root/autodl-tmp")

        with pytest.raises(ValidationError):
            ensure_in_sandbox("/root/autodl-tmp/../../etc", "/root/autodl-tmp")

    def test_prefix_confusion_prevented(self):
        """Test that similar prefixes don't cause confusion."""
        # /root/autodl-tmp-other should NOT be allowed when sandbox is /root/autodl-tmp
        with pytest.raises(ValidationError):
            ensure_in_sandbox("/root/autodl-tmp-other", "/root/autodl-tmp")

    def test_trailing_slash_handled(self):
        """Test that trailing slashes are handled correctly."""
        ensure_in_sandbox("/root/autodl-tmp/test", "/root/autodl-tmp/")  # Should not raise
        ensure_in_sandbox("/root/autodl-tmp/test/", "/root/autodl-tmp")  # Should not raise


class TestJoinRemotePath:
    """Tests for join_remote_path function."""

    def test_simple_join(self):
        """Test simple path joining."""
        assert join_remote_path("/root", "autodl-tmp") == "/root/autodl-tmp"
        assert join_remote_path("/root", "autodl-tmp", "test") == "/root/autodl-tmp/test"

    def test_absolute_component_replaces(self):
        """Test that absolute components replace previous parts."""
        assert join_remote_path("/root", "/autodl-tmp") == "/autodl-tmp"


class TestGetRemoteParent:
    """Tests for get_remote_parent function."""

    def test_get_parent(self):
        """Test getting parent directory."""
        assert get_remote_parent("/root/autodl-tmp/test") == "/root/autodl-tmp"
        assert get_remote_parent("/root/autodl-tmp") == "/root"
        assert get_remote_parent("/root") == "/"

    def test_root_has_no_parent(self):
        """Test that root directory has no parent."""
        assert get_remote_parent("/") is None


class TestGetRemoteBasename:
    """Tests for get_remote_basename function."""

    def test_get_basename(self):
        """Test getting basename."""
        assert get_remote_basename("/root/autodl-tmp/test.txt") == "test.txt"
        assert get_remote_basename("/root/autodl-tmp") == "autodl-tmp"
        assert get_remote_basename("/root") == "root"
