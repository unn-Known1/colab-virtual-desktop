"""
Comprehensive Logging System for Colab Virtual Desktop

Provides structured logging with multiple levels, color support,
file rotation, and metrics tracking.
"""

import os
import sys
import time
import json
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Union, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import traceback


class LogLevel(Enum):
    """Log level enumeration"""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class ColabFormatter(logging.Formatter):
    """Custom formatter with colors and structured output"""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'
    }

    def __init__(
        self,
        use_colors: bool = True,
        include_timestamp: bool = True,
        include_level: bool = True,
        include_module: bool = True,
        json_format: bool = False
    ):
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()
        self.include_timestamp = include_timestamp
        self.include_level = include_level
        self.include_module = include_module
        self.json_format = json_format

    def format(self, record: logging.LogRecord) -> str:
        if self.json_format:
            return self._format_json(record)
        else:
            return self._format_console(record)

    def _format_json(self, record: logging.LogRecord) -> str:
        """Format as JSON line"""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Include exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Include extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'message', 'pathname', 'process', 'processName',
                          'relativeCreated', 'stack_info', 'thread', 'threadName',
                          'exc_info', 'exc_text']:
                log_data[key] = value

        return json.dumps(log_data, default=str)

    def _format_console(self, record: logging.LogRecord) -> str:
        """Format for console with colors"""
        parts = []

        # Timestamp
        if self.include_timestamp:
            timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
            parts.append(f"\033[90m[{timestamp}]\033[0m")

        # Level with color
        levelname = record.levelname
        if self.use_colors and levelname in self.COLORS:
            level = f"{self.COLORS[levelname]}{levelname:8}\033[0m"
        else:
            level = levelname
        parts.append(level)

        # Module
        if self.include_module:
            module = f"{record.module}:{record.funcName}"
            parts.append(f"\033[90m[{module}]\033[0m")

        # Message
        msg = record.getMessage()
        parts.append(msg)

        formatted = " ".join(parts)

        # Add exception if present
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            formatted = f"{formatted}\n{exc_text}"

        return formatted


