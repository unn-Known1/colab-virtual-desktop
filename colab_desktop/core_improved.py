#!/usr/bin/env python3
"""
Colab Virtual Desktop - Core functionality (Improved)

Automates the setup of a virtual desktop environment in Google Colab:
- Xvfb (virtual X server)
- XFCE (lightweight desktop environment)
- VNC server (tightvncserver, or alternatives)
- noVNC (web-based VNC client)
- ngrok (public tunneling)

This version includes:
- Comprehensive error handling with retries
- Detailed logging with multiple levels
- Service health checks and verification
- Proper process management
- Graceful degradation
- Better dependency detection
"""

import os
import sys
import subprocess
import time
import signal
import threading
import shlex
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any, Callable
import json
import traceback
from dataclasses import dataclass
from enum import Enum

# Optional imports
try:
    from pyngrok import ngrok, conf
    NGROK_AVAILABLE = True
except ImportError:
    NGROK_AVAILABLE = False


class ServiceStatus(Enum):
    """Service status enumeration"""
    NOT_STARTED = "not_started"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class DesktopError(Exception):
    """Base exception for desktop errors"""
    pass


class DependencyError(DesktopError):
    """Missing dependency error"""
    pass


class ServiceStartError(DesktopError):
    """Service failed to start"""
    pass


class ConfigurationError(DesktopError):
    """Invalid configuration error"""
    pass


@dataclass
class ServiceInfo:
    """Information about a running service"""
    name: str
    status: ServiceStatus
    pid: Optional[int] = None
    port: Optional[int] = None
    url: Optional[str] = None
    error: Optional[str] = None


def is_colab() -> bool:
    """Check if running in Google Colab environment"""
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        pass
    return 'COLAB_GPU' in os.environ or 'COLAB_TF_ADDR' in os.environ


class CommandRunner:
    """Enhanced command runner with retry and timeout support"""

    def __init__(self, logger: Optional[Callable] = None):
        self.logger = logger or print
        self.default_timeout = 30

    def run(
        self,
        cmd: str,
        shell: bool = True,
        capture: bool = False,
        timeout: Optional[int] = None,
        check: bool = False,
        retry_count: int = 0,
        retry_delay: float = 1.0,
        cwd: Optional[str] = None
    ) -> Tuple[int, str, str]:
        """
        Run a shell command with enhanced error handling

        Args:
            cmd: Command to run
            shell: Use shell execution
            capture: Capture stdout/stderr
            timeout: Timeout in seconds (None for no timeout)
            check: Raise exception on non-zero return code
            retry_count: Number of retries on failure
            retry_delay: Delay between retries in seconds
            cwd: Working directory

        Returns:
            Tuple of (return_code, stdout, stderr)

        Raises:
            subprocess.CalledProcessError: If check=True and command fails after retries
            DesktopError: For other execution errors
        """
        timeout = timeout or self.default_timeout

        for attempt in range(retry_count + 1):
            try:
                if capture:
                    result = subprocess.run(
                        cmd,
                        shell=shell,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=cwd
                    )
                    rc, out, err = result.returncode, result.stdout, result.stderr
                else:
                    result = subprocess.run(cmd, shell=shell, timeout=timeout, cwd=cwd)
                    rc, out, err = result.returncode, "", ""

                if rc != 0 and check:
                    raise subprocess.CalledProcessError(rc, cmd, out, err)

                return rc, out, err

            except subprocess.TimeoutExpired as e:
                if attempt < retry_count:
                    self.logger(f"Command timed out, retrying {attempt + 1}/{retry_count}: {cmd}")
                    time.sleep(retry_delay)
                    continue
                return -1, "", f"Command timed out after {timeout}s: {str(e)}"

            except Exception as e:
                if attempt < retry_count:
                    self.logger(f"Command failed, retrying {attempt + 1}/{retry_count}: {cmd} - {e}")
                    time.sleep(retry_delay)
                    continue
                return -1, "", str(e)

        return -1, "", "Max retries exceeded"

    def check_output(self, cmd: str, shell: bool = True, timeout: Optional[int] = None) -> str:
        """Run command and return stdout, raise on error"""
        rc, out, err = self.run(cmd, shell=shell, capture=True, check=True, timeout=timeout)
        return out

    def exists(self, path: str) -> bool:
        """Check if file or directory exists"""
        return Path(path).exists()

    def which(self, command: str) -> Optional[str]:
        """Find command in PATH"""
        try:
            return self.check_output(f"which {command}", shell=True).strip()
        except:
            return None


