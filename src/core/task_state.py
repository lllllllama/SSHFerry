"""Task state machine – validates and enforces legal state transitions."""

# Legal transitions: current_state -> set of allowed next states
TRANSITIONS: dict[str, set[str]] = {
    "pending":  {"running", "canceled"},
    "running":  {"done", "failed", "paused", "canceled"},
    "paused":   {"running", "canceled"},
    "done":     set(),
    "failed":   set(),
    "canceled": set(),
}

ALL_STATES = set(TRANSITIONS.keys())
TERMINAL_STATES = {"done", "failed", "canceled"}


def is_valid_transition(current: str, target: str) -> bool:
    """Return True if *current -> target* is a legal transition."""
    return target in TRANSITIONS.get(current, set())


def assert_transition(current: str, target: str) -> None:
    """Raise ValueError if the transition is illegal."""
    if not is_valid_transition(current, target):
        raise ValueError(
            f"Illegal task state transition: {current!r} -> {target!r}. "
            f"Allowed from {current!r}: {TRANSITIONS.get(current, set())}"
        )
