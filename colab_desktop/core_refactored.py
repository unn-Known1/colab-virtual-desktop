#!/usr/bin/env python3
"""
Colab Virtual Desktop - Core functionality (Fully Refactored)

This is the main improved implementation that integrates:
- Comprehensive error handling
- Advanced logging system
- Health monitoring
- Port management
- Configuration validation
- Modular architecture
"""

import os
import sys
import signal
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

# Import improved components
from .base import (
    DesktopComponent, LifecycleManager, ComponentInfo,
    Configurable, ServiceLifecycleMixin, is_colab, get_default_log_dir
)
from .logger_improved import ColabLogger, LogLevel
from .port_manager_improved import PortManager, PortInfo
from .health_improved import (
    ServiceHealthChecker, HealthMonitor, HealthStatus,
    create_health_checker, quick_health_check
)
from .config_improved import ConfigValidator, ConfigBuilder, validate_config


class XvfbComponent(DesktopComponent, ServiceLifecycleMixin, Configurable):
    """Xvfb virtual display server component"""

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[Callable] = None,
        runner: Optional[Callable] = None
    ):
        DesktopComponent.__init__(self, logger, runner)
        ServiceLifecycleMixin.__init__(self)
        Configurable.__init__(self, config)

        self.display = self.get_config('display', ':1')
        self.geometry = self.get_config('geometry', '1280x720')
        self.depth = self.get_config('depth', 24)
        self.process_name = 'Xvfb'

    def initialize(self) -> bool:
        """Check if Xvfb is available"""
        self.logger("Checking Xvfb availability...")
        rc, out, err = self.runner("which Xvfb", capture=True)
        if rc != 0:
            self.logger("Xvfb not found - will attempt installation", level="WARNING")
        return True

    def start(self) -> bool:
        """Start Xvfb"""
        self.logger(f"Starting Xvfb on display {self.display}...")

        # Build command
        cmd = f"Xvfb {self.display} -screen 0 {self.geometry}x{self.depth} -ac +extension GLX +render -noreset"

        if self._start_process(cmd):
            # Set DISPLAY
            os.environ["DISPLAY"] = self.display
            time.sleep(2)
            self.logger(f"✅ Xvfb started (PID {self._pid})")
            return True

        self.logger("❌ Failed to start Xvfb", level="ERROR")
        return False

    def stop(self) -> bool:
        """Stop Xvfb"""
        self.logger("Stopping Xvfb...")
        return self._stop_process(kill=True)

    def is_running(self) -> bool:
        """Check if Xvfb is running"""
        if self._process:
            return self.is_process_running()
        # Fallback: check by pattern
        rc, out, _ = self.runner("pgrep -f Xvfb", capture=True)
        return rc == 0 and bool(out.strip())

    def get_status(self) -> Dict[str, Any]:
        """Get Xvfb status"""
        info = ComponentInfo(
            name='xvfb',
            status='running' if self.is_running() else 'stopped',
            pid=self._pid,
            metadata={'display': self.display, 'geometry': self.geometry, 'depth': self.depth}
        )
        return info.to_dict()


