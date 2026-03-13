"""
Utility functions for Colab Virtual Desktop
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Tuple


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

    # Fallback: check environment variables
    return 'COLAB_GPU' in os.environ or 'COLAB_TF_ADDR' in os.environ


def run_command(
    cmd: str,
    shell: bool = True,
    capture: bool = False,
    timeout: int = None,
    check: bool = False
) -> Tuple[int, str, str]:
    """
    Run a shell command with proper error handling

    Args:
        cmd: Command to run
        shell: Use shell execution
        capture: Capture stdout/stderr
        timeout: Timeout in seconds
        check: Raise exception on failure

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
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        else:
            result = subprocess.run(cmd, shell=shell, timeout=timeout)
            return result.returncode, "", ""
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def kill_processes_on_port(port: int):
    """
    Kill any process listening on a given port

    Args:
        port: Port number to clear
    """
    try:
        # Try lsof
        code, out, err = run_command(f"lsof -ti:{port}", capture=True)
        if code == 0 and out.strip():
            pids = out.strip().split('\n')
            for pid in pids:
                if pid.strip():
                    run_command(f"kill -9 {pid} 2>/dev/null")
    except Exception:
        pass

    try:
        # Fallback to fuser
        run_command(f"fuser -k {port}/tcp 2>/dev/null")
    except Exception:
        pass

    try:
        # Alternative: pkill on process name
        if port == 5901:
            run_command("pkill -f 'Xvfb.*:1'")
            run_command("pkill -f 'vnc.*:1'")
        elif port == 6080:
            run_command("pkill -f websockify")
    except Exception:
        pass


def check_port_in_use(port: int) -> bool:
    """
    Check if a port is in use

    Args:
        port: Port to check

    Returns:
        True if port is in use, False otherwise
    """
    try:
        code, out, _ = run_command(f"netstat -tuln | grep ':{port} '", capture=True)
        return code == 0 and bool(out.strip())
    except:
        return False


def get_public_url_from_ngrok() -> Optional[str]:
    """
    Get the public URL from ngrok if it's running

    Returns:
        Public URL string or None
    """
    try:
        from pyngrok import ngrok
        tunnels = ngrok.get_tunnels()
        if tunnels:
            return str(tunnels[0].public_url).replace("http://", "https://")
    except:
        pass
    return None


def format_bytes(num: int) -> str:
    """Format bytes to human-readable string"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if num < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def wait_for_port(port: int, timeout: int = 30, interval: float = 0.5) -> bool:
    """
    Wait for a port to become available

    Args:
        port: Port to wait for
        timeout: Maximum wait time in seconds
        interval: Check interval in seconds

    Returns:
        True if port is available within timeout, False otherwise
    """
    import time
    start = time.time()
    while time.time() - start < timeout:
        if not check_port_in_use(port):
            return True
        time.sleep(interval)
    return False


def get_environment_summary() -> dict:
    """
    Get a summary of the current environment

    Returns:
        Dictionary with environment info
    """
    info = {
        'is_colab': is_colab(),
        'python_version': sys.version.split()[0],
        'platform': sys.platform,
    }

    if is_colab():
        info.update({
            'colab_gpu': 'COLAB_GPU' in os.environ,
            'colab_tpu': 'COLAB_TPU_ADDR' in os.environ,
            'colab_version': os.environ.get('COLAB_RUNTIME_VERSION', 'unknown')
        })

    return info
