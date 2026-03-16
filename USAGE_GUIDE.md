# Colab Virtual Desktop - Usage Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Installation](#installation)
3. [Basic Usage](#basic-usage)
4. [Advanced Features](#advanced-features)
5. [Configuration](#configuration)
6. [Monitoring & Health](#monitoring--health)
7. [Troubleshooting](#troubleshooting)
8. [API Reference](#api-reference)

---

## Quick Start

### 1. Get ngrok Token
1. Sign up at [ngrok.com](https://ngrok.com)
2. Get your auth token from the dashboard

### 2. Install in Colab
```python
!pip install -q colab-virtual-desktop
```

### 3. Start Desktop
```python
from colab_desktop import start_virtual_desktop

desktop = start_virtual_desktop("YOUR_NGROK_TOKEN")
# URL printed automatically - open in browser!
```

That's it! 🎉

---

## Installation

### From PyPI (when published)
```bash
pip install colab-virtual-desktop
```

### From Source
```bash
git clone <repo>
cd colab-virtual-desktop
pip install -e .
```

### Dependencies (Auto-installed)
The tool automatically installs:
- Xvfb (virtual X server)
- XFCE desktop environment
- tightvncserver
- novnc + websockify
- Additional utilities

---

## Basic Usage

### Simple One-Liner
```python
from colab_desktop import start_virtual_desktop

desktop = start_virtual_desktop(
    ngrok_token="YOUR_TOKEN",
    auto_open=True  # Browser opens automatically
)
```

### Context Manager (Auto-cleanup)
```python
from colab_desktop import start_virtual_desktop

with start_virtual_desktop("YOUR_TOKEN") as desktop:
    url = desktop.get_url()
    print(f"Desktop available at: {url}")

    # Run GUI apps
    !firefox &
    !xclock &

# Desktop automatically stops when exiting 'with' block
```

### Manual Control
```python
from colab_desktop import ColabDesktopImproved

desktop = ColabDesktopImproved(ngrok_auth_token="YOUR_TOKEN")

# Setup (installs dependencies - run once)
desktop.setup()

# Start services
desktop.start()

# Get URL
url = desktop.get_url()
print(f"Open: {url}")

# ... use desktop ...

# Clean shutdown
desktop.stop()
```

---

## Advanced Features

### Custom Configuration
```python
from colab_desktop import ColabDesktopImproved

desktop = ColabDesktopImproved(
    ngrok_auth_token="YOUR_TOKEN",
    vnc_password="strong_password_here",  # Min 8 chars
    display=":2",                          # Use display :2 instead of :1
    geometry="1920x1080",                  # Full HD resolution
    depth=24,                              # Color depth (8, 16, 24, 32)
    vnc_port=5902,                        # Custom VNC port
    novnc_port=6081,                      # Custom noVNC port
    ngrok_region="eu",                    # Regional tunnel
    auto_open=True,                       # Open browser automatically
    install_deps=True                     # Auto-install dependencies
)
```

### Using Configuration Builder
```python
from colab_desktop import ConfigBuilder

config = (ConfigBuilder()
          .with_ngrok_token("TOKEN")
          .with_geometry("1280x720")
          .with_depth(16)
          .with_auto_open(False)
          .validate()          # Validates and auto-corrects
          .build())            # Returns dict

desktop = ColabDesktopImproved(**config)
```

### Using Presets
```python
from colab_desktop.helpers import create_desktop_with_preset, PRESETS

# Available presets: default, hd, low-res, performance, ultra-low
desktop = create_desktop_with_preset(
    ngrok_token="TOKEN",
    preset_name='hd',  # 1920x1080, depth=24
    auto_open=True
)

print(f"Preset: {PRESETS['hd']['description']}")
```

### Health Monitoring
```python
from colab_desktop import ColabDesktopImproved

desktop = ColabDesktopImproved(ngrok_auth_token="TOKEN")
desktop.setup()
desktop.start()

# Check health status
print(desktop.get_health_status_text())

# Or get structured data
status = desktop.get_health_status_text()  # Human-readable
# Or use health checker directly for programmatic access
```

### Launching GUI Applications
```python
# After starting desktop
desktop.launch_app("xclock &")
desktop.launch_app("firefox &")
desktop.launch_app("gedit &")

# Run Python GUI apps
import tkinter as tk
root = tk.Tk()
root.mainloop()

# PyGame
import pygame
pygame.init()
screen = pygame.display.set_mode((640, 480))
```

### Taking Screenshots
```python
screenshot_path = desktop.take_screenshot("/content/my_screenshot.png")
print(f"Screenshot saved: {screenshot_path}")
```

### Running in Background
```python
import threading
import time

def run_desktop():
    desktop = start_virtual_desktop("TOKEN", auto_open=False)
    time.sleep(3600)  # Keep alive for 1 hour
    desktop.stop()

thread = threading.Thread(target=run_desktop, daemon=True)
thread.start()
```

---

## Configuration

### Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ngrok_auth_token` | **Required** | Get from https://ngrok.com dashboard |
| `vnc_password` | `"colab123"` | VNC server password (min 6 chars) |
| `display` | `":1"` | X display number (`:1`, `:2`, etc.) |
| `geometry` | `"1280x720"` | Screen resolution (e.g., `1920x1080`) |
| `depth` | `24` | Color depth: 8, 16, 24, or 32 |
| `vnc_port` | `5901` | VNC server port (1024-65535) |
| `novnc_port` | `6080` | noVNC web port (1024-65535) |
| `ngrok_region` | `"us"` | ngrok region: us, eu, ap, au, sa, jp, in |
| `auto_open` | `False` | Auto-open browser when desktop ready |
| `install_deps` | `True` | Auto-install system dependencies |

### Environment Variables
Override configuration via environment:
- `NGROK_AUTH_TOKEN`: ngrok token
- `COLAB_DESKTOP_QUIET`: Set to '1' for quiet mode
- `COLAB_DESKTOP_DEBUG`: Set to '1' for debug logging

### Validation
```python
config = validate_config(your_config)
if not config['valid']:
    print(config['errors'])
```

---

## Monitoring & Health

### Health Status (Text)
```python
print(desktop.get_health_status_text())
```
Output:
```
============================================================
SERVICE HEALTH STATUS
============================================================
Overall: ✅ healthy

✅ XVFB
   Status: running
   PID: 12345
   Port: 6001
   Display: :1

✅ VNC
   Status: running
   PID: 12346
   Port: 5901

✅ NOVNC
   Status: running
   PID: 12347
   Port: 6080
   URL: http://localhost:6080

✅ NGROK
   Status: running
   URL: https://abc123.ngrok-free.app/vnc.html

============================================================
```

### Programmatic Health Check
```python
health = desktop.health_checker
health.run_all_checks()

if health.get_overall_health() == "healthy":
    print("All services running!")

for service, info in health.results.items():
    print(f"{service}: {info.status.value}")
```

### Resource Usage
```python
usage = health.get_resource_usage()
for service, info in usage.items():
    print(f"{service}: {info['memory_mb']:.1f}MB RAM, "
          f"{info['cpu_percent']:.1f}% CPU")
```

---

## Troubleshooting

### Common Issues

**1. "VNC server not found"**
```bash
# In Colab cell
!apt-get update && apt-get install -y tightvncserver
```

**2. "ngrok connection failed"**
- Check your auth token is correct
- ngrok may have usage limits on free tier
- Try different region: `ngrok_region="eu"`

**3. "Browser shows black screen"**
- Wait 10-15 seconds for XFCE to fully start
- Check desktop URL is correct (includes `/vnc.html`)
- Refresh browser page

**4. "Port already in use"**
- Tool auto-detects conflicts and suggests alternatives
- Manually set different ports:
  ```python
  ColabDesktop(vnc_port=5902, novnc_port=6081)
  ```

**5. "No module named 'pyngrok'"**
```python
!pip install pyngrok
```

### Debug Mode
```python
import os
os.environ['COLAB_DESKTOP_DEBUG'] = '1'

# Or use verbose flag
desktop = start_virtual_desktop("TOKEN", verbose=True)
```

### Check Logs
Logs are automatically saved to:
- Colab: `/content/colab_desktop_logs/`
- Local: `~/.colab_desktop/logs/`

View logs:
```python
!tail -f /content/colab_desktop_logs/colab_desktop_*.log
```

### Reset Everything
```python
desktop.stop()  # Stop if running
desktop.port_manager.cleanup_all(kill_processes=True)
desktop.health_checker.stop_monitoring()
```

---

## API Reference

### Main Classes

#### `ColabDesktopImproved`
The improved desktop manager with all enhancements.

**Constructor:**
```python
ColabDesktopImproved(
    ngrok_auth_token: str,
    vnc_password: str = "colab123",
    display: str = ":1",
    geometry: str = "1280x720",
    depth: int = 24,
    vnc_port: Optional[int] = None,
    novnc_port: Optional[int] = None,
    ngrok_region: str = "us",
    auto_open: bool = False,
    install_deps: bool = True
)
```

**Methods:**
- `setup() -> bool`: Install dependencies and prepare
- `start() -> bool`: Start all services
- `stop() -> None`: Stop all services
- `restart() -> bool`: Restart all services
- `get_url() -> Optional[str]`: Get public VNC URL
- `launch_app(command: str, wait: bool = False)`: Start GUI app
- `take_screenshot(path: str) -> str`: Capture desktop
- `get_health_status_text() -> str`: Human-readable health status

**Context Manager:**
```python
with ColabDesktopImproved(...) as desktop:
    # Auto-starts
    # Auto-stops on exit
    pass
```

#### `ConfigBuilder`
Fluent configuration builder.

**Example:**
```python
config = (ConfigBuilder()
          .with_ngrok_token("...")
          .with_geometry("1920x1080")
          .validate()
          .build())
```

All `with_*` methods available:
- `with_ngrok_token(token)`
- `with_vnc_password(password)`
- `with_display(display)`
- `with_geometry(geometry)`
- `with_depth(depth)`
- `with_vnc_port(port)`
- `with_novnc_port(port)`
- `with_ngrok_region(region)`
- `with_auto_open(flag)`
- `with_install_deps(flag)`
- `with_extra(key, value)`: Custom options

#### `PortManager`
Port allocation and conflict resolution.

**Methods:**
- `reserve_port(service, preferred_port, force) -> PortInfo`
- `release_port(port)`
- `release_service(service)`
- `get_reserved_port(service) -> Optional[int]`
- `force_release_port(port, kill_process)`
- `get_available_ports(count, range) -> List[int]`
- `suggest_port_for_service(service) -> int`
- `cleanup_all(kill_processes)`

#### `ColabLogger`
Advanced logging with metrics.

**Methods:**
- `debug()`, `info()`, `warning()`, `error()`, `critical()`
- `exception()`: Log with traceback
- `audit(action, details, user)`: Audit log
- `inc_counter(name, value)`: Increment counter
- `time_operation(name)`: Timing context manager
- `get_metrics() -> dict`: Get performance metrics

### Helper Functions

#### `start_virtual_desktop()`
Quick one-liner startup.

```python
desktop = start_virtual_desktop(
    ngrok_token: str,
    auto_open: bool = True,
    geometry: str = "1280x720",
    **kwargs
) -> ColabDesktopImproved
```

#### `validate_config(config)`
Validate configuration dictionary.

```python
config, summary = validate_config({
    'ngrok_auth_token': '...',
    'geometry': '1280x720'
})
```

#### `create_desktop_with_preset(ngrok_token, preset_name)`
Create desktop using predefined preset.

```python
desktop = create_desktop_with_preset(
    "TOKEN",
    preset_name='hd'  # default, hd, low-res, performance, ultra-low
)
```

### Constants

#### `PRESETS`
Predefined configurations:
```python
PRESETS = {
    'default': {'geometry': '1280x720', 'depth': 24, 'description': 'Standard HD'},
    'hd': {'geometry': '1920x1080', 'depth': 24, 'description': 'Full HD'},
    'low-res': {'geometry': '1024x768', 'depth': 16, 'description': 'Low resolution'},
    'performance': {'geometry': '1280x720', 'depth': 16, 'description': 'Optimized'},
    'ultra-low': {'geometry': '800x600', 'depth': 16, 'description': 'Minimal'}
}
```

---

## Examples Directory

See the `examples/` directory for complete notebook examples:
- `basic_usage.ipynb`: Simple startup and usage
- `advanced.ipynb`: Advanced features, health monitoring, custom configs
- `install_colab.py`: Standalone installer script

---

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes with tests
4. Run tests: `pytest tests/ -v`
5. Submit Pull Request

---

## License

MIT License - see LICENSE file.

---

## Support

- **Issues:** Use GitHub Issues
- **Documentation:** This guide and code docstrings
- **Examples:** Check `examples/` directory

---

**Enjoy your virtual desktop in Google Colab!** 🚀