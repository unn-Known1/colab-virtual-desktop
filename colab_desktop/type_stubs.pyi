"""
Type stubs for Colab Virtual Desktop

This module provides type hints and comprehensive documentation
for the refactored codebase, enhancing IDE support and code clarity.
"""

from typing import (
    Any, Dict, List, Optional, Tuple, Union, Callable,
    Sequence, Iterable, Iterator, TypeVar, Generic,
    Protocol, runtime_checkable, Literal, TypedDict
)
from dataclasses import dataclass
from pathlib import Path
import sys
import time


# ==================== Base Types ====================

T = TypeVar('T')


@runtime_checkable
class SupportsRun(Protocol):
    """Protocol for objects that can run commands"""
    def __call__(self, cmd: str, **kwargs: Any) -> Tuple[int, str, str]: ...


@dataclass
class ComponentInfo:
    """
    Standardized information about a desktop component

    Attributes:
        name: Component identifier (e.g., 'xvfb', 'vnc')
        status: Current status ('stopped', 'starting', 'running', 'failed')
        pid: Process ID if running
        port: Port number if applicable
        url: URL if applicable
        dependencies: List of component names this depends on
        metadata: Additional component-specific data
        error: Error message if status is 'failed'
        last_check: Timestamp of last status check
    """
    name: str
    status: str = "stopped"
    pid: Optional[int] = None
    port: Optional[int] = None
    url: Optional[str] = None
    dependencies: List[str] = None
    metadata: Dict[str, Any] = None
    error: Optional[str] = None
    last_check: float = 0.0

    def __post_init__(self) -> None:
        if self.dependencies is None:
            self.dependencies = []
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dictionary"""
        return {
            'name': self.name,
            'status': self.status,
            'pid': self.pid,
            'port': self.port,
            'url': self.url,
            'dependencies': self.dependencies.copy(),
            'metadata': self.metadata.copy(),
            'error': self.error,
            'last_check': self.last_check
        }


class HealthStatus:
    """Service health status enumeration"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


# ==================== Logging Types ====================

class LogLevel:
    """Log level constants"""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class ColabLogger:
    """
    Enhanced logger with structured output, metrics, and audit trail.

    Features:
    - Console and file output with rotation
    - JSON structured logging option
    - Colorized console output
    - Performance metrics collection
    - Audit logging for important events
    - Thread-safe operations

    Example:
        logger = ColabLogger(name="desktop", level=LogLevel.INFO)
        logger.info("Desktop started", extra={"url": url})
        logger.audit("desktop_start", details={"user": "colab"})
    """

    def __init__(
        self,
        name: str = "colab_desktop",
        level: Union[int, LogLevel] = LogLevel.INFO,
        log_file: Optional[str] = None,
        log_dir: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        json_format: bool = False,
        console_output: bool = True,
        include_metrics: bool = True,
        audit_log: bool = True
    ) -> None:
        ...

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message"""
        ...

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log info message"""
        ...

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message"""
        ...

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log error message"""
        ...

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log critical message"""
        ...

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log exception with traceback"""
        ...

    def audit(self, action: str, details: Optional[Dict[str, Any]] = None, user: str = "system") -> None:
        """
        Log an audit event for important system actions

        Args:
            action: Action performed (e.g., 'desktop_start', 'desktop_stop')
            details: Additional structured details
            user: User identifier
        """
        ...

    def inc_counter(self, name: str, value: int = 1) -> None:
        """Increment a performance counter"""
        ...

    def time_operation(self, name: str) -> "MetricsContext":
        """Context manager for timing operations"""
        ...

    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        ...

    def set_level(self, level: Union[int, LogLevel]) -> None:
        """Change log level at runtime"""
        ...

    def close(self) -> None:
        """Close all handlers and cleanup"""
        ...


class MetricsContext:
    """Context manager for timing operations"""
    def __enter__(self) -> "MetricsContext": ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool: ...


# ==================== Port Management Types ====================

class PortInfo:
    """
    Information about a network port

    Attributes:
        port: Port number
        service: Service name using this port
        pid: Process ID using the port
        process_name: Name of the process
        user: User running the process
        in_use: Whether port is currently in use
        can_bind: Whether port can be bound
        locked_by: Reservation owner
    """
    port: int
    service: str
    pid: Optional[int]
    process_name: Optional[str]
    user: Optional[str]
    in_use: bool
    can_bind: bool
    locked_by: Optional[str]


