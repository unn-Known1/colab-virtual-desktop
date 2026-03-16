"""
Base classes and common infrastructure for Colab Virtual Desktop

Provides shared functionality, abstract base classes, and
common utilities for the desktop management system.
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Callable, List, Tuple
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from contextlib import contextmanager


class DesktopComponent(ABC):
    """Abstract base class for desktop components"""

    def __init__(
        self,
        logger: Optional[Callable] = None,
        runner: Optional[Callable] = None
    ):
        self.logger = logger or self._default_logger
        self.runner = runner or self._default_runner
        self._initialized = False
        self._started = False
        self._stopped = False

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the component (one-time setup)"""
        pass

    @abstractmethod
    def start(self) -> bool:
        """Start the component"""
        pass

    @abstractmethod
    def stop(self) -> bool:
        """Stop the component"""
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """Check if component is running"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Get component status"""
        pass

    def _default_logger(self, msg: str, level: str = "INFO"):
        """Default logger"""
        print(f"[{level}] {msg}")

    def _default_runner(self, cmd: str, **kwargs):
        """Default command runner"""
        try:
            import subprocess
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=kwargs.get('timeout', 30)
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, "", str(e)

    def __enter__(self):
        self.initialize()
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


@dataclass
class ComponentInfo:
    """Standardized component information"""
    name: str
    status: str = "stopped"  # stopped, starting, running, failed
    pid: Optional[int] = None
    port: Optional[int] = None
    url: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    last_check: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'status': self.status,
            'pid': self.pid,
            'port': self.port,
            'url': self.url,
            'dependencies': self.dependencies,
            'metadata': self.metadata,
            'error': self.error,
            'last_check': self.last_check
        }


class LifecycleManager:
    """
    Manages lifecycle of multiple components

    Handles initialization order, dependency resolution,
    graceful shutdown, and state transitions.
    """

    def __init__(self, logger: Optional[Callable] = None):
        self.logger = logger or print
        self.components: Dict[str, DesktopComponent] = {}
        self.info: Dict[str, ComponentInfo] = {}
        self._lock = threading.RLock()

    def register(self, name: str, component: DesktopComponent, dependencies: List[str] = None):
        """Register a component"""
        with self._lock:
            self.components[name] = component
            self.info[name] = ComponentInfo(
                name=name,
                dependencies=dependencies or []
            )

    def initialize_all(self, skip_existing: bool = True) -> bool:
        """Initialize all components in dependency order"""
        with self._lock:
            order = self._resolve_dependencies()
            success = True

            for name in order:
                comp = self.components[name]
                info = self.info[name]

                if skip_existing and info.status in ("running", "started"):
                    self.logger(f"Component {name} already initialized, skipping")
                    continue

                try:
                    self.logger(f"Initializing {name}...")
                    if comp.initialize():
                        info.status = "initialized"
                        self.logger(f"✅ {name} initialized")
                    else:
                        info.status = "failed"
                        info.error = "Initialization returned False"
                        success = False
                        self.logger(f"❌ {name} initialization failed")
                except Exception as e:
                    info.status = "failed"
                    info.error = str(e)
                    success = False
                    self.logger(f"❌ {name} initialization error: {e}")

            return success

    def start_all(self) -> bool:
        """Start all components in dependency order"""
        with self._lock:
            order = self._resolve_dependencies()
            success = True

            for name in order:
                comp = self.components[name]
                info = self.info[name]

                if info.status in ("failed", "stopped"):
                    try:
                        self.logger(f"Starting {name}...")
                        if comp.start():
                            info.status = "running"
                            info.pid = getattr(comp, 'pid', None)
                            info.port = getattr(comp, 'port', None)
                            info.url = getattr(comp, 'url', None)
                            self.logger(f"✅ {name} started")
                        else:
                            info.status = "failed"
                            info.error = "Start returned False"
                            success = False
                            self.logger(f"❌ {name} start failed")
                    except Exception as e:
                        info.status = "failed"
                        info.error = str(e)
                        success = False
                        self.logger(f"❌ {name} start error: {e}")

            return success

    def stop_all(self) -> bool:
        """Stop all components in reverse dependency order"""
        with self._lock:
            order = self._resolve_dependencies(reverse=True)
            success = True

            for name in order:
                comp = self.components.get(name)
                info = self.info.get(name)

                if not comp or not info:
                    continue

                if info.status in ("stopped", "failed"):
                    continue

                try:
                    self.logger(f"Stopping {name}...")
                    if comp.stop():
                        info.status = "stopped"
                        info.pid = None
                        info.port = None
                        info.url = None
                        self.logger(f"✅ {name} stopped")
                    else:
                        info.status = "failed"
                        info.error = "Stop returned False"
                        success = False
                        self.logger(f"❌ {name} stop failed")
                except Exception as e:
                    info.status = "failed"
                    info.error = str(e)
                    success = False
                    self.logger(f"❌ {name} stop error: {e}")

            return success

    def _resolve_dependencies(self, reverse: bool = False) -> List[str]:
        """Resolve component startup order based on dependencies"""
        with self._lock:
            # Build dependency graph
            graph = {}
            for name, info in self.info.items():
                graph[name] = info.dependencies.copy()

            # Topological sort
            visited = set()
            temp = set()
            order = []

            def visit(node: str):
                if node in temp:
                    raise RuntimeError(f"Circular dependency detected: {node}")
                if node not in visited:
                    temp.add(node)
                    for dep in graph.get(node, []):
                        if dep in self.info:  # Only if dependency is registered
                            visit(dep)
                    temp.remove(node)
                    visited.add(node)
                    order.append(node)

            for node in list(graph.keys()):
                if node not in visited:
                    visit(node)

            if reverse:
                return list(reversed(order))
            return order

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all components"""
        with self._lock:
            return {name: info.to_dict() for name, info in self.info.items()}

    def get_running_components(self) -> List[str]:
        """Get list of running component names"""
        return [name for name, info in self.info.items() if info.status == "running"]

    def is_healthy(self) -> bool:
        """Check if all components are healthy"""
        return all(info.status == "running" for info in self.info.values())


class Configurable:
    """Mixin for components that need configuration"""

    def __init__(self, config: Dict[str, Any]):
        self._config = config.copy()
        self._validated = False

    @property
    def config(self) -> Dict[str, Any]:
        """Get configuration (read-only)"""
        return self._config.copy()

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get config value"""
        return self._config.get(key, default)

    def requires_config(self, *keys: str) -> bool:
        """Check if required config keys are present"""
        return all(k in self._config for k in keys)


