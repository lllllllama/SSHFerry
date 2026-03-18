"""In-memory log buffering for REST and websocket consumers."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
from threading import Lock

from src.shared.logging_ import SanitizingFormatter


DEFAULT_LOG_BUFFER_LIMIT = 500
DEFAULT_LOG_LEVEL = logging.INFO


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Single sanitized log entry exposed to the frontend."""

    sequence: int
    timestamp: float
    level: str
    logger: str
    message: str
    rendered: str


@dataclass(frozen=True, slots=True)
class LogSnapshot:
    """Snapshot of the current in-memory log buffer."""

    items: list[LogEntry]
    total: int
    sequence: int


class InMemoryLogHandler(logging.Handler):
    """Logging handler that stores recent entries for the frontend."""

    def __init__(self, service: 'LogService'):
        super().__init__(level=DEFAULT_LOG_LEVEL)
        self._service = service
        self.setFormatter(
            SanitizingFormatter(
                '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = SanitizingFormatter._sanitize_text(record.getMessage())
            rendered = self.format(record)
            self._service.append_entry(
                timestamp=float(record.created),
                level=record.levelname.upper(),
                logger=record.name,
                message=message,
                rendered=rendered,
            )
        except Exception:
            self.handleError(record)


class LogService:
    """Thread-safe ring buffer for backend log lines."""

    def __init__(self, max_entries: int = DEFAULT_LOG_BUFFER_LIMIT):
        self._entries: deque[LogEntry] = deque(maxlen=max_entries)
        self._sequence = 0
        self._lock = Lock()
        self._attached_loggers: dict[str, logging.Logger] = {}
        self.handler = InMemoryLogHandler(self)

    def attach_logger(self, logger: logging.Logger, level: int = DEFAULT_LOG_LEVEL) -> None:
        """Attach the in-memory handler to a logger once."""
        with self._lock:
            if logger.name in self._attached_loggers:
                return
            if logger.level == logging.NOTSET or logger.level > level:
                logger.setLevel(level)
            logger.addHandler(self.handler)
            self._attached_loggers[logger.name] = logger

    def append_entry(self, *, timestamp: float, level: str, logger: str, message: str, rendered: str) -> None:
        """Append a new entry and advance the snapshot sequence."""
        with self._lock:
            self._sequence += 1
            self._entries.append(
                LogEntry(
                    sequence=self._sequence,
                    timestamp=timestamp,
                    level=level,
                    logger=logger,
                    message=message,
                    rendered=rendered,
                )
            )

    def snapshot(self, *, limit: int | None = None) -> LogSnapshot:
        """Return the current entries in chronological order."""
        with self._lock:
            items = list(self._entries)
            if limit is not None and limit > 0 and len(items) > limit:
                items = items[-limit:]
            return LogSnapshot(items=items, total=len(self._entries), sequence=self._sequence)

    def clear(self) -> None:
        """Clear buffered entries and advance the snapshot sequence."""
        with self._lock:
            self._entries.clear()
            self._sequence += 1

    def close(self) -> None:
        """Detach the handler from every logger that was wired into the buffer."""
        with self._lock:
            for logger in self._attached_loggers.values():
                logger.removeHandler(self.handler)
            self._attached_loggers.clear()
        self.handler.close()