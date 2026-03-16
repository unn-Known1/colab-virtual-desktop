"""
Port Management and Conflict Resolution for Colab Virtual Desktop

Provides intelligent port allocation, conflict detection,
dynamic port selection, and cleanup.
"""

import os
import sys
import socket
import subprocess
import time
import threading
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Set
from dataclasses import dataclass
from contextlib import contextmanager
import random


@dataclass
class PortInfo:
    """Information about a port"""
    port: int
    service: str
    pid: Optional[int] = None
    process_name: Optional[str] = None
    user: Optional[str] = None
    in_use: bool = False
    can_bind: bool = False
    locked_by: Optional[str] = None  # Who allocated it


class PortManager:
    """
    Intelligent port management with conflict resolution

    Features:
    - Automatic port allocation with conflict avoidance
    - Persistent port reservations
    - Force-kill cleanup of stuck processes
    - Port range management
    - Real-time conflict detection
    - Graceful port release
    """

    # Common port ranges for different services
    SERVICE_PORT_RANGES = {
        'vnc': (5900, 5910),
        'novnc': (6080, 6090),
        'ssh': (2200, 2300),
        'jupyter': (8888, 8898),
        'tensorboard': (6006, 6016),
        'custom': (10000, 30000)
    }

    # Reserved ports that should be skipped
    RESERVED_PORTS = {
        22, 80, 443, 4433, 8080, 8081, 3000, 5000, 8000, 9000
    }

    def __init__(
        self,
        runner: Optional[Callable] = None,
        logger: Optional[Callable] = None,
        reservation_file: Optional[str] = None
    ):
        """
        Initialize port manager

        Args:
            runner: Command runner function
            logger: Logging function
            reservation_file: File to persist port reservations
        """
        self.runner = runner or self._default_runner
        self.logger = logger or print
        self.reservation_file = reservation_file or self._default_reservation_file()

        # Active reservations
        self.reservations: Dict[int, PortInfo] = {}
        self.service_allocations: Dict[str, int] = {}  # service -> port

        # Load persisted reservations
        self._load_reservations()

        # Lock for thread safety
        self._lock = threading.RLock()

        # Scan for conflicts on init
        self._scan_all_ports()

    def _default_runner(self, cmd: str, **kwargs):
        """Default command runner"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=kwargs.get('timeout', 5)
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, "", str(e)

    def _default_reservation_file(self) -> Path:
        """Get default reservation file path"""
        if is_colab():
            return Path('/content/colab_desktop_ports.json')
        else:
            return Path.home() / '.colab_desktop' / 'port_reservations.json'

    def _load_reservations(self):
        """Load persisted reservations"""
        try:
            if self.reservation_file.exists():
                import json
                with open(self.reservation_file, 'r') as f:
                    data = json.load(f)

                for port_str, info in data.items():
                    port = int(port_str)
                    self.reservations[port] = PortInfo(**info)

                self.logger(f"Loaded {len(self.reservations)} port reservations")
        except Exception as e:
            self.logger(f"Failed to load reservations: {e}", level="WARNING")

    def _save_reservations(self):
        """Save reservations to disk"""
        try:
            self.reservation_file.parent.mkdir(parents=True, exist_ok=True)

            import json
            data = {}
            for port, info in self.reservations.items():
                data[str(port)] = asdict(info)

            with open(self.reservation_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            self.logger(f"Failed to save reservations: {e}", level="WARNING")

    def _scan_port(self, port: int) -> Optional[PortInfo]:
        """Scan a single port to determine its state"""
        info = PortInfo(port=port)

        try:
            # Check if we have a reservation
            if port in self.reservations:
                info.locked_by = self.reservations[port].locked_by
                info.service = self.reservations[port].service

            # Check if something is listening
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                result = s.connect_ex(('127.0.0.1', port))
                info.in_use = (result == 0)

            if info.in_use:
                # Try to find process
                try:
                    rc, out, err = self.runner(f"lsof -i:{port} -sTCP:LISTEN -n -P", capture=True, timeout=2)
                    if rc == 0 and out.strip():
                        lines = out.strip().split('\n')
                        if len(lines) > 1:
                            parts = lines[1].split()
                            if len(parts) >= 2:
                                info.pid = int(parts[1])
                                info.process_name = parts[0] if len(parts) > 0 else None
                                info.user = parts[2] if len(parts) > 2 else None
                except:
                    pass
            else:
                # Try to bind to see if port is available
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s.bind(('127.0.0.1', port))
                        info.can_bind = True
                except OSError:
                    info.can_bind = False

        except Exception as e:
            self.logger(f"Error scanning port {port}: {e}", level="DEBUG")

        return info

    def _scan_all_ports(self, port_range: Tuple[int, int] = (1, 65535)):
        """Scan a range of ports to detect current usage"""
        with self._lock:
            self.logger("Scanning ports...", level="DEBUG")
            for port in range(port_range[0], port_range[1] + 1):
                if port % 1000 == 0:
                    time.sleep(0.001)  # Yield occasionally

                info = self._scan_port(port)
                if info.in_use and port not in self.reservations:
                    self.logger(f"Port {port} in use by {info.process_name} (PID {info.pid})",
                               level="DEBUG")

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
            port_range: Custom range to search (start, end)
            force: Force reservation even if port is in use (DANGEROUS)

        Returns:
            PortInfo with reserved port

        Raises:
            RuntimeError: If no available port found
        """
        with self._lock:
            # If we already have a reservation for this service, return it
            if service in self.service_allocations:
                existing_port = self.service_allocations[service]
                if existing_port in self.reservations:
                    self.logger(f"Reusing existing reservation for {service}: port {existing_port}")
                    return self.reservations[existing_port]

            # Determine port range
            if not port_range:
                port_range = self.SERVICE_PORT_RANGES.get(service)
                if not port_range:
                    # Use custom range
                    port_range = (10000, 30000)

            start, end = port_range

            # Try preferred port first
            if preferred_port and start <= preferred_port <= end:
                if self._can_reserve(preferred_port, force):
                    return self._create_reservation(preferred_port, service)

            # Search for available port in range
            # Shuffle to avoid always using same ports
            ports = list(range(start, end + 1))
            # Remove reserved ports
            ports = [p for p in ports if p not in self.RESERVED_PORTS]
            random.shuffle(ports)

            for port in ports:
                if self._can_reserve(port, force):
                    return self._create_reservation(port, service)

            # If no port found in range, try extended range
            extended_start = max(1024, start - 100)
            extended_end = min(65535, end + 100)
            if (extended_start, extended_end) != (start, end):
                self.logger(f"No ports in range {start}-{end}, trying extended range...")
                ports = list(range(extended_start, extended_end + 1))
                ports = [p for p in ports if p not in self.RESERVED_PORTS]
                random.shuffle(ports)
                for port in ports:
                    if self._can_reserve(port, force):
                        return self._create_reservation(port, service)

            raise RuntimeError(f"No available ports for service '{service}' in range {start}-{end}")

    def _can_reserve(self, port: int, force: bool) -> bool:
        """Check if a port can be reserved"""
        # Check reservation file
        if port in self.reservations:
            existing = self.reservations[port]
            if existing.locked_by != "current_session":
                return False
            # Already reserved by us, can reuse
            return True

        # Check if in use
        info = self._scan_port(port)

        if info.in_use:
            if force:
                self.logger(f"Force-reserving port {port} (currently in use)", level="WARNING")
                return True
            return False

        if not info.can_bind:
            return False

        return True

    def _create_reservation(self, port: int, service: str) -> PortInfo:
        """Create a reservation for a port"""
        info = PortInfo(
            port=port,
            service=service,
            locked_by="current_session",
            can_bind=True
        )

        self.reservations[port] = info
        self.service_allocations[service] = port
        self._save_reservations()

        self.logger(f"Reserved port {port} for service '{service}'", level="INFO")
        return info

    def release_port(self, port: int):
        """Release a specific port reservation"""
        with self._lock:
            if port in self.reservations:
                service = self.reservations[port].service
                if service in self.service_allocations and self.service_allocations[service] == port:
                    del self.service_allocations[service]
                del self.reservations[port]
                self._save_reservations()
                self.logger(f"Released port {port}")

    def release_service(self, service: str):
        """Release all ports for a service"""
        with self._lock:
            if service in self.service_allocations:
                port = self.service_allocations[service]
                if port in self.reservations:
                    del self.reservations[port]
                del self.service_allocations[service]
                self._save_reservations()
                self.logger(f"Released all reservations for service '{service}'")

    def get_reserved_port(self, service: str) -> Optional[int]:
        """Get the port reserved for a service"""
        return self.service_allocations.get(service)

    def get_reservation_info(self, port: int) -> Optional[PortInfo]:
        """Get reservation info for a port"""
        return self.reservations.get(port)

    def force_release_port(self, port: int, kill_process: bool = False):
        """
        Force release a port, optionally killing the process using it

        Args:
            port: Port to release
            kill_process: Kill the process using the port (admin/root may be required)
        """
        with self._lock:
            info = self._scan_port(port)

            if info.pid and kill_process:
                try:
                    self.logger(f"Killing PID {info.pid} on port {port}")
                    subprocess.run(["kill", "-9", str(info.pid)], check=False)
                    time.sleep(1)  # Give it time to die
                except Exception as e:
                    self.logger(f"Failed to kill process: {e}", level="ERROR")

            # Clear any reservation
            self.release_port(port)

    def cleanup_all(self, kill_processes: bool = False):
        """
        Clean up all reservations

        Args:
            kill_processes: Also kill processes using reserved ports
        """
        with self._lock:
            ports_to_kill = []
            if kill_processes:
                for port, info in self.reservations.items():
                    if info.pid:
                        ports_to_kill.append((port, info.pid))

            # Clear reservations
            self.reservations.clear()
            self.service_allocations.clear()
            self._save_reservations()

            # Kill processes if requested
            for port, pid in ports_to_kill:
                try:
                    subprocess.run(["kill", "-9", str(pid)], check=False)
                    self.logger(f"Killed process {pid} on port {port}")
                except:
                    pass

            self.logger("Port manager cleaned up", level="INFO")

    def get_available_ports(
        self,
        count: int,
        port_range: Optional[Tuple[int, int]] = None,
        exclude_reserved: bool = True
    ) -> List[int]:
        """
        Get multiple available ports

        Args:
            count: Number of ports needed
            port_range: Range to search (default: service default)
            exclude_reserved: Exclude reserved ports

        Returns:
            List of available port numbers
        """
        if not port_range:
            # Use a wide range
            port_range = (1024, 65535)

        start, end = port_range
        available = []

        with self._lock:
            # Scan first
            for port in range(start, end + 1):
                if len(available) >= count:
                    break

                if exclude_reserved and port in self.RESERVED_PORTS:
                    continue

                if port in self.reservations:
                    continue

                info = self._scan_port(port)
                if info.can_bind and not info.in_use:
                    available.append(port)

        if len(available) < count:
            # Try a different approach - randomly
            ports = list(range(start, end + 1))
            if exclude_reserved:
                ports = [p for p in ports if p not in self.RESERVED_PORTS]

            random.shuffle(ports)

            for port in ports:
                if len(available) >= count:
                    break
                if port in self.reservations:
                    continue

                info = self._scan_port(port)
                if info.can_bind and not info.in_use:
                    available.append(port)

        return available[:count]

    def scan_services(self) -> List[PortInfo]:
        """
        Scan common ports to detect services

        Returns:
            List of PortInfo for ports with known services
        """
        common_ports = {
            5900: 'VNC',
            5901: 'VNC',
            5902: 'VNC',
            5903: 'VNC',
            6080: 'noVNC',
            6081: 'noVNC',
            8080: 'HTTP Alt',
            8888: 'Jupyter',
            6006: 'TensorBoard',
            22: 'SSH',
        }

        results = []
        for port, service in common_ports.items():
            info = self._scan_port(port)
            info.service = service
            results.append(info)

        return results

    def get_port_conflicts(self) -> List[PortInfo]:
        """
        Get list of ports with conflicts (in use but not reserved)

        Returns:
            List of conflicting PortInfo objects
        """
        conflicts = []
        with self._lock:
            # Scan a sample of ports
            common_ports = list(range(5900, 5910)) + list(range(6080, 6090))
            for port in common_ports:
                info = self._scan_port(port)
                if info.in_use and port not in self.reservations:
                    conflicts.append(info)

        return conflicts

    def is_safe_port(self, port: int) -> bool:
        """Check if a port is in the safe range for user applications"""
        return 1024 <= port <= 65535 and port not in self.RESERVED_PORTS

    def suggest_port_for_service(self, service: str) -> int:
        """
        Suggest an available port for a service

        Args:
            service: Service type

        Returns:
            Suggested port number

        Raises:
            RuntimeError: If no port available
        """
        port_range = self.SERVICE_PORT_RANGES.get(service, (10000, 30000))
        available = self.get_available_ports(1, port_range)
        if available:
            return available[0]
        raise RuntimeError(f"No available ports for {service}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup_all(kill_processes=False)

    def get_status(self) -> Dict[str, Any]:
        """Get port manager status"""
        with self._lock:
            return {
                'reserved_ports': len(self.reservations),
                'service_allocations': self.service_allocations.copy(),
                'reservations': [
                    {'port': p, 'service': i.service, 'locked_by': i.locked_by}
                    for p, i in self.reservations.items()
                ]
            }


# Convenience functions

def is_port_in_use(port: int, host: str = 'localhost') -> bool:
    """Quick check if port is in use"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
    except:
        return False


def find_available_port(
    start: int = 10000,
    end: int = 30000,
    exclude: Optional[List[int]] = None
) -> Optional[int]:
    """
    Find an available port in range

    Args:
        start: Start of range
        end: End of range
        exclude: Ports to exclude

    Returns:
        Available port or None
    """
    exclude = exclude or []
    with PortManager() as pm:
        ports = pm.get_available_ports(1, (start, end))
        if ports:
            return ports[0]
    return None


def kill_process_on_port(port: int) -> bool:
    """Kill process listening on port"""
    try:
        result = subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        try:
            subprocess.run(["kill", "-9", f"$(lsof -ti:{port})"], shell=True, timeout=5)
            return True
        except:
            return False