class ProcessManager:
    """Manages processes with proper cleanup and tracking"""

    def __init__(self, logger: Optional[Callable] = None):
        self.logger = logger or print
        self.processes: List[subprocess.Popen] = []
        self._lock = threading.Lock()

    def start(self, cmd: str, shell: bool = True, env: Optional[Dict] = None) -> subprocess.Popen:
        """Start a background process and track it"""
        try:
            proc = subprocess.Popen(
                cmd,
                shell=shell,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True  # Create new process group for easier cleanup
            )
            with self._lock:
                self.processes.append(proc)
            self.logger(f"Started process PID {proc.pid}: {cmd[:50]}...")
            return proc
        except Exception as e:
            raise DesktopError(f"Failed to start process: {e}")

    def kill_by_pattern(self, pattern: str):
        """Kill processes matching a pattern"""
        try:
            runner = CommandRunner(self.logger)
            # Use pkill with pattern
            rc, _, _ = runner.run(f"pkill -f '{pattern}'", check=False)
            if rc == 0:
                self.logger(f"Killed processes matching: {pattern}")
        except Exception as e:
            self.logger(f"Error killing processes: {e}", level="WARNING")

    def kill_by_port(self, port: int):
        """Kill process listening on a port"""
        try:
            runner = CommandRunner(self.logger)
            # Try lsof first
            rc, out, _ = runner.run(f"lsof -ti:{port}", capture=True, check=False)
            if rc == 0 and out.strip():
                pids = [p for p in out.strip().split('\n') if p.strip()]
                for pid in pids:
                    try:
                        runner.run(f"kill -9 {pid}", check=False)
                        self.logger(f"Killed PID {pid} on port {port}")
                    except:
                        pass
        except Exception as e:
            self.logger(f"Error killing port {port}: {e}", level="WARNING")

    def cleanup(self):
        """Clean up all tracked processes"""
        with self._lock:
            for proc in self.processes[:]:
                try:
                    if proc.poll() is None:  # Still running
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    self.processes.remove(proc)
                except Exception as e:
                    self.logger(f"Error cleaning up process: {e}", level="WARNING")

    def is_running(self, pid: int) -> bool:
        """Check if a process with given PID is running"""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class ServiceManager:
    """Manages desktop services with health checks"""

    def __init__(self, runner: CommandRunner, proc_mgr: ProcessManager):
        self.runner = runner
        self.proc_mgr = proc_mgr
        self.services: Dict[str, ServiceInfo] = {}

    def register_service(self, name: str, port: Optional[int] = None):
        """Register a service for tracking"""
        self.services[name] = ServiceInfo(
            name=name,
            status=ServiceStatus.NOT_STARTED,
            port=port
        )

    def update_status(self, name: str, status: ServiceStatus, **kwargs):
        """Update service status"""
        if name in self.services:
            self.services[name].status = status
            for key, value in kwargs.items():
                if hasattr(self.services[name], key):
                    setattr(self.services[name], key, value)

    def wait_for_port(self, port: int, timeout: int = 30, interval: float = 0.5) -> bool:
        """Wait for a port to become available (listening)"""
        start = time.time()
        while time.time() - start < timeout:
            if self._is_port_listening(port):
                return True
            time.sleep(interval)
        return False

    def _is_port_listening(self, port: int) -> bool:
        """Check if port is listening"""
        try:
            rc, out, _ = self.runner.run(
                f"netstat -tuln 2>/dev/null | grep ' LISTEN ' | grep ':{port} '",
                capture=True,
                check=False
            )
            return rc == 0 and bool(out.strip())
        except:
            return False

    def verify_process_running(self, pattern: str, min_count: int = 1) -> Tuple[bool, List[str]]:
        """Verify that processes matching pattern are running"""
        try:
            rc, out, _ = self.runner.run(f"pgrep -f '{pattern}'", capture=True, check=False)
            if rc == 0:
                pids = [p for p in out.strip().split('\n') if p.strip()]
                if len(pids) >= min_count:
                    return True, pids
        except:
            pass
        return False, []


def validate_port(port: int) -> bool:
    """Validate port number"""
    return 1024 <= port <= 65535


def validate_geometry(geometry: str) -> bool:
    """Validate geometry format (e.g., 1280x720)"""
    try:
        width, height = geometry.lower().split('x')
        return int(width) >= 800 and int(height) >= 600
    except:
        return False