class DesktopEnvironmentComponent(DesktopComponent, ServiceLifecycleMixin, Configurable):
    """Desktop environment (XFCE) component"""

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[Callable] = None,
        runner: Optional[Callable] = None
    ):
        DesktopComponent.__init__(self, logger, runner)
        ServiceLifecycleMixin.__init__(self)
        Configurable.__init__(self, config)

        self.display = self.get_config('display', ':1')

    def initialize(self) -> bool:
        """Detect available desktop environment"""
        self.logger("Detecting desktop environments...")
        self.desktop_cmd = None

        # Check for common desktops
        checks = [
            ('xfce4', 'startxfce4'),
            ('gnome', 'gnome-session'),
            ('kde', 'startkde'),
        ]

        for name, cmd in checks:
            rc, _, _ = self.runner(f"which {cmd}", capture=True)
            if rc == 0:
                self.desktop_cmd = cmd
                self.logger(f"Found {name} desktop: {cmd}")
                break

        if not self.desktop_cmd:
            self.logger("No desktop environment found, will use fallback", level="WARNING")
            self.desktop_cmd = "xterm"

        return True

    def start(self) -> bool:
        """Start desktop environment"""
        self.logger(f"Starting desktop environment...")

        # Start desktop command
        if self._start_process(f"{self.desktop_cmd} &"):
            time.sleep(3)
            self.logger("✅ Desktop environment started")
            return True

        self.logger("❌ Failed to start desktop", level="ERROR")
        return False

    def stop(self) -> bool:
        """Stop desktop environment"""
        self.logger("Stopping desktop environment...")
        # Kill all X clients
        self.runner("pkill -KILL -u $USER", check=False)
        return self._stop_process(kill=True)

    def is_running(self) -> bool:
        """Check if desktop is running"""
        # Check for common desktop processes
        rc, out, _ = self.runner("ps aux | grep -E '(xfce|gnome|kde|xterm)' | grep -v grep", capture=True)
        return rc == 0 and bool(out.strip())

    def get_status(self) -> Dict[str, Any]:
        """Get desktop status"""
        info = ComponentInfo(
            name='desktop',
            status='running' if self.is_running() else 'stopped',
            pid=self._pid,
            metadata={'display': self.display, 'command': getattr(self, 'desktop_cmd', 'unknown')}
        )
        return info.to_dict()


class VNCComponent(DesktopComponent, ServiceLifecycleMixin, Configurable):
    """VNC server component"""

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[Callable] = None,
        runner: Optional[Callable] = None
    ):
        DesktopComponent.__init__(self, logger, runner)
        ServiceLifecycleMixin.__init__(self)
        Configurable.__init__(self, config)

        self.display = self.get_config('display', ':1')
        self.geometry = self.get_config('geometry', '1280x720')
        self.depth = self.get_config('depth', 24)
        self.vnc_port = self.get_config('vnc_port', 5901)
        self.vnc_password = self.get_config('vnc_password', 'colab123')
        self.vnc_server = self.get_config('vnc_server', None)  # Auto-detect if None

    def initialize(self) -> bool:
        """Detect VNC server"""
        self.logger("Detecting VNC server...")

        # Auto-detect if not specified
        if not self.vnc_server:
            candidates = ['vncserver', 'Xvnc', 'tightvncserver', 'TigerVNC']
            for cmd in candidates:
                rc, _, _ = self.runner(f"which {cmd}", capture=True)
                if rc == 0:
                    self.vnc_server = cmd
                    self.logger(f"Found VNC server: {cmd}")
                    break

        if not self.vnc_server:
            self.logger("VNC server not found", level="ERROR")
            return False

        return True

    def start(self) -> bool:
        """Start VNC server"""
        self.logger(f"Starting VNC server on port {self.vnc_port}...")

        # Build command
        cmd = f"{self.vnc_server} {self.display} -geometry {self.geometry} -depth {self.depth}"

        # Add password if available
        vnc_passwd = Path.home() / '.vnc' / 'passwd'
        if vnc_passwd.exists():
            cmd += f" -PasswordFile={vnc_passwd}"
        else:
            cmd += " -SecurityTypes None"  # Allow no password

        if self._start_process(cmd):
            time.sleep(2)
            self.logger(f"✅ VNC server started (PID {self._pid})")
            return True

        self.logger("❌ Failed to start VNC server", level="ERROR")
        return False

    def stop(self) -> bool:
        """Stop VNC server"""
        self.logger("Stopping VNC server...")
        return self._stop_process(kill=True)

    def is_running(self) -> bool:
        """Check if VNC is running"""
        if self._process:
            return self.is_process_running()
        pattern = self.vnc_server or 'Xvnc|vncserver'
        rc, out, _ = self.runner(f"pgrep -f '{pattern}'", capture=True)
        return rc == 0 and bool(out.strip())

    def get_status(self) -> Dict[str, Any]:
        """Get VNC status"""
        info = ComponentInfo(
            name='vnc',
            status='running' if self.is_running() else 'stopped',
            pid=self._pid,
            port=self.vnc_port,
            metadata={'geometry': self.geometry, 'depth': self.depth, 'server': self.vnc_server}
        )
        return info.to_dict()


