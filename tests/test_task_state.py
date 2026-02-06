"""Tests for task state machine transitions."""
import pytest

from src.core.task_state import (
    TERMINAL_STATES,
    assert_transition,
    is_valid_transition,
)


class TestIsValidTransition:
    def test_pending_to_running(self):
        assert is_valid_transition("pending", "running") is True

    def test_pending_to_canceled(self):
        assert is_valid_transition("pending", "canceled") is True

    def test_pending_to_done_invalid(self):
        assert is_valid_transition("pending", "done") is False

    def test_running_to_done(self):
        assert is_valid_transition("running", "done") is True

    def test_running_to_failed(self):
        assert is_valid_transition("running", "failed") is True

    def test_running_to_paused(self):
        assert is_valid_transition("running", "paused") is True

    def test_running_to_canceled(self):
        assert is_valid_transition("running", "canceled") is True

    def test_paused_to_running(self):
        assert is_valid_transition("paused", "running") is True

    def test_paused_to_canceled(self):
        assert is_valid_transition("paused", "canceled") is True

    def test_paused_to_done_invalid(self):
        assert is_valid_transition("paused", "done") is False

    def test_terminal_states_have_no_outgoing(self):
        for state in TERMINAL_STATES:
            for target in ["pending", "running", "paused", "done", "failed", "canceled"]:
                assert is_valid_transition(state, target) is False

    def test_unknown_state_returns_false(self):
        assert is_valid_transition("unknown", "running") is False


class TestAssertTransition:
    def test_valid_does_not_raise(self):
        assert_transition("pending", "running")  # should not raise

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Illegal task state transition"):
            assert_transition("done", "running")

    def test_invalid_from_failed(self):
        with pytest.raises(ValueError):
            assert_transition("failed", "running")
