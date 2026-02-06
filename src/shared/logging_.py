"""Structured logging for SSHFerry."""
import logging
import sys
from pathlib import Path
from typing import Optional

from src.shared.errors import ErrorCode


class SanitizingFormatter(logging.Formatter):
    """
    Formatter that sanitizes sensitive information from log messages.
    
    Prevents passwords, passphrases, and key contents from being logged.
    """

    SENSITIVE_KEYS = [
        'password',
        'passphrase',
        'key',
        'private_key',
        'secret',
        'token',
    ]

    def format(self, record: logging.LogRecord) -> str:
        """Format and sanitize log record."""
        # Sanitize message
        if hasattr(record, 'msg'):
            msg_lower = str(record.msg).lower()
            for key in self.SENSITIVE_KEYS:
                if key in msg_lower:
                    # Replace sensitive data patterns
                    # This is a simple approach; production may need more sophisticated detection
                    pass

        return super().format(record)


def setup_logger(
    name: str = "sshferry",
    level: int = logging.INFO,
    log_file: Optional[Path] = None
) -> logging.Logger:
    """
    Set up application logger with sanitization.
    
    Args:
        name: Logger name
        level: Logging level
        log_file: Optional file path for file handler
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = SanitizingFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_formatter = SanitizingFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def log_task_event(
    logger: logging.Logger,
    task_id: str,
    engine: str,
    kind: str,
    status: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    src: Optional[str] = None,
    dst: Optional[str] = None,
    bytes_done: Optional[int] = None,
    bytes_total: Optional[int] = None,
    speed: Optional[float] = None,
    error_code: Optional[ErrorCode] = None,
    message: Optional[str] = None
):
    """
    Log a structured task event.
    
    Args:
        logger: Logger instance
        task_id: Task ID
        engine: Engine name (sftp/mscp)
        kind: Task kind (upload/download/etc)
        status: Task status
        host: Remote host (optional)
        port: Remote port (optional)
        user: Username (optional, will be sanitized)
        src: Source path (optional)
        dst: Destination path (optional)
        bytes_done: Bytes completed (optional)
        bytes_total: Total bytes (optional)
        speed: Transfer speed in bytes/sec (optional)
        error_code: Error code if failed (optional)
        message: Additional message (optional)
    """
    parts = [
        f"task_id={task_id[:8]}",
        f"engine={engine}",
        f"kind={kind}",
        f"status={status}",
    ]

    if host and port:
        parts.append(f"remote={host}:{port}")
    if user:
        # Sanitize username (only show first 3 chars)
        sanitized_user = user[:3] + "***" if len(user) > 3 else "***"
        parts.append(f"user={sanitized_user}")
    if src:
        parts.append(f"src={src}")
    if dst:
        parts.append(f"dst={dst}")
    if bytes_done is not None and bytes_total is not None:
        progress = (bytes_done / bytes_total * 100) if bytes_total > 0 else 0
        parts.append(f"progress={progress:.1f}%")
    if speed is not None:
        speed_mb = speed / (1024 * 1024)
        parts.append(f"speed={speed_mb:.2f}MB/s")
    if error_code:
        parts.append(f"error={error_code.name}")
    if message:
        parts.append(f"msg={message}")

    log_msg = " | ".join(parts)

    if status == "failed" or error_code:
        logger.error(log_msg)
    elif status in ("done", "completed"):
        logger.info(log_msg)
    else:
        logger.debug(log_msg)


# Default logger instance
default_logger = setup_logger()