class NoVNCComponent(DesktopComponent, ServiceLifecycleMixin, Configurable):
    """noVNC websockify proxy component"""

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[Callable] = None,
        runner: Optional[Callable] = None
    ):
        DesktopComponent.__init__(self, logger, runner)
        ServiceLifecycleMixin.__init__(self)
        Configurable.__init__(self, config)

        self.novnc_port = self.get_config('novnc_port', 6080)
        self.vnc_port = self.get_config('vnc_port', 5901)
        self.novnc_path = self.get_config('novnc_path', None)

    def initialize(self) -> bool:
        """Find noVNC installation"""
        self.logger("Locating noVNC...")

        # Check configured path
        if self.novnc_path and Path(self.novnc_path).exists():
            self.logger(f"Using configured noVNC path: {self.novnc_path}")
            return True

        # Search common locations
        paths = [
            '/usr/share/novnc',
            '/usr/local/novnc',
            str(Path.home() / 'novnc'),
            str(Path.home() / 'noVNC'),
        ]

        for path in paths:
            if Path(path).exists():
                self.novnc_path = path
                self.logger(f"Found noVNC: {path}")
                return True

        self.logger("noVNC not found - will attempt to install from source", level="WARNING")
        return True

    def start(self) -> bool:
        """Start websockify proxy"""
        self.logger(f"Starting noVNC on port {self.novnc_port}...")

        if not self.novnc_path:
            # Try to install from source
            if not self._install_novnc():
                return False

        cmd = f"websockify --web={self.novnc_path} {self.novnc_port} localhost:{self.vnc_port}"

        if self._start_process(cmd):
            time.sleep(2)
            self.logger(f"✅ noVNC started (PID {self._pid})")
            return True

        self.logger("❌ Failed to start noVNC", level="ERROR")
        return False

    def _install_novnc(self) -> bool:
        """Install noVNC from source"""
        try:
            repo_dir = Path.home() / 'novnc'
            if not repo_dir.exists():
                self.logger("Installing noVNC from source...")
                rc, out, err = self.runner("git clone https://github.com/novnc/noVNC.git ~/novnc", timeout=120)
                if rc != 0:
                    self.logger(f"Git clone failed: {err}", level="ERROR")
                    return False

            # Use git version
            self.novnc_path = str(repo_dir)
            return True
        except Exception as e:
            self.logger(f"Failed to install noVNC: {e}", level="ERROR")
            return False

    def stop(self) -> bool:
        """Stop noVNC"""
        self.logger("Stopping noVNC...")
        return self._stop_process(kill=True)

    def is_running(self) -> bool:
        """Check if noVNC is running"""
        if self._process:
            return self.is_process_running()
        rc, out, _ = self.runner("pgrep -f websockify", capture=True)
        return rc == 0 and bool(out.strip())

    def get_status(self) -> Dict[str, Any]:
        """Get noVNC status"""
        info = ComponentInfo(
            name='novnc',
            status='running' if self.is_running() else 'stopped',
            pid=self._pid,
            port=self.novnc_port,
            url=f"http://localhost:{self.novnc_port}",
            metadata={'path': self.novnc_path, 'vnc_target': f'localhost:{self.vnc_port}'}
        )
        return info.to_dict()