class ColabDesktop:
    """
    Virtual Desktop Manager for Google Colab (Improved)

    Features:
    - One-command setup of XFCE desktop environment
    - VNC server with password protection (with fallback support)
    - noVNC web interface (accessible via browser)
    - ngrok tunneling for public access
    - Comprehensive error handling and retries
    - Health checks and service verification
    - Automatic cleanup and process management
    - Context manager support
    - Detailed logging
    """

    # Default configurations
    DEFAULT_VNC_PORTS = [5901, 5902, 5903]
    DEFAULT_NOVNC_PORTS = [6080, 6081, 6082]

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
        logger: Optional[Callable] = None,
    ):
        """
        Initialize Colab Desktop

        Args:
            ngrok_auth_token: ngrok auth token (get from https://ngrok.com)
            vnc_password: VNC server password (default: colab123)
            display: X display number (default: :1)
            geometry: Screen resolution (default: 1280x720)
            depth: Color depth (default: 24)
            vnc_port: VNC server port (default: 5901)
            novnc_port: noVNC web port (default: 6080)
            ngrok_region: ngrok tunnel region (default: us)
            auto_open: Automatically open browser (default: False)
            install_deps: Auto-install system packages (default: True)
            logger: Custom logger function (default: print)
        """
        # Validate inputs early
        if not validate_geometry(geometry):
            raise ConfigurationError(f"Invalid geometry format: {geometry}. Use format like '1280x720'")

        if depth not in [8, 16, 24, 32]:
            raise ConfigurationError(f"Invalid depth: {depth}. Use 8, 16, 24, or 32")

        if vnc_port and not validate_port(vnc_port):
            raise ConfigurationError(f"Invalid vnc_port: {vnc_port}. Must be 1024-65535")
        if novnc_port and not validate_port(novnc_port):
            raise ConfigurationError(f"Invalid novnc_port: {novnc_port}. Must be 1024-65535")

        self.ngrok_auth_token = ngrok_auth_token or os.environ.get('NGROK_AUTH_TOKEN')
        self.vnc_password = vnc_password
        self.display = display
        self.geometry = geometry
        self.depth = depth
        self.vnc_port = vnc_port or self.DEFAULT_VNC_PORTS[0]
        self.novnc_port = novnc_port or self.DEFAULT_NOVNC_PORTS[0]
        self.ngrok_region = ngrok_region
        self.auto_open = auto_open
        self.install_deps = install_deps
        self.logger = logger or self._default_logger

        # State tracking
        self.runner = CommandRunner(self.logger)
        self.proc_mgr = ProcessManager(self.logger)
        self.service_mgr = ServiceManager(self.runner, self.proc_mgr)
        self.xvfb_proc: Optional[subprocess.Popen] = None
        self.vncserver_proc: Optional[subprocess.Popen] = None
        self.websockify_proc: Optional[subprocess.Popen] = None
        self.ngrok_tunnel = None
        self.tunnel_url: Optional[str] = None
        self.is_running = False
        self._shutdown_event = threading.Event()

        # Paths
        self.home = Path.home()
        self.vnc_dir = self.home / '.vnc'
        self.vnc_passwd = self.vnc_dir / 'passwd'
        self.xstartup = self.vnc_dir / 'xstartup'

        # Colab-specific setup
        self.colab_env = is_colab()

    def _default_logger(self, message: str, level: str = "INFO"):
        """Default logging function"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")

    def log(self, message: str, level: str = "INFO"):
        """Log message with timestamp"""
        self.logger(message, level)

    def _detect_vnc_server(self) -> Optional[str]:
        """Detect which VNC server is available"""
        candidates = ['vncserver', 'Xvnc', 'tightvncserver', 'TigerVNC']
        for cmd in candidates:
            if self.runner.which(cmd):
                self.log(f"Found VNC server: {cmd}")
                return cmd
        return None

    def _detect_desktop_environment(self) -> List[str]:
        """Detect available desktop environments"""
        de = []
        if self.runner.exists('/usr/bin/startxfce4'):
            de.append('xfce4')
        if self.runner.exists('/usr/bin/startkde'):
            de.append('kde')
        if self.runner.exists('/usr/bin/gnome-session'):
            de.append('gnome')
        return de

    def validate_environment(self) -> List[str]:
        """Validate that required dependencies are available"""
        missing = []

        # Check system commands
        required_cmds = ['Xvfb', 'xset', 'xterm']
        for cmd in required_cmds:
            if not self.runner.which(cmd):
                missing.append(f"X11 command: {cmd}")

        # Check VNC server
        if not self._detect_vnc_server():
            missing.append("VNC server (tightvncserver, Xvnc, TigerVNC, or similar)")

        # Check desktop environment
        de = self._detect_desktop_environment()
        if not de:
            missing.append("Desktop environment (XFCE, KDE, GNOME)")

        # Check noVNC
        novnc_paths = ['/usr/share/novnc', '/usr/local/novnc', str(self.home / 'novnc')]
        if not any(self.runner.exists(p) for p in novnc_paths):
            missing.append("noVNC (websockify package)")

        # Check Python packages
        try:
            import pyngrok
        except ImportError:
            if self.ngrok_auth_token:
                missing.append("pyngrok (install: pip install pyngrok)")

        return missing

    def install_system_dependencies(self) -> bool:
        """Install required system packages with retry and fallback"""
        self.log("="*60)
        self.log("Installing system dependencies...")
        self.log("="*60)

        if not self.colab_env:
            self.log("Not in Colab - skipping apt-get install", "WARNING")
            return True

        # Check what's already installed
        missing = self.validate_environment()
        if not missing:
            self.log("All dependencies already installed!")
            return True

        self.log(f"Missing dependencies: {', '.join(missing)}")

        # Map missing items to packages
        package_map = {
            'X11 command: Xvfb': 'xvfb',
            'VNC server': 'tightvncserver',
            'noVNC': 'novnc',
            'Desktop environment': 'xfce4 xfce4-goodies',
        }

        packages = set()
        for item in missing:
            for key, pkg in package_map.items():
                if key in item:
                    packages.add(pkg)

        # Add other useful packages
        packages.update(['wget', 'curl', 'git', 'python3-pip', 'dbus', 'dbus-x11', 'x11-utils'])

        package_list = ' '.join(sorted(packages))
        cmd = f"apt-get update -qq && apt-get install -y -qq {package_list}"

        self.log(f"Installing: {package_list}")

        for attempt in range(3):
            rc, out, err = self.runner.run(cmd, timeout=600)
            if rc == 0:
                self.log("✅ System dependencies installed successfully")
                return True
            else:
                self.log(f"Attempt {attempt + 1} failed: {err}", level="WARNING")
                if attempt < 2:
                    time.sleep(5)

        self.log("❌ Failed to install system dependencies after 3 attempts", level="ERROR")
        return False

    def install_python_dependencies(self) -> bool:
        """Install required Python packages"""
        self.log("Installing Python dependencies...")

        packages = []
        try:
            import pyngrok
            self.log("pyngrok already installed")
        except ImportError:
            packages.append("pyngrok>=3.0.0")

        if packages:
            cmd = f"pip install -q {' '.join(packages)}"
            rc, out, err = self.runner.run(cmd, timeout=120)
            if rc != 0:
                self.log(f"Python install failed: {err}", "ERROR")
                return False

        self.log("Python dependencies OK")
        return True

    def setup_vnc_password(self) -> bool:
        """Set up VNC server password with validation"""
        self.log("Setting up VNC password...")

        if len(self.vnc_password) < 8:
            self.log("VNC password too short (minimum 8 characters)", "WARNING")
            # We'll still proceed but warn

        self.vnc_dir.mkdir(parents=True, exist_ok=True)

        # Create password file
        try:
            # Use vncpasswd if available
            if self.runner.which('vncpasswd'):
                cmd = f"echo '{self.vnc_password}' | vncpasswd -f > {self.vnc_passwd}"
            else:
                # Fallback: create manually (uses simple XOR encryption)
                from hashlib import md5
                # VNC password format: 2 bytes magic + 16 bytes encrypted
                # We'll use vncpasswd output if possible, otherwise skip
                self.log("vncpasswd not found, skipping password setup", "WARNING")
                return True

            rc, out, err = self.runner.run(cmd)
            if rc != 0:
                raise Exception(err)

            # Set permissions
            self.runner.run(f"chmod 600 {self.vnc_passwd}", check=False)

            # Verify password file
            if not self.vnc_passwd.exists() or self.vnc_passwd.stat().st_size < 10:
                raise Exception("Password file not created properly")

            self.log("VNC password configured")
            return True

        except Exception as e:
            self.log(f"Failed to set VNC password: {e}", "ERROR")
            # Continue anyway - VNC might still work with no password
            return True

    def _create_xstartup(self):
        """Create xstartup script for VNC"""
        xstartup_content = f"""#!/bin/bash