class PortManager:
    """
    Intelligent port allocation and conflict resolution

    Features:
    - Automatic port reservation with persistence
    - Conflict detection and resolution
    - Force-kill stuck processes
    - Service-specific port ranges
    - Thread-safe operations

    Example:
        with PortManager() as pm:
            port = pm.reserve_port('vnc', preferred_port=5901)
            print(f"Reserved VNC on port {port.port}")
    """

    # Service port ranges
    SERVICE_PORT_RANGES: Dict[str, Tuple[int, int]] = {
        'vnc': (5900, 5910),
        'novnc': (6080, 6090),
        'ssh': (2200, 2300),
        'jupyter': (8888, 8898),
    }

    def __init__(
        self,
        runner: Optional[SupportsRun] = None,
        logger: Optional[Callable] = None,
        reservation_file: Optional[Union[str, Path]] = None
    ) -> None:
        ...

    def reserve_port(
        self,
        service: str,
        preferred_port: Optional[int] = None,
        port_range: Optional[Tuple[int, int]] = None,
        force: bool = False
    ) -> PortInfo:
        """
        Reserve a port for a service

        Args:
            service: Service name (e.g., 'vnc', 'novnc')
            preferred_port: Preferred port number
            port_range: Custom range to search
            force: Force reservation even if port in use (dangerous)

        Returns:
            PortInfo with reserved port

        Raises:
            RuntimeError: If no available port found
        """
        ...

    def release_port(self, port: int) -> None:
        """Release a specific port reservation"""
        ...

    def release_service(self, service: str) -> None:
        """Release all ports for a service"""
        ...

    def get_reserved_port(self, service: str) -> Optional[int]:
        """Get the port reserved for a service"""
        ...

    def force_release_port(self, port: int, kill_process: bool = False) -> None:
        """
        Force release a port, optionally killing the process

        Args:
            port: Port to release
            kill_process: Kill the process using it (requires privileges)
        """
        ...

    def cleanup_all(self, kill_processes: bool = False) -> None:
        """Clean up all reservations"""
        ...

    def get_status(self) -> Dict[str, Any]:
        """Get port manager status"""
        ...

    def __enter__(self) -> "PortManager":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup_all(kill_processes=False)


# ==================== Health Check Types ====================

class HealthCheckResult:
    """Result of a single health check"""
    service_name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    last_check: float
    response_time_ms: Optional[float]
    pid: Optional[int]
    port: Optional[int]
    url: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        ...


class ServiceHealthChecker:
    """
    Comprehensive health checking for desktop services

    Performs multi-layer checks:
    - Process liveness
    - Port availability
    - HTTP endpoints (for noVNC)
    - X11 responsiveness
    - Dependency verification

    Example:
        checker = create_health_checker(desktop)
        checker.run_all_checks()
        print(checker.get_health_status_text())
    """

    def __init__(
        self,
        runner: Optional[SupportsRun] = None,
        logger: Optional[Callable] = None
    ) -> None:
        ...

    def run_all_checks(self, include_deps: bool = True) -> Dict[str, HealthCheckResult]:
        """
        Run health checks for all services

        Args:
            include_deps: Check dependencies as well

        Returns:
            Dictionary mapping service name to HealthCheckResult
        """
        ...

    def get_overall_health(self) -> HealthStatus:
        """Get overall health status"""
        ...

    def get_unhealthy_services(self) -> List[HealthCheckResult]:
        """Get list of unhealthy services"""
        ...

    def get_service_info(self, service_name: str) -> Optional[HealthCheckResult]:
        """Get health info for specific service"""
        ...

    def wait_for_healthy(
        self,
        timeout: int = 60,
        poll_interval: float = 2.0,
        required_services: Optional[List[str]] = None
    ) -> bool:
        """
        Wait until services become healthy

        Args:
            timeout: Maximum wait time in seconds
            poll_interval: Check interval
            required_services: Services that must be healthy (None for all required)

        Returns:
            True if healthy within timeout
        """
        ...

    def start_monitoring(self, interval: float = 10.0) -> None:
        """Start background health monitoring"""
        ...

    def stop_monitoring(self) -> None:
        """Stop background health monitoring"""
        ...

    def get_health_report(self, include_history: bool = False) -> Dict[str, Any]:
        """Generate comprehensive health report"""
        ...

    def get_resource_usage(self) -> Dict[str, Any]:
        """Get resource usage for desktop processes"""
        ...

    def get_health_status_text(self) -> str:
        """Get human-readable status"""
        ...