class NgrokComponent(DesktopComponent, Configurable):
    """ngrok tunneling component"""

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[Callable] = None,
        runner: Optional[Callable] = None
    ):
        DesktopComponent.__init__(self, logger, runner)
        ServiceLifecycleMixin.__init__(self)
        Configurable.__init__(self, config)

        self.ngrok_token = self.get_config('ngrok_auth_token')
        self.ngrok_region = self.get_config('ngrok_region', 'us')
        self.novnc_port = self.get_config('novnc_port', 6080)
        self.tunnel = None
        self.tunnel_url = None

    def initialize(self) -> bool:
        """Check pyngrok availability"""
        self.logger("Checking ngrok/pyngrok...")

        try:
            import pyngrok
            self.logger("pyngrok is available")
            return True
        except ImportError:
            if self.ngrok_token:
                self.logger("pyngrok not installed but ngrok token provided", level="WARNING")
                return False
            else:
                self.logger("pyngrok not installed and no token provided - ngrok disabled", level="INFO")
                return False

    def start(self) -> bool:
        """Start ngrok tunnel"""
        if not self.ngrok_token:
            self.logger("No ngrok token - skipping", level="INFO")
            return True

        self.logger(f"Starting ngrok tunnel (region: {self.ngrok_region})...")

        try:
            from pyngrok import ngrok, conf
            conf.get_default().auth_token = self.ngrok_token
            conf.get_default().region = self.ngrok_region

            # Disable monitor thread
            conf.get_default().monitor_thread = False

            # Start tunnel
            self.tunnel = ngrok.connect(self.novnc_port, "http")
            self.tunnel_url = str(self.tunnel).replace("http://", "https://")

            self.logger(f"✅ ngrok tunnel: {self.tunnel_url}")
            return True

        except Exception as e:
            self.logger(f"❌ Failed to start ngrok: {e}", level="ERROR")
            return False

    def stop(self) -> bool:
        """Stop ngrok tunnel"""
        self.logger("Stopping ngrok...")
        if self.tunnel:
            try:
                from pyngrok import ngrok
                ngrok.disconnect(self.tunnel.public_url)
                self.tunnel = None
                self.tunnel_url = None
            except Exception as e:
                self.logger(f"Error stopping ngrok: {e}", level="WARNING")
        return True

    def is_running(self) -> bool:
        """Check if ngrok is running"""
        if self.tunnel:
            try:
                from pyngrok import ngrok
                tunnels = ngrok.get_tunnels()
                return any(t.public_url == self.tunnel.public_url for t in tunnels)
            except:
                return False
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get ngrok status"""
        info = ComponentInfo(
            name='ngrok',
            status='running' if self.is_running() else 'stopped',
            url=self.tunnel_url,
            metadata={'region': self.ngrok_region}
        )
        return info.to_dict()


class ColabDesktopImproved:
    """
    Improved Colab Virtual Desktop with all enhancements

    Integrates:
    - Modular component architecture
    - Comprehensive logging
    - Health monitoring
    - Port management
    - Configuration validation
    - Graceful degradation
    - Auto-recovery
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
    ):
        """
        Initialize improved ColabDesktop

        All same parameters as original, plus optional advanced components
        """
        # Build configuration
        self.config = {
            'ngrok_auth_token': ngrok_auth_token,
            'vnc_password': vnc_password,
            'display': display,
            'geometry': geometry,
            'depth': depth,
            'vnc_port': vnc_port,
            'novnc_port': novnc_port,
            'ngrok_region': ngrok_region,
            'auto_open': auto_open,
            'install_deps': install_deps,
        }

        # Validate configuration
        self.logger = logger or ColabLogger(
            name="colab_desktop_improved",
            level=LogLevel.INFO,
            log_dir=str(get_default_log_dir()),
            console_output=True
        )

        self.port_manager = port_manager or PortManager(logger=self.logger)
        self.health_checker = None  # Will be created after components start

        # Lifecycle manager
        self.lifecycle = LifecycleManager(logger=self.logger)

        # Components (will be created in setup)
        self.components: Dict[str, DesktopComponent] = {}
        self.is_running = False
        self._shutdown_event = threading.Event()

    def _create_components(self):
        """Create all component instances"""
        self.logger.info("Creating components...")

        self.components = {
            'xvfb': XvfbComponent(self.config, logger=self.logger.log, runner=self.run_command),
            'desktop': DesktopEnvironmentComponent(self.config, logger=self.logger.log, runner=self.run_command),
            'vnc': VNCComponent(self.config, logger=self.logger.log, runner=self.run_command),
            'novnc': NoVNCComponent(self.config, logger=self.logger.log, runner=self.run_command),
        }

        # Only add ngrok if token provided
        if self.config.get('ngrok_auth_token'):
            self.components['ngrok'] = NgrokComponent(self.config, logger=self.logger.log, runner=self.run_command)

        # Register with lifecycle manager
        self.lifecycle.register('xvfb', self.components['xvfb'])
        self.lifecycle.register('desktop', self.components['desktop'], dependencies=['xvfb'])
        self.lifecycle.register('vnc', self.components['vnc'], dependencies=['xvfb'])
        self.lifecycle.register('novnc', self.components['novnc'], dependencies=['vnc'])
        if 'ngrok' in self.components:
            self.lifecycle.register('ngrok', self.components['ngrok'], dependencies=['novnc'])

    def run_command(self, cmd: str, **kwargs) -> Tuple[int, str, str]:
        """Run command with logging"""
        self.logger.debug(f"Running: {cmd}")
        return self.runner(cmd, **kwargs)

    def validate_environment(self) -> List[str]:
        """Validate environment dependencies"""
        self.logger.info("Validating environment...")

        validator = ConfigValidator(self.config)
        summary = validator.validate_all(auto_correct=True)

        if summary.errors:
            self.logger.error("Configuration validation failed:")
            for err in summary.errors:
                self.logger.error(f"  {err.field}: {err.message}")
                if err.suggestion:
                    self.logger.info(f"    Suggestion: {err.suggestion}")
            return [e.message for e in summary.errors]

        if summary.warnings:
            for warn in summary.warnings:
                self.logger.warning(f"{warn.field}: {warn.message}")

        # Apply corrections
        self.config.update(validator.get_corrected_config())

        # Check critical dependencies
        missing = []
        required = ['Xvfb', 'xset']
        for cmd in required:
            rc, _, _ = self.run_command(f"which {cmd}", capture=True)
            if rc != 0:
                missing.append(f"Required command '{cmd}' not found")

        return missing

    def install_dependencies(self) -> bool:
        """Install system dependencies"""
        self.logger.info("Installing dependencies...")

        if not is_colab():
            self.logger.warning("Not in Colab - skipping apt installation")
            return True

        packages = [
            "xfce4", "xfce4-goodies", "tightvncserver", "novnc",
            "websockify", "xvfb", "wget", "curl", "git",
            "python3-pip", "dbus", "dbus-x11", "x11-utils"
        ]

        cmd = f"apt-get update -qq && apt-get install -y -qq {' '.join(packages)}"
        rc, out, err = self.run_command(cmd, timeout=600)

        if rc != 0:
            self.logger.error(f"Dependency installation failed: {err}")
            return False

        # Install Python packages
        try:
            import pyngrok
        except ImportError:
            self.run_command("pip install -q pyngrok>=3.0.0", timeout=120)

        self.logger.info("✅ Dependencies installed")
        return True

    def setup_vnc_password(self) -> bool:
        """Setup VNC password"""
        self.logger.info("Setting up VNC password...")

        vnc_dir = Path.home() / '.vnc'
        vnc_dir.mkdir(parents=True, exist_ok=True)

        vnc_passwd = vnc_dir / 'passwd'

        # Only set if password provided
        if self.config['vnc_password']:
            try:
                cmd = f"echo '{self.config['vnc_password']}' | vncpasswd -f > {vnc_passwd}"
                rc, out, err = self.run_command(cmd)
                if rc == 0:
                    self.run_command(f"chmod 600 {vnc_passwd}", check=False)
                    self.logger.info("VNC password configured")
                    return True
            except:
                self.logger.warning("Failed to set VNC password, continuing without it")
                return True
        else:
            self.logger.info("No VNC password specified, server will be unlocked")

        return True

    def setup(self) -> bool:
        """
        Setup phase: Prepare environment

        Returns:
            True if setup successful, False otherwise
        """
        self.logger.info("="*60)
        self.logger.info("SETUP PHASE")
        self.logger.info("="*60)

        # Validate configuration
        missing_deps = self.validate_environment()
        if missing_deps:
            return False

        # Install dependencies if needed
        if self.config['install_deps']:
            if not self.install_dependencies():
                return False

        # Setup VNC password
        if not self.setup_vnc_password():
            return False

        # Create components
        self._create_components()

        # Initialize components
        if not self.lifecycle.initialize_all():
            self.logger.error("Component initialization failed")
            return False

        self.logger.info("✅ Setup complete")
        return True

    def start(self) -> bool:
        """
        Start all services

        Returns:
            True if all started successfully
        """
        self.logger.info("="*60)
        self.logger.info("STARTING VIRTUAL DESKTOP")
        self.logger.info("="*60)

        # Start all components
        if not self.lifecycle.start_all():
            self.logger.error("Failed to start some components")
            return False

        self.is_running = True

        # Create health checker
        self.health_checker = create_health_checker(self)
        self.health_checker.run_all_checks()

        # Print status
        url = self.get_url()
        if url:
            self.logger.info("="*60)
            self.logger.info("✅ VIRTUAL DESKTOP READY!")
            self.logger.info("="*60)
            self.logger.info(f"🌐 Desktop URL: {url}")
            if self.config['auto_open']:
                self._open_browser(url)
            self.logger.info("="*60)

        # Log component status
        status = self.lifecycle.get_status()
        for name, info in status.items():
            icon = "✅" if info['status'] == 'running' else "❌"
            self.logger.info(f"  {icon} {name}: {info['status']}")

        return True

    def stop(self):
        """Stop all services"""
        if not self.is_running:
            return

        self.logger.info("Stopping virtual desktop...")
        self._shutdown_event.set()

        # Stop health monitoring
        if hasattr(self, 'health_monitor'):
            self.health_monitor.stop()

        # Stop components
        self.lifecycle.stop_all()

        # Cleanup port manager
        self.port_manager.cleanup_all()

        self.is_running = False
        self.logger.info("✅ Virtual desktop stopped")

    def restart(self) -> bool:
        """Restart all services"""
        self.logger.info("Restarting virtual desktop...")
        self.stop()
        time.sleep(3)
        return self.start()

    def get_url(self) -> Optional[str]:
        """Get public desktop URL"""
        ngrok_status = self.lifecycle.info.get('ngrok')
        if ngrok_status and ngrok_status.url:
            novnc_port = self.config.get('novnc_port', 6080)
            return f"{ngrok_status.url}/vnc.html"
        return None

    def _open_browser(self, url: str):
        """Open URL in browser"""
        try:
            import webbrowser
            webbrowser.open(url)
            self.logger.info(f"🌐 Opening browser: {url}")
        except Exception as e:
            self.logger.warning(f"Failed to open browser: {e}")

    def launch_app(self, command: str, wait: bool = False):
        """Launch GUI application"""
        env = os.environ.copy()
        env['DISPLAY'] = self.config['display']

        if wait:
            self.runner(command, env=env)
        else:
            import subprocess
            subprocess.Popen(
                command,
                shell=True,
                env=env,
                start_new_session=True
            )

        self.logger.info(f"🚀 Launched: {command}")

    def take_screenshot(self, output_path: str = "/content/desktop_screenshot.png") -> str:
        """Take screenshot"""
        env = os.environ.copy()
        env['DISPLAY'] = self.config['display']

        methods = [
            f"scrot {output_path}",
            f"import -window root {output_path}",
        ]

        for method in methods:
            try:
                result = self.runner(method, timeout=5)
                if result[0] == 0 and Path(output_path).exists():
                    self.logger.info(f"📸 Screenshot: {output_path}")
                    return output_path
            except:
                continue

        return ""

    def get_health_status_text(self) -> str:
        """Get formatted health status"""
        if self.health_checker:
            return quick_health_check(self)
        return "Health checker not initialized"

    def __enter__(self):
        if not self.setup():
            raise RuntimeError("Setup failed")
        if not self.start():
            raise RuntimeError("Start failed")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def quick_start(ngrok_token: str, **kwargs) -> ColabDesktopImproved:
    """
    Quick start function - creates and starts desktop in one call

    Args:
        ngrok_token: Your ngrok auth token
        **kwargs: Additional arguments for ColabDesktopImproved

    Returns:
        Running ColabDesktopImproved instance
    """
    desktop = ColabDesktopImproved(ngrok_auth_token=ngrok_token, **kwargs)
    if not desktop.setup():
        raise RuntimeError("Setup failed - check logs")
    if not desktop.start():
        raise RuntimeError("Start failed - check logs")
    return desktop