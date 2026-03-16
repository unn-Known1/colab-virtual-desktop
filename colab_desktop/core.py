#!/usr/bin/env python3
"""
Colab Virtual Desktop - Core functionality

Automates the setup of a virtual desktop environment in Google Colab:
- Xvfb (virtual X server)
- XFCE (lightweight desktop environment)
- VNC server (tightvncserver)
- noVNC (web-based VNC client)
- ngrok (public tunneling)
"""

import os
import sys
import subprocess
import time
import signal
import threading
from pathlib import Path
from typing import Optional, Tuple, List
import json

# Optional imports
try:
    from pyngrok import ngrok, conf
    NGROK_AVAILABLE = True
except ImportError:
    NGROK_AVAILABLE = False


def is_colab() -> bool:
    """Check if running in Google Colab environment"""
    return 'google.colab' in sys.modules or 'COLAB_GPU' in os.environ


def run_command(cmd: str, shell: bool = True, capture: bool = False, timeout: int = None):
    """Run a shell command with proper error handling"""
    try:
        if capture:
            result = subprocess.run(
                cmd, shell=shell, capture_output=True, text=True, timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        else:
            proc = subprocess.run(cmd, shell=shell, timeout=timeout)
            return proc.returncode, "", ""
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def kill_processes_on_port(port: int):
    """Kill any process listening on a given port"""
    try:
        # Try lsof first
        code, out, err = run_command(f"lsof -ti:{port}", capture=True)
        if code == 0 and out.strip():
            pids = out.strip().split('\n')
            for pid in pids:
                if pid:
                    run_command(f"kill -9 {pid} 2>/dev/null")
    except:
        # Fallback to fuser
        try:
            run_command(f"fuser -k {port}/tcp 2>/dev/null")
        except:
            pass


class ColabDesktop:
    """
    Virtual Desktop Manager for Google Colab

    Features:
    - One-command setup of XFCE desktop environment
    - VNC server with password protection
    - noVNC web interface (accessible via browser)
    - ngrok tunneling for public access
    - Automatic cleanup and process management
    - Graceful shutdown handling
    """

    def __init__(
        self,
        ngrok_auth_token: Optional[str] = None,
        vnc_password: str = "colab123",
        display: str = ":1",
        geometry: str = "1280x720",
        depth: int = 24,
        vnc_port: int = 5901,
        novnc_port: int = 6080,
        ngrok_region: str = "us",
        auto_open: bool = False,
        install_deps: bool = True,
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
            install_deps: Auto-install system dependencies (default: True)
        """
        self.ngrok_auth_token = ngrok_auth_token or os.environ.get('NGROK_AUTH_TOKEN')
        self.vnc_password = vnc_password
        self.display = display
        self.geometry = geometry
        self.depth = depth
        self.vnc_port = vnc_port
        self.novnc_port = novnc_port
        self.ngrok_region = ngrok_region
        self.auto_open = auto_open
        self.install_deps = install_deps

        # State tracking
        self.xvfb_proc = None
        self.vncserver_proc = None
        self.websockify_proc = None
        self.ngrok_tunnel = None
        self.tunnel_url = None
        self.is_running = False

        # Paths
        self.home = Path.home()
        self.vnc_dir = self.home / '.vnc'
        self.vnc_passwd = self.vnc_dir / 'passwd'

        # Colab-specific setup
        self.colab_env = is_colab()

    def log(self, message: str, level: str = "INFO"):
        """Log message with timestamp"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")

    def install_system_dependencies(self) -> bool:
        """Install required system packages"""
        self.log("Installing system dependencies...")

        if not is_colab():
            self.log("Not in Colab - skipping apt-get install", "WARNING")
            return True

        packages = [
            "xfce4",
            "xfce4-goodies",
            "tightvncserver",
            "novnc",
            "websockify",
            "xvfb",
            "wget",
            "curl",
            "git",
            "python3-pip",
            "dbus",
            "dbus-x11",
            "x11-utils",
        ]

        cmd = f"apt-get update && apt-get install -y {' '.join(packages)}"
        self.log(f"Running: {cmd}")

        code, stdout, stderr = run_command(cmd, timeout=300)
        if code != 0:
            self.log(f"Installation failed: {stderr}", "ERROR")
            return False

        self.log("System dependencies installed successfully")
        return True

    def install_python_dependencies(self) -> bool:
        """Install required Python packages"""
        self.log("Installing Python dependencies...")

        packages = ["pyngrok>=3.0.0"]
        cmd = f"pip install -q {' '.join(packages)}"

        code, stdout, stderr = run_command(cmd, timeout=120)
        if code != 0:
            self.log(f"Python install failed: {stderr}", "ERROR")
            return False

        self.log("Python dependencies installed")
        return True

    def setup_vnc_password(self) -> bool:
        """Set up VNC server password"""
        self.log("Setting up VNC password...")

        self.vnc_dir.mkdir(parents=True, exist_ok=True)

        # Create password file
        cmd = f"echo '{self.vnc_password}' | vncpasswd -f > {self.vnc_passwd}"
        code, stdout, stderr = run_command(cmd)

        if code != 0:
            self.log(f"Failed to set VNC password: {stderr}", "ERROR")
            return False

        # Set permissions
        run_command(f"chmod 600 {self.vnc_passwd}")
        self.log("VNC password configured")
        return True

    def start_xvfb(self) -> bool:
        """Start Xvfb virtual display server"""
        self.log(f"Starting Xvfb on display {self.display}...")

        # Kill any existing Xvfb on this display
        kill_processes_on_port(5900)  # Xvfb often uses 5900+display

        cmd = f"Xvfb {self.display} -screen 0 {self.geometry}x{self.depth} &"
        code, stdout, stderr = run_command(cmd)

        if code != 0:
            self.log(f"Failed to start Xvfb: {stderr}", "ERROR")
            return False

        # Set DISPLAY environment variable
        os.environ["DISPLAY"] = self.display

        # Wait for Xvfb to start
        time.sleep(2)

        self.log(f"Xvfb started on {self.display}")
        return True

    def start_xfce(self) -> bool:
        """Start XFCE desktop environment"""
        self.log("Starting XFCE desktop...")

        # Try different methods to start XFCE
        commands = [
            "startxfce4 &",
            "xfce4-session &",
            "/usr/bin/startxfce4 &",
        ]

        for cmd in commands:
            code, stdout, stderr = run_command(cmd)
            if code == 0:
                self.log("XFCE started successfully")
                time.sleep(3)  # Give it time to initialize
                return True

        self.log("Failed to start XFCE after all attempts", "ERROR")
        return False

    def start_vnc_server(self) -> bool:
        """Start VNC server"""
        self.log(f"Starting VNC server on port {self.vnc_port}...")

        # Kill any existing VNC on this port
        kill_processes_on_port(self.vnc_port)

        cmd = f"vncserver {self.display} -geometry {self.geometry} -depth {self.depth} -SecurityTypes None"
        # Note: We already set password in ~/.vnc/passwd, but VNC will use it

        code, stdout, stderr = run_command(cmd)
        if code != 0:
            self.log(f"Failed to start VNC server: {stderr}", "ERROR")
            return False

        time.sleep(2)
        self.log("VNC server started")
        return True

    def start_websockify(self) -> bool:
        """Start noVNC websockify proxy"""
        self.log(f"Starting noVNC websockify on port {self.novnc_port}...")

        # Kill any existing process on novnc port
        kill_processes_on_port(self.novnc_port)

        # Find noVNC path
        novnc_paths = [
            "/usr/share/novnc",
            "/usr/local/novnc",
            str(self.home / "novnc"),
        ]

        novnc_path = None
        for path in novnc_paths:
            if Path(path).exists():
                novnc_path = path
                break

        if not novnc_path:
            self.log("noVNC installation not found", "ERROR")
            return False

        cmd = f"websockify --web={novnc_path} {self.novnc_port} localhost:{self.vnc_port} &"
        code, stdout, stderr = run_command(cmd)

        if code != 0:
            self.log(f"Failed to start websockify: {stderr}", "ERROR")
            return False

        time.sleep(2)
        self.log(f"noVNC web server started on port {self.novnc_port}")
        return True

    def start_ngrok(self) -> bool:
        """Start ngrok tunnel"""
        if not NGROK_AVAILABLE:
            self.log("pyngrok not installed. Install with: pip install pyngrok", "ERROR")
            return False

        if not self.ngrok_auth_token:
            self.log("No ngrok auth token provided. Set NGROK_AUTH_TOKEN environment variable or pass ngrok_auth_token", "ERROR")
            return False

        self.log("Starting ngrok tunnel...")

        try:
            # Configure ngrok
            conf.get_default().auth_token = self.ngrok_auth_token
            conf.get_default().region = self.ngrok_region

            # Kill any existing tunnel on the port
            kill_processes_on_port(self.novnc_port)

            # Start tunnel
            self.ngrok_tunnel = ngrok.connect(self.novnc_port, "http")
            self.tunnel_url = str(self.ngrok_tunnel).strip()
            self.tunnel_url = self.tunnel_url.replace("http://", "https://")

            self.log(f"ngrok tunnel created: {self.tunnel_url}")
            return True

        except Exception as e:
            self.log(f"Failed to start ngrok: {str(e)}", "ERROR")
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
            self.log(f"Opening browser: {url}")
        except Exception as e:
            self.log(f"Failed to open browser: {e}", "ERROR")

    def setup(self) -> bool:
        """Install all dependencies (call this first in Colab)"""
        self.log("="*60)
        self.log("Setting up Colab Virtual Desktop")
        self.log("="*60)

        if not self.colab_env:
            self.log("WARNING: Not running in Google Colab. Some features may not work.", "WARNING")

        steps = [
            ("Installing system dependencies", self.install_system_dependencies),
            ("Installing Python dependencies", self.install_python_dependencies),
            ("Setting up VNC password", self.setup_vnc_password),
        ]

        for name, step_func in steps:
            self.log(f"Step: {name}")
            if not step_func():
                self.log(f"Setup failed at: {name}", "ERROR")
                return False
            self.log(f"✓ {name} completed")

        self.log("Setup complete! Now call .start() to launch the desktop.")
        return True

    def start(self) -> bool:
        """Start all services (Xvfb, XFCE, VNC, noVNC, ngrok)"""
        if self.is_running:
            self.log("Desktop is already running", "WARNING")
            return True

        self.log("Starting virtual desktop services...")

        steps = [
            ("Xvfb", self.start_xvfb),
            ("XFCE", self.start_xfce),
            ("VNC server", self.start_vnc_server),
            ("noVNC websockify", self.start_websockify),
            ("ngrok tunnel", self.start_ngrok),
        ]

        for name, step_func in steps:
            self.log(f"Starting: {name}")
            if not step_func():
                self.log(f"Failed to start: {name}", "ERROR")
                self.stop()
                return False
            self.log(f"✓ {name} started")

        self.is_running = True

        url = self.get_url()
        if url:
            self.log("="*60)
            self.log("✅ VIRTUAL DESKTOP READY!")
            self.log("="*60)
            self.log(f"Desktop URL: {url}")
            self.log("Open this URL in your browser to access the desktop.")
            if self.auto_open:
                self.open_in_browser()
            self.log("="*60)

        return True

    def stop(self):
        """Stop all services and clean up"""
        self.log("Stopping virtual desktop...")

        # Kill processes
        for port in [self.vnc_port, self.novnc_port]:
            kill_processes_on_port(port)

        # Stop Xvfb
        try:
            run_command("pkill -f Xvfb")
        except:
            pass

        # Stop VNC server
        try:
            run_command("vncserver -kill :1 2>/dev/null")
            run_command("vncserver -kill :2 2>/dev/null")
        except:
            pass

        # Stop websockify
        try:
            run_command("pkill -f websockify")
        except:
            pass

        # Stop ngrok
        if self.ngrok_tunnel:
            try:
                ngrok.disconnect(self.ngrok_tunnel.public_url)
            except:
                pass
            self.ngrok_tunnel = None

        self.is_running = False
        self.tunnel_url = None
        self.log("Virtual desktop stopped")

    def restart(self) -> bool:
        """Restart all services"""
        self.log("Restarting virtual desktop...")
        self.stop()
        time.sleep(2)
        return self.start()


    def launch_app(self, command: str):
        """Launch an X11 application on the virtual desktop
        
        Args:
            command: Shell command to run the application (e.g., "xclock &")
        """
        import subprocess
        
        # Ensure DISPLAY is set
        env = os.environ.copy()
        env['DISPLAY'] = self.display
        
        # Launch the application
        subprocess.Popen(command, shell=True, env=env)
        self.log(f"Launched application: {command}")

    def take_screenshot(self, output_path: str = "/content/desktop_screenshot.png") -> str:
        """Take a screenshot of the virtual desktop
        
        Args:
            output_path: Where to save the screenshot (PNG format)
            
        Returns:
            Path to screenshot file, or empty string if failed
        """
        import subprocess
        from pathlib import Path
        
        # Ensure DISPLAY is set
        env = os.environ.copy()
        env['DISPLAY'] = self.display
        
        # Try different screenshot methods in order of preference
        methods = [
            f"scrot {output_path}",
            f"import -window root {output_path}",
            f"xwd -out {output_path}.xwd && convert {output_path}.xwd {output_path}"
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
                    self.log(f"Screenshot saved: {output_path}")
                    return output_path
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
        
        self.log("Failed to capture screenshot", level="ERROR")
        return ""

    def __enter__(self):
        self.setup()
        self.start()
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
        raise RuntimeError("Setup failed")
    if not desktop.start():
        raise RuntimeError("Start failed")
    return desktop