class MetricsCollector:
    """Collect and aggregate metrics"""

    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.timers: Dict[str, List[float]] = {}
        self.gauges: Dict[str, float] = {}
        self._lock = None
        try:
            import threading
            self._lock = threading.Lock()
        except:
            pass

    def increment(self, metric: str, value: int = 1):
        """Increment a counter"""
        self._safe_update('counters', metric, lambda x: x + value, 0)

    def timing(self, metric: str):
        """Context manager for timing operations"""
        return TimingContext(self, metric)

    def gauge(self, metric: str, value: float):
        """Set a gauge value"""
        self._safe_set('gauges', metric, value)

    def get(self, metric: str, metric_type: str = 'counters') -> Any:
        """Get metric value"""
        store = getattr(self, metric_type, {})
        return store.get(metric, 0)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Get all metrics"""
        return {
            'counters': self.counters.copy(),
            'timers': {k: {
                'count': len(v),
                'avg': sum(v) / len(v) if v else 0,
                'min': min(v) if v else 0,
                'max': max(v) if v else 0,
                'total': sum(v)
            } for k, v in self.timers.items()},
            'gauges': self.gauges.copy()
        }

    def reset(self):
        """Reset all metrics"""
        self.counters.clear()
        self.timers.clear()
        self.gauges.clear()

    def _safe_update(self, store_name: str, key: str, updater: Callable, default: Any):
        """Thread-safe update"""
        store = getattr(self, store_name)
        if self._lock:
            with self._lock:
                store[key] = updater(store.get(key, default))
        else:
            store[key] = updater(store.get(key, default))

    def _safe_set(self, store_name: str, key: str, value: Any):
        """Thread-safe set"""
        store = getattr(self, store_name)
        if self._lock:
            with self._lock:
                store[key] = value
        else:
            store[key] = value


class TimingContext:
    """Context manager for timing operations"""

    def __init__(self, collector: MetricsCollector, metric: str):
        self.collector = collector
        self.metric = metric
        self.start_time: Optional[float] = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.time() - self.start_time
            self.collector._safe_update('timers', self.metric, lambda x: x + [duration], [])


class ColabLogger:
    """
    Enhanced logger for Colab Virtual Desktop

    Features:
    - Multiple output handlers (console, file, metrics)
    - Structured logging (JSON option)
    - Colorized output
    - Performance metrics
    - Audit trail
    - Configurable log levels
    - Automatic cleanup
    """

    def __init__(
        self,
        name: str = "colab_desktop",
        level: Union[LogLevel, int] = LogLevel.INFO,
        log_file: Optional[str] = None,
        log_dir: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB
        backup_count: int = 5,
        json_format: bool = False,
        console_output: bool = True,
        include_metrics: bool = True,
        audit_log: bool = True
    ):
        """
        Initialize logger

        Args:
            name: Logger name
            level: Minimum log level
            log_file: Log file path (if None, uses default location)
            log_dir: Log directory (used if log_file is None)
            max_bytes: Maximum log file size before rotation
            backup_count: Number of backup files to keep
            json_format: Use JSON format for logs
            console_output: Enable console output
            include_metrics: Track performance metrics
            audit_log: Enable audit logging
        """
        self.name = name
        self.level = level.value if isinstance(level, LogLevel) else level
        self.json_format = json_format
        self.include_metrics = include_metrics
        self.audit_log = audit_log

        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.level)

        # Remove existing handlers
        self.logger.handlers.clear()

        # Console handler
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_formatter = ColabFormatter(
                use_colors=True,
                json_format=False
            )
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(self.level)
            self.logger.addHandler(console_handler)

        # File handler
        if log_file or log_dir:
            log_path = self._resolve_log_path(log_file, log_dir)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )

            file_formatter = ColabFormatter(
                use_colors=False,
                json_format=json_format
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(self.level)
            self.logger.addHandler(file_handler)

        # Metrics collector
        if include_metrics:
            self.metrics = MetricsCollector()
            self._log_metrics_periodically()
        else:
            self.metrics = None

        # Audit logger (separate file for important events)
        if audit_log:
            audit_path = self._resolve_log_path(
                log_file or "audit",
                log_dir,
                suffix="audit.log"
            )
            audit_handler = logging.handlers.RotatingFileHandler(
                audit_path,
                maxBytes=max_bytes // 10,  # Smaller size for audit
                backupCount=backup_count,
                encoding='utf-8'
            )
            audit_formatter = ColabFormatter(
                use_colors=False,
                json_format=True  # Always JSON for audit
            )
            audit_handler.setFormatter(audit_formatter)
            audit_handler.setLevel(logging.WARNING)  # Only warnings and above
            self.logger.addHandler(audit_handler)

        self.logger.info(f"Logger initialized: {name} (level={logging.getLevelName(self.level)})")

    def _resolve_log_path(
        self,
        log_file: Optional[str],
        log_dir: Optional[str],
        suffix: str = ".log"
    ) -> Path:
        """Resolve log file path"""
        if log_file:
            return Path(log_file).expanduser().resolve()
        else:
            if not log_dir:
                # Default log directory
                if is_colab():
                    log_dir = '/content/logs'
                else:
                    log_dir = Path.home() / '.colab_desktop' / 'logs'
            log_dir = Path(log_dir).expanduser()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.name}_{timestamp}{suffix}"
            return log_dir / filename

    def _log_metrics_periodically(self):
        """Start background thread to periodically log metrics"""
        if not self.include_metrics:
            return

        import threading

        def metrics_worker():
            while True:
                time.sleep(300)  # Every 5 minutes
                try:
                    metrics_data = self.metrics.get_all()
                    if any(metrics_data.values()):
                        self.debug("Performance metrics", extra={'metrics': metrics_data})
                except:
                    pass

        thread = threading.Thread(target=metrics_worker, daemon=True)
        thread.start()

    # Logger methods
    def debug(self, msg: str, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)

    def audit(self, action: str, details: Optional[Dict[str, Any]] = None, user: str = "system"):
        """
        Log an audit event (important system actions)

        Args:
            action: Action performed (e.g., 'desktop_start', 'desktop_stop')
            details: Additional details
            user: User who performed action
        """
        if not self.audit_log:
            return

        audit_data = {
            'audit': True,
            'action': action,
            'user': user,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        }
        self.logger.warning("AUDIT: " + action, extra={'audit_data': audit_data})

    def inc_counter(self, name: str, value: int = 1):
        """Increment a performance counter"""
        if self.metrics:
            self.metrics.increment(name, value)

    def time_operation(self, name: str):
        """Context manager for timing operations"""
        if self.metrics:
            return self.metrics.timing(name)
        else:
            return DummyContextManager()

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        if self.metrics:
            return self.metrics.get_all()
        return {}

    def set_level(self, level: Union[LogLevel, int]):
        """Change log level at runtime"""
        level_val = level.value if isinstance(level, LogLevel) else level
        self.logger.setLevel(level_val)
        for handler in self.logger.handlers:
            handler.setLevel(level_val)

    def add_handler(self, handler: logging.Handler, formatter: Optional[logging.Formatter] = None):
        """Add a custom handler"""
        if formatter:
            handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def close(self):
        """Close all handlers and cleanup"""
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
        self.logger.handlers.clear()


class DummyContextManager:
    """Dummy context manager for when metrics are disabled"""
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


# Convenience functions for global logger
_global_logger: Optional[ColabLogger] = None


def get_logger(name: str = "colab_desktop", **kwargs) -> ColabLogger:
    """Get or create global logger instance"""
    global _global_logger
    if _global_logger is None or _global_logger.name != name:
        _global_logger = ColabLogger(name=name, **kwargs)
    return _global_logger


def configure_logging(**kwargs) -> ColabLogger:
    """Configure and return logger (convenience function)"""
    global _global_logger
    _global_logger = ColabLogger(**kwargs)
    return _global_logger


def set_global_logger(logger: ColabLogger):
    """Set the global logger instance"""
    global _global_logger
    _global_logger = logger


# Helper function to check Colab environment
def is_colab() -> bool:
    """Check if running in Google Colab"""
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        return False


# Default logger configuration for Colab
def get_default_colab_logger() -> ColabLogger:
    """Get logger with Colab-appropriate defaults"""
    if is_colab():
        log_dir = '/content/colab_desktop_logs'
    else:
        log_dir = Path.home() / '.colab_desktop' / 'logs'

    return ColabLogger(
        name="colab_desktop",
        level=LogLevel.INFO,
        log_dir=str(log_dir),
        max_bytes=5 * 1024 * 1024,  # 5 MB
        backup_count=3,
        json_format=False,
        console_output=True,
        include_metrics=True,
        audit_log=True
    )