"""
Colab Virtual Desktop - Turn Google Colab into a remote desktop with VNC access

A complete solution for running GUI applications in Google Colab and accessing them
via browser using VNC + noVNC + ngrok tunneling.

This is the IMPROVED version with enhanced error handling, health monitoring,
port management, and validation.

Quick usage:
    from colab_desktop import start_virtual_desktop

    desktop = start_virtual_desktop("YOUR_NGROK_TOKEN")

    # Open desktop.get_url() in browser
    # Run GUI apps...

    desktop.stop()

Advanced usage:
    from colab_desktop import ColabDesktopImproved

    desktop = ColabDesktopImproved(geometry="1280x720")
    desktop.setup()  # Install dependencies and prepare
    desktop.start()  # Start all services
    print(desktop.get_url())
    desktop.open_browser()

    # When done
    desktop.stop()
"""

# Re-export main classes and functions
from .core_refactored import (
    ColabDesktopImproved,
    quick_start as quick_start_improved,
    XvfbComponent,
    DesktopEnvironmentComponent,
    VNCComponent,
    NoVNCComponent,
    NgrokComponent,
    LifecycleManager,
    ComponentInfo,
    DesktopComponent,
    ServiceLifecycleMixin,
    Configurable,
    LazyInitializable,
)
from .logger_improved import (
    ColabLogger,
    LogLevel,
    MetricsCollector,
    get_default_colab_logger,
    get_logger,
    configure_logging,
)
from .port_manager_improved import (
    PortManager,
    PortInfo,
    is_port_in_use,
    find_available_port,
    kill_process_on_port,
)
from .health_improved import (
    ServiceHealthChecker,
    HealthMonitor,
    HealthStatus,
    HealthCheckResult,
    create_health_checker,
    quick_health_check,
)
from .config_improved import (
    ConfigValidator,
    ConfigBuilder,
    ValidationResult,
    ValidationSummary,
    validate_config,
    ConfigError,
)
from .base import (
    is_colab,
    get_default_log_dir,
    ensure_dir,
    CommandRunner,
)
from .helpers import (
    start_virtual_desktop,
    test_desktop,
    install_all_dependencies,
    get_desktop_status,
    wait_for_desktop_ready,
    PRESETS,
    create_desktop_with_preset,
    quick_health_check as quick_health_check_helper,
)

# Maintain backward compatibility with original API
from .core import ColabDesktop as ColabDesktopOriginal
from .helpers import start_virtual_desktop as start_virtual_desktop_original

# Default to improved version
start_virtual_desktop = start_virtual_desktop  # Re-export - uses improved version from helpers

__all__ = [
    # Main classes
    "ColabDesktopImproved",
    "ColabDesktopOriginal",
    "start_virtual_desktop",
    "quick_start_improved",

    # Components
    "XvfbComponent",
    "DesktopEnvironmentComponent",
    "VNCComponent",
    "NoVNCComponent",
    "NgrokComponent",
    "LifecycleManager",
    "ComponentInfo",
    "DesktopComponent",

    # Mixins
    "ServiceLifecycleMixin",
    "Configurable",
    "LazyInitializable",

    # Logging
    "ColabLogger",
    "LogLevel",
    "MetricsCollector",
    "get_default_colab_logger",

    # Port management
    "PortManager",
    "PortInfo",
    "is_port_in_use",
    "find_available_port",

    # Health
    "ServiceHealthChecker",
    "HealthMonitor",
    "HealthStatus",
    "HealthCheckResult",
    "create_health_checker",
    "quick_health_check",

    # Config
    "ConfigValidator",
    "ConfigBuilder",
    "ValidationResult",
    "ValidationSummary",
    "validate_config",
    "ConfigError",

    # Utilities
    "is_colab",
    "get_default_log_dir",
    "ensure_dir",
    "CommandRunner",

    # Helpers
    "test_desktop",
    "install_all_dependencies",
    "get_desktop_status",
    "wait_for_desktop_ready",
    "PRESETS",
    "create_desktop_with_preset",
]

__version__ = "1.1.0-improved"
__author__ = "AI Agent"
__email__ = "agent@stepfun.com"