# ==================== Config Validation Types ====================

class ValidationSeverity:
    """Validation severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationResult:
    """Result of a single validation check"""
    field: str
    value: Any
    valid: bool
    message: str
    severity: Union[ValidationSeverity, str]
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        ...


@dataclass
class ValidationSummary:
    """Summary of all validation results"""
    all_valid: bool
    errors: List[ValidationResult] = None
    warnings: List[ValidationResult] = None
    infos: List[ValidationResult] = None
    corrected: List[Dict[str, Any]] = None

    def add_result(self, result: ValidationResult) -> None:
        """Add a validation result"""
        ...

    def has_critical_errors(self) -> bool:
        """Check if there are critical errors"""
        ...

    def get_formatted_report(self) -> str:
        """Get human-readable report"""
        ...


class ConfigValidator:
    """
    Comprehensive configuration validator

    Validates all configuration parameters with:
    - Type checking and conversion
    - Range and format validation
    - Allowed values checking
    - Cross-field dependencies
    - Environment compatibility

    Example:
        validator = ConfigValidator(config)
        summary = validator.validate_all(auto_correct=True)
        if not summary.all_valid:
            print(summary.get_formatted_report())
        corrected_config = validator.get_corrected_config()
    """

    SCHEMAS: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        config: Dict[str, Any],
        env_overrides: bool = True,
        strict: bool = False,
        runner: Optional[SupportsRun] = None
    ) -> None:
        ...

    def validate_all(self, auto_correct: bool = True) -> ValidationSummary:
        """
        Validate all configuration fields

        Args:
            auto_correct: Attempt automatic corrections

        Returns:
            ValidationSummary with all results
        """
        ...

    def get_corrected_config(self) -> Dict[str, Any]:
        """Get configuration with corrections applied"""
        ...

    def is_valid(self, treat_warnings_as_errors: bool = False) -> bool:
        """Check if configuration is valid"""
        ...


class ConfigBuilder:
    """
    Builder pattern for creating validated configurations

    Provides fluent interface for building and validating configs.

    Example:
        config = (ConfigBuilder()
                  .with_ngrok_token("...")
                  .with_geometry("1920x1080")
                  .validate()
                  .build())
    """

    def __init__(self) -> None:
        ...

    def with_ngrok_token(self, token: str) -> "ConfigBuilder":
        """Set ngrok auth token"""
        ...

    def with_vnc_password(self, password: str) -> "ConfigBuilder":
        """Set VNC password"""
        ...

    def with_display(self, display: str) -> "ConfigBuilder":
        """Set X display"""
        ...

    def with_geometry(self, geometry: str) -> "ConfigBuilder":
        """Set screen geometry (e.g., '1280x720')"""
        ...

    def with_depth(self, depth: int) -> "ConfigBuilder":
        """Set color depth (8, 16, 24, or 32)"""
        ...

    def with_vnc_port(self, port: int) -> "ConfigBuilder":
        """Set VNC port"""
        ...

    def with_novnc_port(self, port: int) -> "ConfigBuilder":
        """Set noVNC port"""
        ...

    def with_auto_open(self, auto_open: bool = True) -> "ConfigBuilder":
        """Set auto-open browser"""
        ...

    def validate(self, auto_correct: bool = True, strict: bool = False) -> "ConfigBuilder":
        """Validate current configuration"""
        ...

    def is_valid(self) -> bool:
        """Check if valid"""
        ...

    def build(self, raise_on_error: bool = True) -> Dict[str, Any]:
        """
        Build final configuration

        Args:
            raise_on_error: Raise ValueError if invalid

        Returns:
            Validated configuration dictionary
        """
        ...


# ==================== Main Desktop Class Types ====================

class DesktopComponent(Protocol):
    """Protocol for desktop components"""
    def initialize(self) -> bool: ...
    def start(self) -> bool: ...
    def stop(self) -> bool: ...
    def is_running(self) -> bool: ...
    def get_status(self) -> Dict[str, Any]: ...


class LifecycleManager:
    """
    Manages lifecycle of multiple components with dependency resolution

    Handles initialization and startup in dependency order,
    and shutdown in reverse order.

    Example:
        lm = LifecycleManager()
        lm.register('xvfb', xvfb_component)
        lm.register('vnc', vnc_component, dependencies=['xvfb'])
        lm.initialize_all()
        lm.start_all()
    """

    def __init__(self, logger: Optional[Callable] = None) -> None:
        ...

    def register(
        self,
        name: str,
        component: DesktopComponent,
        dependencies: Optional[List[str]] = None
    ) -> None:
        """Register a component"""
        ...

    def initialize_all(self, skip_existing: bool = True) -> bool:
        """Initialize all components in dependency order"""
        ...

    def start_all(self) -> bool:
        """Start all components in dependency order"""
        ...

    def stop_all(self) -> bool:
        """Stop all components in reverse dependency order"""
        ...

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all components"""
        ...

    def get_running_components(self) -> List[str]:
        """Get list of running component names"""
        ...

    def is_healthy(self) -> bool:
        """Check if all components are healthy"""
        ...


