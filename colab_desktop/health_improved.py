"""
Service Health Checks and Verification for Colab Virtual Desktop

Provides comprehensive health monitoring, verification, and self-healing
capabilities for all desktop services.
"""

import os
import sys
import time
import subprocess
import socket
import psutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import platform


class HealthStatus(Enum):
    """Service health status"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    service_name: str
    status: HealthStatus
    message: str = ""
    details: Optional[Dict[str, Any]] = None
    last_check: float = 0.0
    response_time_ms: Optional[float] = None
    pid: Optional[int] = None
    port: Optional[int] = None
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'service': self.service_name,
            'status': self.status.value,
            'message': self.message,
            'details': self.details or {},
            'last_check': self.last_check,
            'response_time_ms': self.response_time_ms,
            'pid': self.pid,
            'port': self.port,
            'url': self.url
        }


@dataclass
class ServiceThresholds:
    """Health threshold configuration"""
    start_timeout: int = 30
    response_timeout: int = 5
    max_restart_attempts: int = 3
    restart_backoff_factor: float = 2.0
    memory_limit_mb: int = 500
    cpu_limit_percent: float = 80.0


class ServiceHealthChecker:
    """
    Comprehensive health checker for desktop services

    Features:
    - Multi-layer health checks (process, port, HTTP, X11)
    - Automatic recovery attempts
    - Performance metrics
    - Dependency verification
    - Resource usage monitoring
    - Health history tracking
    """

    # Service definitions with their health checks
    SERVICE_DEFINITIONS = {
        'xvfb': {
            'display_env': 'DISPLAY',
            'port': 6000,  # Base port for display :1 -> 6001, but we check 6000
            'check_command': 'xset q',
            'process_pattern': 'Xvfb',
            'required': True
        },
        'vnc': {
            'port': 5901,
            'process_pattern': 'Xvnc|vncserver|tightvnc',
            'required': True,
            'dependency': 'xvfb'
        },
        'novnc': {
            'port': 6080,
            'process_pattern': 'websockify',
            'url_path': '/vnc.html',
            'required': True,
            'dependency': 'vnc'
        },
        'ngrok': {
            'process_pattern': 'ngrok',
            'check_url': True,
            'url_suffix': '/vnc.html',
            'required': True,
            'dependency': 'novnc'
        }
    }

    def __init__(
        self,
        thresholds: Optional[ServiceThresholds] = None,
        runner: Optional[Callable] = None,
        logger: Optional[Callable] = None
    ):
        """
        Initialize health checker

        Args:
            thresholds: Health check thresholds
            runner: Command runner (like CommandRunner.run)
            logger: Logging function
        """
        self.thresholds = thresholds or ServiceThresholds()
        self.runner = runner or self._default_runner
        self.logger = logger or print
        self.results: Dict[str, HealthCheckResult] = {}
        self.history: List[Dict[str, Any]] = []
        self.restart_attempts: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

    def _default_runner(self, cmd: str, **kwargs) -> Tuple[int, str, str]:
        """Default command runner"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=kwargs.get('timeout', self.thresholds.response_timeout)
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Timeout"
        except Exception as e:
            return -1, "", str(e)

    def check_xvfb(self) -> HealthCheckResult:
        """Check Xvfb service"""
        start = time.time()

        # Check process
        rc, out, err = self.runner("pgrep -f Xvfb", capture=True, check=False)
        pids = [int(p) for p in out.strip().split('\n') if p.strip()] if rc == 0 else []

        if not pids:
            return HealthCheckResult(
                service_name='xvfb',
                status=HealthStatus.STOPPED,
                message="Xvfb process not found",
                last_check=time.time()
            )

        pid = pids[0]

        # Check display in environment
        display = os.environ.get('DISPLAY', '')
        if not display:
            return HealthCheckResult(
                service_name='xvfb',
                status=HealthStatus.UNHEALTHY,
                message="DISPLAY environment variable not set",
                pid=pid,
                last_check=time.time()
            )

        # Check if X server responds
        try:
            rc, out, err = self.runner("xset q", capture=True, timeout=2)
            if rc == 0:
                response_time = (time.time() - start) * 1000
                return HealthCheckResult(
                    service_name='xvfb',
                    status=HealthStatus.HEALTHY,
                    message="Xvfb running and responsive",
                    pid=pid,
                    port=6000 + int(display[1:]) if display.startswith(':') and display[1:].isdigit() else None,
                    response_time_ms=response_time,
                    last_check=time.time(),
                    details={'display': display}
                )
            else:
                return HealthCheckResult(
                    service_name='xvfb',
                    status=HealthStatus.UNHEALTHY,
                    message=f"X server not responding: {err}",
                    pid=pid,
                    last_check=time.time()
                )
        except Exception as e:
            return HealthCheckResult(
                service_name='xvfb',
                status=HealthStatus.UNHEALTHY,
                message=f"X check failed: {e}",
                pid=pid,
                last_check=time.time()
            )

    def check_vnc(self) -> HealthCheckResult:
        """Check VNC server"""
        start = time.time()

        # Check process
        rc, out, err = self.runner("pgrep -f 'Xvnc|vncserver'", capture=True, check=False)
        pids = [int(p) for p in out.strip().split('\n') if p.strip()] if rc == 0 else []

        if not pids:
            return HealthCheckResult(
                service_name='vnc',
                status=HealthStatus.STOPPED,
                message="VNC server process not found",
                last_check=time.time()
            )

        pid = pids[0]

        # Check port
        port = 5901  # Default
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.thresholds.response_timeout)
                result = s.connect_ex(('localhost', port))
                if result == 0:
                    response_time = (time.time() - start) * 1000
                    return HealthCheckResult(
                        service_name='vnc',
                        status=HealthStatus.HEALTHY,
                        message="VNC server running and accepting connections",
                        pid=pid,
                        port=port,
                        response_time_ms=response_time,
                        last_check=time.time()
                    )
        except:
            pass

        return HealthCheckResult(
            service_name='vnc',
            status=HealthStatus.UNHEALTHY,
            message="VNC port not responding",
            pid=pid,
            port=port,
            last_check=time.time()
        )

    def check_novnc(self) -> HealthCheckResult:
        """Check noVNC websockify proxy"""
        start = time.time()

        # Check process
        rc, out, err = self.runner("pgrep -f websockify", capture=True, check=False)
        pids = [int(p) for p in out.strip().split('\n') if p.strip()] if rc == 0 else []

        if not pids:
            return HealthCheckResult(
                service_name='novnc',
                status=HealthStatus.STOPPED,
                message="websockify process not found",
                last_check=time.time()
            )

        pid = pids[0]
        port = 6080

        # Check HTTP endpoint
        try:
            import urllib.request
            import urllib.error

            url = f"http://localhost:{port}/vnc.html"
            req = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(req, timeout=self.thresholds.response_timeout) as resp:
                if resp.status == 200:
                    response_time = (time.time() - start) * 1000
                    return HealthCheckResult(
                        service_name='novnc',
                        status=HealthStatus.HEALTHY,
                        message="noVNC web interface responding",
                        pid=pid,
                        port=port,
                        url=url,
                        response_time_ms=response_time,
                        last_check=time.time(),
                        details={'status_code': resp.status}
                    )
        except urllib.error.URLError as e:
            return HealthCheckResult(
                service_name='novnc',
                status=HealthStatus.UNHEALTHY,
                message=f"Web request failed: {e.reason}",
                pid=pid,
                port=port,
                last_check=time.time()
            )
        except Exception as e:
            return HealthCheckResult(
                service_name='novnc',
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {e}",
                pid=pid,
                port=port,
                last_check=time.time()
            )

    def check_ngrok(self) -> HealthCheckResult:
        """Check ngrok tunnel"""
        start = time.time()

        # Check process
        rc, out, err = self.runner("pgrep -f ngrok", capture=True, check=False)
        pids = [int(p) for p in out.strip().split('\n') if p.strip()] if rc == 0 else []

        if not pids:
            return HealthCheckResult(
                service_name='ngrok',
                status=HealthStatus.STOPPED,
                message="ngrok process not found",
                last_check=time.time()
            )

        pid = pids[0]

        # Check via pyngrok if available
        try:
            from pyngrok import ngrok
            tunnels = ngrok.get_tunnels()
            if tunnels:
                tunnel = tunnels[0]
                response_time = (time.time() - start) * 1000
                return HealthCheckResult(
                    service_name='ngrok',
                    status=HealthStatus.HEALTHY,
                    message="ngrok tunnel active",
                    pid=pid,
                    url=str(tunnel.public_url).replace("http://", "https://"),
                    response_time_ms=response_time,
                    last_check=time.time(),
                    details={'tunnels': len(tunnels)}
                )
        except:
            pass

        return HealthCheckResult(
            service_name='ngrok',
            status=HealthStatus.UNHEALTHY,
            message="ngrok tunnel not accessible",
            pid=pid,
            last_check=time.time()
        )

    def check_dependencies(self, service_name: str) -> Tuple[bool, List[str]]:
        """
        Check if service dependencies are healthy

        Args:
            service_name: Name of service to check

        Returns:
            Tuple of (all_deps_healthy, list_of_unhealthy_deps)
        """
        definition = self.SERVICE_DEFINITIONS.get(service_name, {})
        dep = definition.get('dependency')
        if not dep:
            return True, []

        dep_result = self.results.get(dep)
        if not dep_result:
            return False, [f"{dep} not checked yet"]
        if dep_result.status != HealthStatus.HEALTHY:
            return False, [dep]

        return True, []

    def run_all_checks(self, include_deps: bool = True) -> Dict[str, HealthCheckResult]:
        """
        Run health checks for all services

        Args:
            include_deps: Check dependencies as well

        Returns:
            Dictionary of service_name -> HealthCheckResult
        """
        new_results = {}

        # Define check order (respect dependencies)
        services = ['xvfb', 'vnc', 'novnc', 'ngrok']

        for service in services:
            # Check dependency
            if include_deps:
                deps_ok, unhealthy_deps = self.check_dependencies(service)
                if not deps_ok:
                    new_results[service] = HealthCheckResult(
                        service_name=service,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Dependencies not healthy: {', '.join(unhealthy_deps)}",
                        last_check=time.time()
                    )
                    continue

            # Run service-specific check
            try:
                if service == 'xvfb':
                    result = self.check_xvfb()
                elif service == 'vnc':
                    result = self.check_vnc()
                elif service == 'novnc':
                    result = self.check_novnc()
                elif service == 'ngrok':
                    result = self.check_ngrok()
                else:
                    result = HealthCheckResult(
                        service_name=service,
                        status=HealthStatus.UNKNOWN,
                        message="Unknown service",
                        last_check=time.time()
                    )

                new_results[service] = result

            except Exception as e:
                new_results[service] = HealthCheckResult(
                    service_name=service,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check exception: {e}",
                    last_check=time.time()
                )

        # Update results atomically
        with self._lock:
            self.results.update(new_results)
            # Add to history
            self.history.append({
                'timestamp': time.time(),
                'results': {k: v.to_dict() for k, v in new_results.items()}
            })
            # Limit history size
            if len(self.history) > 1000:
                self.history = self.history[-100:]

        return new_results

    def get_overall_health(self) -> HealthStatus:
        """Get overall health status across all required services"""
        results = self.results

        if not results:
            return HealthStatus.UNKNOWN

        # Check required services
        required_services = [s for s, d in self.SERVICE_DEFINITIONS.items() if d.get('required')]

        for service in required_services:
            result = results.get(service)
            if not result or result.status != HealthStatus.HEALTHY:
                return HealthStatus.UNHEALTHY

        return HealthStatus.HEALTHY

    def get_unhealthy_services(self) -> List[HealthCheckResult]:
        """Get list of unhealthy services"""
        return [r for r in self.results.values() if r.status != HealthStatus.HEALTHY]

    def get_service_info(self, service_name: str) -> Optional[HealthCheckResult]:
        """Get health info for specific service"""
        return self.results.get(service_name)

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
            required_services: List of services that must be healthy (None for all required)

        Returns:
            True if healthy within timeout, False otherwise
        """
        start = time.time()
        services_to_check = required_services or [
            s for s, d in self.SERVICE_DEFINITIONS.items() if d.get('required')
        ]

        while time.time() - start < timeout:
            self.run_all_checks()

            unhealthy = self.get_unhealthy_services()
            unhealthy_names = [s.service_name for s in unhealthy]

            # Check if all required services are healthy
            all_healthy = all(
                service not in unhealthy_names
                for service in services_to_check
            )

            if all_healthy:
                return True

            time.sleep(poll_interval)

        return False

    def start_monitoring(self, interval: float = 10.0):
        """
        Start background monitoring thread

        Args:
            interval: Check interval in seconds
        """
        if self._running:
            return

        self._running = True

        def monitor_loop():
            while self._running:
                try:
                    self.run_all_checks()
                    time.sleep(interval)
                except Exception as e:
                    self.logger(f"Health monitor error: {e}", level="ERROR")
                    time.sleep(interval)

        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        self.logger("Health monitoring started", level="INFO")

    def stop_monitoring(self):
        """Stop background monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self.logger("Health monitoring stopped", level="INFO")

    def get_health_report(self, include_history: bool = False) -> Dict[str, Any]:
        """
        Generate comprehensive health report

        Args:
            include_history: Include historical data

        Returns:
            Dictionary with health information
        """
        report = {
            'timestamp': time.time(),
            'overall_status': self.get_overall_health().value,
            'services': {k: v.to_dict() for k, v in self.results.items()},
            'unhealthy_count': len(self.get_unhealthy_services()),
            'required_services': [s for s, d in self.SERVICE_DEFINITIONS.items() if d.get('required')]
        }

        if include_history and self.history:
            report['history'] = self.history[-10:]  # Last 10 checks

        return report

    def get_resource_usage(self) -> Dict[str, Any]:
        """
        Get resource usage for desktop processes

        Returns:
            Dictionary with memory/CPU info
        """
        usage = {}
        try:
            for service, result in self.results.items():
                if result.pid:
                    try:
                        proc = psutil.Process(result.pid)
                        with proc.oneshot():
                            usage[service] = {
                                'pid': result.pid,
                                'memory_mb': proc.memory_info().rss / 1024 / 1024,
                                'cpu_percent': proc.cpu_percent(interval=0.1),
                                'num_threads': proc.num_threads(),
                                'status': proc.status()
                            }
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        usage[service] = {'error': 'Process not accessible'}
        except:
            pass

        return usage

    def check_port_availability(self, port: int, host: str = 'localhost') -> bool:
        """Check if a port is available for binding"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
                return True
        except OSError:
            return False

    def verify_all_ports(
        self,
        ports: List[int],
        host: str = 'localhost'
    ) -> Dict[int, bool]:
        """Verify multiple ports are available"""
        return {
            port: self.check_port_availability(port, host) or not self._is_port_in_use(port, host)
            for port in ports
        }

    def _is_port_in_use(self, port: int, host: str) -> bool:
        """Check if port is in use"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex((host, port))
                return result == 0
        except:
            return False

    def get_health_status_text(self) -> str:
        """
        Get human-readable health status

        Returns:
            Multi-line status string
        """
        lines = []
        lines.append("="*60)
        lines.append("SERVICE HEALTH STATUS")
        lines.append("="*60)

        overall = self.get_overall_health()
        icon = "✅" if overall == HealthStatus.HEALTHY else "❌"
        lines.append(f"Overall: {icon} {overall.value}")
        lines.append("")

        for service in ['xvfb', 'vnc', 'novnc', 'ngrok']:
            result = self.results.get(service)
            if result:
                icon = "✅" if result.status == HealthStatus.HEALTHY else "❌"
                lines.append(f"{icon} {service.upper()}")
                lines.append(f"   Status: {result.status.value}")
                if result.message:
                    lines.append(f"   Message: {result.message}")
                if result.pid:
                    lines.append(f"   PID: {result.pid}")
                if result.port:
                    lines.append(f"   Port: {result.port}")
                if result.url:
                    lines.append(f"   URL: {result.url}")
                if result.response_time_ms:
                    lines.append(f"   Response: {result.response_time_ms:.1f}ms")
                lines.append("")

        # Add resource usage
        usage = self.get_resource_usage()
        if usage:
            lines.append("RESOURCE USAGE:")
            for service, info in usage.items():
                if 'error' not in info:
                    lines.append(f"  {service}: {info['memory_mb']:.1f}MB RAM, "
                                 f"{info['cpu_percent']:.1f}% CPU, "
                                 f"{info['num_threads']} threads")
                else:
                    lines.append(f"  {service}: {info['error']}")

        lines.append("="*60)
        return "\n".join(lines)


