"""Event bus for decoupled communication between components."""
from PySide6.QtCore import QObject, Signal

from src.shared.models import Task


class EventBus(QObject):
    """
    Central event bus using Qt signals.

    All components subscribe here instead of wiring directly to each other.
    """

    # Task lifecycle
    task_added = Signal(Task)
    task_updated = Signal(Task)
    task_finished = Signal(Task)

    # Connection
    connection_state_changed = Signal(str)  # "connecting" | "connected" | "disconnected" | "failed"

    # Remote panel
    remote_dir_loaded = Signal(str, list)  # path, list[RemoteEntry]
    remote_dir_failed = Signal(str, str)  # path, error_message

    # Log
    log_message = Signal(str)  # plain text log line


# Singleton instance
event_bus = EventBus()