class ColabDesktopImproved:
    """
    Improved virtual desktop manager with all enhancements

    Integrates modular architecture, comprehensive logging,
    health monitoring, port management, and validation.

    Example:
        desktop = ColabDesktopImproved(ngrok_auth_token="...")
        if desktop.setup():
            if desktop.start():
                print(f"URL: {desktop.get_url()}")
                # Use desktop...
                desktop.stop()
    """

    def __init__(
        self,
        ngrok_auth_token: Optional[str] = None,
        vnc_password: str = "colab123",
        display: str = ":1",
        geometry: str = "1280x720",
        depth: int = 24,
        vnc_port: Optional[int] = None,
        novnc_port: Optional[int] = None,
        ngrok_region: str = "us",
        auto_open: bool = False,
        install_deps: bool = True,
        logger: Optional[ColabLogger] = None,
        port_manager: Optional[PortManager] = None,
        health_checker: Optional[ServiceHealthChecker] = None
    ) -> None:
        ...

    def validate_environment(self) -> List[str]:
        """Validate environment and configuration"""
        ...

    def install_dependencies(self) -> bool:
        """Install system and Python dependencies"""
        ...

    def setup_vnc_password(self) -> bool:
        """Setup VNC server password"""
        ...

    def setup(self) -> bool:
        """Setup phase: prepare environment"""
        ...

    def start(self) -> bool:
        """Start all services"""
        ...

    def stop(self) -> None:
        """Stop all services"""
        ...

    def restart(self) -> bool:
        """Restart all services"""
        ...

    def get_url(self) -> Optional[str]:
        """Get public desktop URL"""
        ...

    def launch_app(self, command: str, wait: bool = False) -> None:
        """Launch a GUI application"""
        ...

    def take_screenshot(self, output_path: str = "/content/desktop_screenshot.png") -> str:
        """Take a screenshot of the desktop"""
        ...

    def get_health_status_text(self) -> str:
        """Get formatted health status"""
        ...

    def __enter__(self) -> "ColabDesktopImproved":
        ...

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ...


def quick_start(ngrok_token: str, **kwargs) -> ColabDesktopImproved:
    """One-line startup function"""
    ...


# ==================== Helper Functions ====================

def is_colab() -> bool:
    """Check if running in Google Colab"""
    ...


def get_default_log_dir() -> Path:
    """Get appropriate log directory for environment"""
    ...


def ensure_dir(path: Union[str, Path]) -> bool:
    """Ensure directory exists, create if needed"""
    ...


def create_health_checker(desktop: ColabDesktopImproved) -> ServiceHealthChecker:
    """Factory to create health checker for a desktop instance"""
    ...


def validate_config(
    config: Dict[str, Any],
    auto_correct: bool = True,
    strict: bool = False
) -> Tuple[Dict[str, Any], ValidationSummary]:
    """Validate configuration dictionary"""
    ...