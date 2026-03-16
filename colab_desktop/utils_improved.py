"""
Utility functions for Colab Virtual Desktop (Improved)

Includes environment detection, command execution, port management,
and other helper functions with better error handling.
"""

import os
import sys
import subprocess
import socket
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import time
import platform


def is_colab() -> bool:
    """
    Detect if running in Google Colab environment

    Returns:
        True if running in Colab, False otherwise
    """
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        pass

    # Check environment variables
    return any(var in os.environ for var in [
        'COLAB_GPU',
        'COLAB_TPU_ADDR',
        'COLAB_TF_ADDR',
        'COLAB_RELEASE_TAG'
    ])


def is_linux() -> bool:
    """Check if OS is Linux"""
    return sys.platform.startswith('linux')


def is_macos() -> bool:
    """Check if OS is macOS"""
    return sys.platform == 'darwin'


def is_windows() -> bool:
    """Check if OS is Windows"""
    return sys.platform == 'win32' or sys.platform == 'cygwin'


class CommandRunner:
    """Enhanced command runner with consistent interface"""

    def __init__(self, logger: Optional[callable] = None):
        self.logger = logger or (lambda msg, level="INFO": print(f"[{level}] {msg}"))

    def run(
        self,
        cmd: str,
        shell: bool = True,
        capture: bool = False,
        timeout: Optional[int] = None,
        check: bool = False,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> Tuple[int, str, str]:
        """
        Run a shell command with proper error handling

        Args:
            cmd: Command to run
            shell: Use shell execution
            capture: Capture stdout/stderr
            timeout: Timeout in seconds (None for no timeout)
            check: Raise CalledProcessError on non-zero return code
            cwd: Working directory
            env: Environment variables (additive to current)

        Returns:
            Tuple of (return_code, stdout, stderr)

        Raises:
            subprocess.CalledProcessError: If check=True and command fails
        """
        try:
            if capture:
                result = subprocess.run(
                    cmd,
                    shell=shell,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                    env=env
                )
                rc, out, err = result.returncode, result.stdout, result.stderr
            else:
                result = subprocess.run(
                    cmd,
                    shell=shell,
                    timeout=timeout,
                    cwd=cwd,
                    env=env
                )
                rc, out, err = result.returncode, "", ""

            if check and rc != 0:
                raise subprocess.CalledProcessError(rc, cmd, out, err)

            return rc, out, err

        except subprocess.TimeoutExpired as e:
            self.logger(f"Command timed out: {cmd}", "WARNING")
            return -1, "", str(e)
        except Exception as e:
            self.logger(f"Command failed: {cmd} - {e}", "ERROR")
            return -1, "", str(e)

    def check_output(self, cmd: str, **kwargs) -> str:
        """Run command and return stdout, raise on error"""
        rc, out, err = self.run(cmd, capture=True, check=True, **kwargs)
        return out.strip()

    def exists(self, path: str) -> bool:
        """Check if file or directory exists"""
        return Path(path).exists()

    def which(self, command: str) -> Optional[str]:
        """Find command in PATH"""
        try:
            return self.check_output(f"which {command}")
        except:
            return None

    def which_any(self, commands: List[str]) -> Optional[str]:
        """Find first available command from list"""
        for cmd in commands:
            path = self.which(cmd)
            if path:
                return path
        return None


def check_port_in_use(port: int, host: str = 'localhost') -> bool:
    """
    Check if a port is in use

    Args:
        port: Port to check
        host: Host to check (default: localhost)

    Returns:
        True if port is in use, False otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
    except:
        return False


def kill_process_on_port(port: int, sudo: bool = False) -> bool:
    """
    Kill process listening on a specific port

    Args:
        port: Port number
        sudo: Use sudo (if needed)

    Returns:
        True if process was killed, False otherwise
    """
    runner = CommandRunner()

    # Method 1: lsof
    try:
        rc, out, _ = runner.run(f"lsof -ti:{port}", capture=True, check=False)
        if rc == 0 and out.strip():
            pids = [p.strip() for p in out.strip().split('\n') if p.strip()]
            for pid in pids:
                try:
                    runner.run(f"kill -9 {pid}", check=False)
                    runner.logger(f"Killed PID {pid} on port {port}")
                except:
                    pass
            return True
    except:
        pass

    # Method 2: fuser
    try:
        runner.run(f"fuser -k {port}/tcp", check=False)
        return True
    except:
        pass

    # Method 3: pkill by pattern
    patterns = {
        5900: "Xvfb.*:1",  # Xvfb on display :1
        5901: "Xvnc.*:1|vncserver.*:1",
        5902: "Xvnc.*:2|vncserver.*:2",
        6080: "websockify.*6080",
        6081: "websockify.*6081",
    }

    if port in patterns:
        try:
            runner.run(f"pkill -f '{patterns[port]}'", check=False)
            return True
        except:
            pass

    return False


def wait_for_port(
    port: int,
    host: str = 'localhost',
    timeout: int = 30,
    interval: float = 0.5,
    expected_state: str = 'open'
) -> bool:
    """
    Wait for a port to reach a specific state

    Args:
        port: Port to wait for
        host: Host to check
        timeout: Maximum wait time in seconds
        interval: Check interval in seconds
        expected_state: 'open' to wait for port to open, 'closed' to wait for close

    Returns:
        True if port reached expected state, False if timeout
    """
    import time
    start = time.time()

    while time.time() - start < timeout:
        in_use = check_port_in_use(port, host)
        if expected_state == 'open' and in_use:
            return True
        elif expected_state == 'closed' and not in_use:
            return True
        time.sleep(interval)

    return False


def get_process_pids(pattern: str) -> List[int]:
    """
    Get PIDs of processes matching a pattern

    Args:
        pattern: Pattern to match (used with pgrep -f)

    Returns:
        List of PIDs (empty if none found)
    """
    runner = CommandRunner()
    try:
        rc, out, _ = runner.run(f"pgrep -f '{pattern}'", capture=True, check=False)
        if rc == 0 and out.strip():
            return [int(pid) for pid in out.strip().split('\n') if pid.strip()]
    except:
        pass
    return []


def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def format_bytes(num: int) -> str:
    """Format bytes to human-readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def format_seconds(seconds: int) -> str:
    """Format seconds to human-readable duration"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}m {secs}s"
    else:
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hrs}h {mins}m"


def get_environment_summary() -> Dict[str, Any]:
    """
    Get a comprehensive summary of the current environment

    Returns:
        Dictionary with environment information
    """
    info = {
        'is_colab': is_colab(),
        'python_version': sys.version.split()[0],
        'platform': sys.platform,
        'platform_full': platform.platform(),
        'hostname': platform.node(),
        'processor': platform.processor(),
    }

    if is_colab():
        info.update({
            'colab_gpu': 'COLAB_GPU' in os.environ,
            'colab_tpu': 'COLAB_TPU_ADDR' in os.environ,
            'colab_version': os.environ.get('COLAB_RUNTIME_VERSION', 'unknown'),
            'gpu_type': os.environ.get('COLAB_GPU', 'none'),
        })

    # Memory info
    try:
        if is_linux():
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
                mem_total = [l for l in meminfo.split('\n') if 'MemTotal:' in l]
                if mem_total:
                    kb = int(mem_total[0].split()[1])
                    info['memory_total'] = format_bytes(kb * 1024)
    except:
        pass

    return info


def check_ports_available(ports: List[int], host: str = 'localhost') -> Dict[int, bool]:
    """
    Check availability of multiple ports

    Args:
        ports: List of port numbers
        host: Host to check

    Returns:
        Dictionary mapping port -> True if available, False if in use
    """
    return {port: not check_port_in_use(port, host) for port in ports}


def find_available_port(start: int = 5900, end: int = 65535, host: str = 'localhost') -> Optional[int]:
    """
    Find an available port in a range

    Args:
        start: Start of range (inclusive)
        end: End of range (inclusive)
        host: Host to check

    Returns:
        Available port number or None if none found
    """
    for port in range(start, end + 1):
        if not check_port_in_use(port, host):
            return port
    return None


def ensure_dir(path: str) -> bool:
    """
    Ensure directory exists, create if needed

    Args:
        path: Directory path

    Returns:
        True if directory exists or was created, False on error
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        print(f"Failed to create directory {path}: {e}")
        return False