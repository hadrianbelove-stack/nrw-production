"""Admin panel logging configuration."""

import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Any


def setup_logger(name: str, log_file: str = 'logs/admin.log', level: int = logging.INFO) -> logging.Logger:
    """
    Configure logging with file rotation and console output.

    Args:
        name (str): Logger name (e.g., 'admin', 'data_generator')
        log_file (str): Path to log file (default: 'logs/admin.log')
        level (int): Logging level (default: logging.INFO)

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    # Get or create logger
    _logger = logging.getLogger(name)

    # Prevent duplicate handlers
    if not _logger.handlers:
        _logger.setLevel(level)

        # Create formatter with user context placeholder
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(user)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler with rotation (10MB, 5 backups)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        _logger.addHandler(file_handler)

        # Console handler for development visibility
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        _logger.addHandler(console_handler)

    return _logger


# Custom LogRecord factory to inject user context
old_factory = logging.getLogRecordFactory()

def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    """Custom LogRecord factory that injects user context.

    Wraps the default LogRecord factory to add 'user' attribute
    with the current authenticated user from Flask-HTTPAuth.

    Args:
        *args: Positional arguments passed to default factory
        **kwargs: Keyword arguments passed to default factory

    Returns:
        LogRecord with added 'user' attribute
    """
    record = old_factory(*args, **kwargs)
    # Inject user context
    record.user = 'system'
    return record

logging.setLogRecordFactory(record_factory)

# Module-level logger instance — import this from other admin modules
logger = setup_logger('admin', 'logs/admin.log', logging.INFO)