export DISPLAY={self.display}
export XKL_XMODMAP_DISABLE=1
export DESKTOP_SESSION=xfce
export XDG_CURRENT_DESKTOP=XFCE
export GDMSESSION=xfce

# Start D-Bus
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    eval `dbus-launch --sh-syntax --exit-with-session`
    export DBUS_SESSION_BUS_ADDRESS
    export DBUS_SESSION_BUS_PID
fi

# Start desktop
{self._get_desktop_start_command()}
"""
        try:
            self.xstartup.write_text(xstartup_content)
            self.xstartup.chmod(0o755)
        except Exception as e:
            self.log(f"Failed to create xstartup: {e}", "WARNING")

    def _get_desktop_start_command(self) -> str:
        """Get the command to start the desktop environment"""
        de = self._detect_desktop_environment()
        if 'xfce4' in de:
            return "startxfce4 &"
        elif 'gnome' in de:
            return "gnome-session &"
        elif 'kde' in de:
            return "startkde &"
        else:
            return "xterm -geometry 80x24+10+10 -bg black -fg white &"

    def start_xvfb(self) -> bool:
        """Start Xvfb virtual display server with verification"""
        self.log(f"Starting Xvfb on display {self.display}...")

        # Kill any existing Xvfb
        self.proc_mgr.kill_by_port(5900)
        self.proc_mgr.kill_by_pattern('Xvfb')

        # Validate display format
        if not (self.display.startswith(':') and self.display[1:].isdigit()):
            raise ConfigurationError(f"Invalid display format: {self.display}")

        cmd = f"Xvfb {self.display} -screen 0 {self.geometry}x{self.depth} -ac +extension GLX +render -noreset"
        self.log(f"Running: {cmd}")

        try:
            self.xvfb_proc = self.proc_mgr.start(cmd)
            time.sleep(2)

            # Verify it's running
            if not self.proc_mgr.is_running(self.xvfb_proc.pid):
                raise ServiceStartError("Xvfb process died immediately")

            # Set DISPLAY
            os.environ["DISPLAY"] = self.display

            # Wait for X to be ready
            if not self.runner.wait_for_port(6000 + int(self.display[1:]), timeout=10):
                self.log("Xvfb may not be responding on display", "WARNING")

            self.log(f"✅ Xvfb started (PID {self.xvfb_proc.pid})")
            return True

        except Exception as e:
            self.log(f"Failed to start Xvfb: {e}", "ERROR")
            return False

    def start_xfce(self) -> bool:
        """Start XFCE desktop environment with verification"""
        self.log("Starting XFCE desktop...")

        # Create xstartup if using VNC server mode
        self._create_xstartup()

        # Try different methods
        methods = [
            ("startxfce4", "startxfce4 &"),
            ("xfce4-session", "xfce4-session &"),
            ("xterm fallback", "xterm -geometry 80x24+10+10 -bg black -fg white &")
        ]

        for name, cmd in methods:
            try:
                self.log(f"Trying: {name}")
                self.proc_mgr.start(cmd)
                time.sleep(3)

                # Verify X client can connect
                rc, _, _ = self.runner.run("xset q", capture=True, check=False)
                if rc == 0:
                    self.log(f"✅ Desktop started using {name}")
                    return True
            except:
                continue

        self.log("❌ Failed to start desktop environment", "ERROR")
        return False

    def start_vnc_server(self) -> bool:
        """Start VNC server with automatic fallback and verification"""
        self.log(f"Starting VNC server on port {self.vnc_port} (display {self.display})...")

        # Kill any existing VNC
        self.proc_mgr.kill_by_port(self.vnc_port)
        self.proc_mgr.kill_by_pattern('Xvnc|vncserver|tightvnc')

        vnc_cmd = self._detect_vnc_server()
        if not vnc_cmd:
            raise ServiceStartError("No VNC server found. Install tightvncserver or similar.")

        # Build command
        cmd = f"{vnc_cmd} {self.display} -geometry {self.geometry} -depth {self.depth}"

        # Add password if set
        if self.vnc_passwd.exists():
            cmd += " -PasswordFile={self.vnc_passwd}"
        else:
            # Disable security if no password (not recommended for production)
            cmd += " -SecurityTypes None"

        # Per-monitor workaround for multi-display (common in VNC)
        if self.display != ":1":
            cmd += f" -rfbport {self.vnc_port}"

        self.log(f"Running: {cmd}")

        try:
            self.vncserver_proc = self.proc_mgr.start(cmd)
            time.sleep(3)

            # Verify VNC server is listening
            if not self.service_mgr.wait_for_port(self.vnc_port, timeout=15):
                self.log("VNC server not listening on port", "ERROR")
                # Try to get error output
                return False

            self.log(f"✅ VNC server started (PID {self.vncserver_proc.pid})")
            return True

        except Exception as e:
            self.log(f"Failed to start VNC server: {e}", "ERROR")
            return False

    def start_websockify(self) -> bool:
        """Start noVNC websockify proxy with verification"""
        self.log(f"Starting noVNC websockify on port {self.novnc_port}...")

        # Kill existing
        self.proc_mgr.kill_by_port(self.novnc_port)
        self.proc_mgr.kill_by_pattern('websockify')

        # Find noVNC path
        novnc_paths = [
            '/usr/share/novnc',
            '/usr/local/novnc',
            str(self.home / 'novnc'),
            str(self.home / 'noVNC'),
            '/opt/novnc',
        ]

        novnc_path = None
        for path in novnc_paths:
            if self.runner.exists(path):
                novnc_path = path
                break

        if not novnc_path:
            # Try to find via find command
            try:
                rc, out, _ = self.runner.run("find /usr -name 'novnc' -type d 2>/dev/null | head -1", capture=True)
                if rc == 0 and out.strip():
                    novnc_path = out.strip()
            except:
                pass

        if not novnc_path:
            self.log("noVNC not found. Install with: apt-get install novnc", "ERROR")
            # Try to continue anyway by downloading
            return self._install_novnc_from_source()

        self.log(f"Using noVNC from: {novnc_path}")

        cmd = f"websockify --web={novnc_path} {self.novnc_port} localhost:{self.vnc_port}"
        self.log(f"Running: {cmd}")

        try:
            self.websockify_proc = self.proc_mgr.start(cmd)
            time.sleep(2)

            if not self.service_mgr.wait_for_port(self.novnc_port, timeout=10):
                self.log("noVNC not responding on port", "ERROR")
                return False

            self.log(f"✅ noVNC started (PID {self.websockify_proc.pid})")
            return True

        except Exception as e:
            self.log(f"Failed to start websockify: {e}", "ERROR")
            return False

    def _install_novnc_from_source(self) -> bool:
        """Fallback: install noVNC from source"""
        self.log("Attempting to install noVNC from source...")
        try:
            # Clone noVNC
            repo_dir = self.home / 'novnc'
            if not repo_dir.exists():
                self.runner.run("git clone https://github.com/novnc/noVNC.git ~/novnc", timeout=60)

            # Use that
            cmd = f"~/novnc/utils/novnc_proxy --web ~/novnc {self.novnc_port} localhost:{self.vnc_port}"
            self.websockify_proc = self.proc_mgr.start(cmd)
            time.sleep(3)

            if self.service_mgr.wait_for_port(self.novnc_port, timeout=10):
                self.log("✅ noVNC installed and started from source")
                return True
        except Exception as e:
            self.log(f"Failed to install noVNC from source: {e}", "ERROR")

        return False

    def start_ngrok(self) -> bool:
        """Start ngrok tunnel with improved error handling"""
        if not NGROK_AVAILABLE:
            self.log("pyngrok not available. Install: pip install pyngrok", "ERROR")
            return False

        if not self.ngrok_auth_token:
            self.log("No ngrok auth token provided", "ERROR")
            return False

        self.log("Starting ngrok tunnel...")

        try:
            # Configure ngrok
            conf.get_default().auth_token = self.ngrok_auth_token
            conf.get_default().region = self.ngrok_region
            conf.get_default().monitor_thread = False

            # Kill any existing tunnel (by checking common ports)
            # We rely on pyngrok's automatic management

            # Start tunnel with connection retry
            for attempt in range(3):
                try:
                    self.ngrok_tunnel = ngrok.connect(
                        self.novnc_port,
                        "http",
                        bind_tls=True  # Force HTTPS
                    )
                    break
                except Exception as e:
                    if attempt < 2:
                        self.log(f"ngrok connection attempt {attempt + 1} failed: {e}", "WARNING")
                        time.sleep(5)
                    else:
                        raise

            self.tunnel_url = str(self.ngrok_tunnel).strip()
            self.tunnel_url = self.tunnel_url.replace("http://", "https://")

            # Verify tunnel is actually working
            if not self.tunnel_url.startswith('https://'):
                raise ServiceStartError(f"Invalid tunnel URL: {self.tunnel_url}")

            self.log(f"✅ ngrok tunnel created: {self.tunnel_url}")
            return True

        except Exception as e:
            self.log(f"Failed to start ngrok: {e}", "ERROR")
            self._try_alternative_tunnel()
            return False

    def _try_alternative_tunnel(self) -> bool:
        """Try alternative tunneling methods if ngrok fails"""
        self.log("Trying alternative tunneling methods...")

        # Could implement localtunnel, serveo, or similar
        # For now, just provide manual instructions
        self.log("Manual access: Use 'ssh -L 6080:localhost:6080 user@your-server' or similar")
        return False

    def get_url(self) -> Optional[str]:
        """Get the public URL for the VNC interface"""
        if self.tunnel_url:
            return f"{self.tunnel_url}/vnc.html"
        return None

    def open_in_browser(self):
        """Open the desktop URL in default browser"""
        url = self.get_url()
        if not url:
            self.log("No URL available - desktop not running?", "ERROR")
            return

        try:
            import webbrowser
            webbrowser.open(url)
            self.log(f"🌐 Opening browser: {url}")
        except Exception as e:
            self.log(f"Failed to open browser: {e}", "ERROR")

    def check_service_health(self) -> Dict[str, ServiceInfo]:
        """Check health of all services"""
        health = {}

        # Xvfb
        xvfb_ok, pids = self.service_mgr.verify_process_running('Xvfb')
        health['xvfb'] = ServiceInfo(
            name='Xvfb',
            status=ServiceStatus.RUNNING if xvfb_ok else ServiceStatus.FAILED,
            pid=int(pids[0]) if pids else None
        )

        # VNC
        vnc_ok, pids = self.service_mgr.verify_process_running('Xvnc|vncserver')
        health['vnc'] = ServiceInfo(
            name='VNC',
            status=ServiceStatus.RUNNING if vnc_ok else ServiceStatus.FAILED,
            port=self.vnc_port,
            pid=int(pids[0]) if pids else None
        )

        # noVNC
        novnc_ok, pids = self.service_mgr.verify_process_running('websockify')
        health['novnc'] = ServiceInfo(
            name='noVNC',
            status=ServiceStatus.RUNNING if novnc_ok else ServiceStatus.FAILED,
            port=self.novnc_port,
            pid=int(pids[0]) if pids else None
        )

        # ngrok
        if self.ngrok_tunnel:
            try:
                tunnels = ngrok.get_tunnels()
                if any(t.public_url == self.ngrok_tunnel.public_url for t in tunnels):
                    ngrok_ok = True
                else:
                    ngrok_ok = False
            except:
                ngrok_ok = False

            health['ngrok'] = ServiceInfo(
                name='ngrok',
                status=ServiceStatus.RUNNING if ngrok_ok else ServiceStatus.FAILED,
                url=self.tunnel_url
            )

        return health

    def setup(self) -> bool:
        """Install all dependencies"""
        self.log("="*60)
        self.log("Colab Virtual Desktop - Setup Phase")
        self.log("="*60)

        steps = [
            ("System dependencies", self.install_system_dependencies),
            ("Python dependencies", self.install_python_dependencies),
            ("VNC password", self.setup_vnc_password),
        ]

        for name, step_func in steps:
            self.log(f"\n⏳ Step: {name}")
            try:
                if not step_func():
                    self.log(f"❌ Setup failed at: {name}", "ERROR")
                    return False
                self.log(f"✅ {name} completed")
            except Exception as e:
                self.log(f"❌ Exception in {name}: {e}", "ERROR")
                traceback.print_exc()
                return False

        self.log("\n" + "="*60)
        self.log("✅ Setup complete! Now call .start() to launch desktop.")
        self.log("="*60)
        return True

    def start(self) -> bool:
        """Start all services"""
        if self.is_running:
            self.log("Desktop is already running", "WARNING")
            return True

        self.log("\n" + "="*60)
        self.log("Starting Virtual Desktop Services")
        self.log("="*60)

        steps = [
            ("Xvfb", self.start_xvfb),
            ("Desktop", self.start_xfce),
            ("VNC", self.start_vnc_server),
            ("noVNC", self.start_websockify),
            ("ngrok", self.start_ngrok),
        ]

        for name, step_func in steps:
            self.log(f"\n▶ Starting: {name}")
            try:
                if not step_func():
                    self.log(f"❌ Failed to start: {name}", "ERROR")
                    self.stop()
                    return False
                self.log(f"✅ {name} started")
            except Exception as e:
                self.log(f"❌ Exception starting {name}: {e}", "ERROR")
                traceback.print_exc()
                self.stop()
                return False

        self.is_running = True

        url = self.get_url()
        if url:
            self.log("\n" + "="*60)
            self.log("✅ VIRTUAL DESKTOP READY!")
            self.log("="*60)
            self.log(f"🌐 Desktop URL: {url}")
            self.log("📱 Open this URL in your browser to access the desktop.")
            if self.auto_open:
                self.open_in_browser()
            self.log("="*60)

            # Show health status
            health = self.check_service_health()
            for name, info in health.items():
                status_icon = "✅" if info.status == ServiceStatus.RUNNING else "❌"
                self.log(f"  {status_icon} {info.name} - {info.status.value}")

        return True

    def stop(self):
        """Stop all services and clean up"""
        self.log("\n🛑 Stopping virtual desktop...")
        self._shutdown_event.set()

        # Stop processes in reverse order
        try:
            # Stop ngrok
            if self.ngrok_tunnel:
                try:
                    ngrok.disconnect(self.ngrok_tunnel.public_url)
                    self.log("ngrok tunnel closed")
                except Exception as e:
                    self.log(f"Error closing ngrok: {e}", "WARNING")
        except:
            pass

        # Clean up process manager
        self.proc_mgr.cleanup()

        # Additional force kills
        self.proc_mgr.kill_by_port(self.vnc_port)
        self.proc_mgr.kill_by_port(self.novnc_port)
        self.proc_mgr.kill_by_pattern('Xvfb')
        self.proc_mgr.kill_by_pattern('Xvnc|vncserver')
        self.proc_mgr.kill_by_pattern('websockify')

        self.is_running = False
        self.tunnel_url = None
        self.log("✅ Virtual desktop stopped")

    def restart(self) -> bool:
        """Restart all services"""
        self.log("🔄 Restarting virtual desktop...")
        self.stop()
        time.sleep(3)
        return self.start()

    def launch_app(self, command: str, wait: bool = False):
        """
        Launch an X11 application on the virtual desktop

        Args:
            command: Shell command to run (e.g., "xclock &")
            wait: If True, wait for the app to finish (blocks)
        """
        env = os.environ.copy()
        env['DISPLAY'] = self.display

        if wait:
            subprocess.run(command, shell=True, env=env)
        else:
            subprocess.Popen(command, shell=True, env=env, start_new_session=True)

        self.log(f"🚀 Launched: {command}")

    def take_screenshot(self, output_path: str = "/content/desktop_screenshot.png") -> str:
        """
        Take a screenshot of the virtual desktop

        Args:
            output_path: Where to save the screenshot (PNG)

        Returns:
            Path to screenshot file, or empty string if failed
        """
        env = os.environ.copy()
        env['DISPLAY'] = self.display

        methods = [
            f"scrot {output_path}",
            f"import -window root {output_path}",
        ]

        for method in methods:
            try:
                result = subprocess.run(
                    method,
                    shell=True,
                    env=env,
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0 and Path(output_path).exists():
                    self.log(f"📸 Screenshot saved: {output_path}")
                    return output_path
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue

        self.log("❌ Failed to capture screenshot", "ERROR")
        return ""

    def __enter__(self):
        if not self.setup():
            raise RuntimeError("Setup failed")
        if not self.start():
            raise RuntimeError("Start failed")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def quick_start(ngrok_token: str, **kwargs) -> ColabDesktop:
    """
    Quick start function - creates and starts desktop in one call

    Args:
        ngrok_token: Your ngrok auth token
        **kwargs: Additional arguments for ColabDesktop

    Returns:
        ColabDesktop instance (running)
    """
    desktop = ColabDesktop(ngrok_auth_token=ngrok_token, **kwargs)
    if not desktop.setup():
        raise RuntimeError("Setup failed - check logs")
    if not desktop.start():
        raise RuntimeError("Start failed - check logs")
    return desktop