class HealthMonitor:
    """
    Advanced health monitor with auto-recovery

    Features:
    - Continuous monitoring
    - Automatic restart of failed services
    - Circuit breaker pattern
    - Alerting callbacks
    - Metrics collection
    """

    def __init__(
        self,
        checker: ServiceHealthChecker,
        restart_callbacks: Optional[Dict[str, Callable]] = None,
        alert_callbacks: Optional[List[Callable]] = None,
        logger: Optional[Callable] = None
    ):
        """
        Initialize health monitor

        Args:
            checker: ServiceHealthChecker instance
            restart_callbacks: Dict of service_name -> restart function
            alert_callbacks: List of functions to call on health change
            logger: Logging function
        """
        self.checker = checker
        self.restart_callbacks = restart_callbacks or {}
        self.alert_callbacks = alert_callbacks or []
        self.logger = logger or print
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._circuit_breakers: Dict[str, Dict[str, Any]] = {}
        self._monitored = False

    def start(
        self,
        check_interval: float = 10.0,
        auto_restart: bool = True,
        max_restart_attempts: int = 3
    ):
        """
        Start health monitoring

        Args:
            check_interval: Seconds between checks
            auto_restart: Automatically restart failed services
            max_restart_attempts: Max restart attempts per service per hour
        """
        self.check_interval = check_interval
        self.auto_restart = auto_restart
        self.max_restart_attempts = max_restart_attempts
        self._running = True

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self.logger("Health monitor started", level="INFO")

    def stop(self):
        """Stop health monitoring"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.logger("Health monitor stopped", level="INFO")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                changes = self.checker.run_all_checks()
                self._process_health_changes(changes)

                # Try auto-restart if enabled
                if self.auto_restart:
                    self._attempt_auto_restart()

                time.sleep(self.check_interval)
            except Exception as e:
                self.logger(f"Monitor loop error: {e}", level="ERROR")
                time.sleep(self.check_interval)

    def _process_health_changes(self, changes: Dict[str, HealthCheckResult]):
        """Detect and react to health status changes"""
        for service, result in changes.items():
            # Check circuit breaker
            breaker = self._circuit_breakers.get(service, {
                'failures': 0,
                'last_failure': 0,
                'state': 'CLOSED'
            })
            self._circuit_breakers[service] = breaker

            old_status = breaker.get('last_status', HealthStatus.UNKNOWN)
            new_status = result.status

            if new_status != old_status:
                # Status changed
                breaker['last_status'] = new_status
                self._on_status_change(service, old_status, new_status, result)

            # Update failure count
            if new_status != HealthStatus.HEALTHY:
                breaker['failures'] = breaker.get('failures', 0) + 1
                breaker['last_failure'] = time.time()
            else:
                breaker['failures'] = 0  # Reset on success

            # Check circuit breaker
            if breaker['failures'] >= 5 and breaker['state'] == 'CLOSED':
                breaker['state'] = 'OPEN'
                self.logger(f"Circuit breaker OPEN for {service}", level="WARNING")

    def _on_status_change(
        self,
        service: str,
        old_status: HealthStatus,
        new_status: HealthStatus,
        result: HealthCheckResult
    ):
        """Handle status change"""
        # Log
        if new_status == HealthStatus.HEALTHY:
            self.logger(f"✅ {service} is now healthy", level="INFO")
        else:
            self.logger(f"❌ {service} became {new_status.value}: {result.message}", level="WARNING")

        # Call alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(service, old_status, new_status, result.to_dict())
            except Exception as e:
                self.logger(f"Alert callback error: {e}", level="ERROR")

    def _attempt_auto_restart(self):
        """Attempt to restart failed services"""
        for service, result in self.checker.results.items():
            if result.status != HealthStatus.HEALTHY and service in self.restart_callbacks:
                breaker = self._circuit_breakers.get(service, {})

                # Check circuit breaker
                if breaker.get('state') == 'OPEN':
                    continue

                # Check restart throttling
                attempts = breaker.get('restart_attempts', 0)
                if attempts >= self.max_restart_attempts:
                    # Check if we've exceeded per-hour limit
                    last = breaker.get('last_restart', 0)
                    if time.time() - last < 3600:
                        continue
                    else:
                        breaker['restart_attempts'] = 0  # Reset after hour

                # Attempt restart
                self.logger(f"Attempting auto-restart for {service}...", level="INFO")
                try:
                    restart_func = self.restart_callbacks[service]
                    restart_func()
                    breaker['restart_attempts'] = attempts + 1
                    breaker['last_restart'] = time.time()
                    time.sleep(3)  # Give it time to start

                    # Re-check immediately
                    self.checker.run_all_checks()
                except Exception as e:
                    self.logger(f"Auto-restart failed for {service}: {e}", level="ERROR")


def create_health_checker(
    desktop_instance: 'ColabDesktop',
    **kwargs
) -> ServiceHealthChecker:
    """
    Factory function to create health checker for a desktop instance

    Args:
        desktop_instance: ColabDesktop instance
        **kwargs: Additional arguments for ServiceHealthChecker

    Returns:
        Configured ServiceHealthChecker
    """
    def custom_runner(cmd: str, **kwargs):
        """Runner that uses desktop's runner if available"""
        return desktop_instance.runner.run(cmd, **kwargs)

    checker = ServiceHealthChecker(
        runner=custom_runner,
        logger=desktop_instance.log,
        **kwargs
    )

    # Store reference in desktop
    desktop_instance.health_checker = checker

    return checker


def quick_health_check(desktop: 'ColabDesktop') -> str:
    """
    Quick health check suitable for CLI display

    Args:
        desktop: ColabDesktop instance

    Returns:
        Formatted status string
    """
    if not hasattr(desktop, 'health_checker'):
        return "Health checker not initialized"

    checker = desktop.health_checker
    checker.run_all_checks()
    return checker.get_health_status_text()