class LazyInitializable:
    """Mixin for components that support lazy initialization"""

    def __init__(self):
        self._lazy_initialized = False

    def ensure_initialized(self) -> bool:
        """Ensure component is initialized"""
        if not self._lazy_initialized:
            self._lazy_initialized = self.initialize()
        return self._lazy_initialized


class ServiceLifecycleMixin:
    """Mixin providing standard service lifecycle"""

    def __init__(self):
        self._process = None
        self._pid = None

    def _start_process(
        self,
        cmd: str,
        env: Optional[Dict] = None,
        cwd: Optional[str] = None
    ) -> bool:
        """Start a subprocess and track it"""
        try:
            import subprocess
            self._process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                cwd=cwd,
                start_new_session=True
            )
            self._pid = self._process.pid
            return True
        except Exception as e:
            self.logger(f"Failed to start process: {e}", level="ERROR")
            return False

    def _stop_process(self, kill: bool = False) -> bool:
        """Stop tracked process"""
        if not self._process:
            return True

        try:
            if kill:
                self._process.kill()
            else:
                self._process.terminate()

            self._process.wait(timeout=10)
            self._process = None
            self._pid = None
            return True
        except Exception as e:
            self.logger(f"Error stopping process: {e}", level="ERROR")
            return False

    def is_process_running(self) -> bool:
        """Check if tracked process is running"""
        if not self._process:
            return False
        return self._process.poll() is None


def is_colab() -> bool:
    """Check if running in Google Colab (centralized)"""
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        return False


def get_default_log_dir() -> Path:
    """Get default log directory for current environment"""
    if is_colab():
        return Path('/content/colab_desktop_logs')
    else:
        return Path.home() / '.colab_desktop' / 'logs'


def ensure_dir(path: Union[str, Path]) -> bool:
    """Ensure directory exists"""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        print(f"Failed to create directory {path}: {e}")
        return False