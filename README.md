# Colab Virtual Desktop

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Status: Beta](https://img.shields.io/badge/status-beta-orange.svg)]()

**Turn Google Colab into a remote desktop with full VNC browser access**

Run GUI applications in Google Colab and access them from any browser using VNC + noVNC + ngrok tunneling.

<div align="center">
  <img src="docs/architecture.png" alt="Architecture" width="800"/>
</div>

---

## ✨ Features

- **One-Command Setup** - Automates entire desktop environment installation
- **XFCE Desktop** - Lightweight, fast Linux desktop environment
- **VNC Server** - Standard remote display protocol with password protection
- **noVNC Web Client** - Access desktop directly in browser (no VNC client needed)
- **ngrok Tunneling** - Secure public URL that works from anywhere
- **Process Management** - Automatic cleanup, graceful shutdown
- **Context Manager** - Use with `with` statement for automatic cleanup
- **CLI Tool** - Command-line interface for quick access
- **Colab Optimized** - Pre-configured for Google Colab environment

---

## 🚀 Quick Start

### In Google Colab Notebook

```python
# 1. Install the package
!pip install -q colab-virtual-desktop

# 2. Import and create desktop (replace with your ngrok token)
from colab_desktop import start_virtual_desktop

desktop = start_virtual_desktop("YOUR_NGROK_AUTH_TOKEN")

# 3. A URL will be printed - open it in browser to see desktop!
# Optional: desktop.open_in_browser()  # Opens automatically if auto_open=True
```

**URL will look like:** `https://xxxx.ngrok-free.app/vnc.html`

---

### Using the CLI

```bash
# Install globally
pip install colab-virtual-desktop

# Run
colab-desktop --token YOUR_NGROK_TOKEN
```

---

## 📦 What Gets Installed

The setup automatically installs:

| Component | Purpose |
|-----------|---------|
| **Xvfb** | Virtual X server (fake display) |
| **XFCE** | Lightweight desktop environment |
| **tightvncserver** | VNC server to serve the display |
| **noVNC** | Web-based VNC client (runs in browser) |
| **websockify** | Proxy that converts VNC to WebSocket |
| **ngrok** | Creates public URL to access localhost |

---

## 🎯 Usage Examples

### Basic Usage with Context Manager

```python
from colab_desktop import ColabDesktop

with ColabDesktop(ngrok_auth_token="YOUR_TOKEN") as desktop:
    print(f"Desktop URL: {desktop.get_url()}")
    # Desktop is running, open URL in browser
    # Run any GUI app here
    # Desktop auto-stops when exiting the with block
```

### Full Control

```python
from colab_desktop import ColabDesktop

desktop = ColabDesktop(
    ngrok_auth_token="YOUR_TOKEN",
    geometry="1920x1080",  # Full HD
    vnc_password="secure123",
    auto_open=True  # Open browser automatically
)

# Setup dependencies (run once)
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

### Quick Helper

```python
from colab_desktop import start_virtual_desktop

desktop = start_virtual_desktop("YOUR_TOKEN", auto_open=True)
# That's it! URL is printed and browser opens automatically.
```

---

## 🛠️ Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ngrok_auth_token` | (required) | Get from [ngrok.com](https://ngrok.com) |
| `vnc_password` | "colab123" | VNC server password |
| `display` | ":1" | X display number |
| `geometry` | "1280x720" | Screen resolution |
| `depth` | 24 | Color depth (bits per pixel) |
| `vnc_port` | 5901 | VNC server port |
| `novnc_port` | 6080 | noVNC web port |
| `ngrok_region` | "us" | ngrok tunnel region (us, eu, ap, au, sa, jp, in) |
| `auto_open` | False | Open browser automatically |
| `install_deps` | True | Auto-install system packages |

---

## 🖥️ Running GUI Applications

Once the desktop is running, you can launch any X11 application from Colab cells:

```python
!xclock &
!firefox &
!gedit &
!python3 -m tkinter  # Tkinter apps
!python3 your_gui_app.py
```

All windows will appear in the virtual desktop accessible via the VNC URL.

---

## 🔐 Security Notes

- **VNC Password**: Set a strong password with `--password` flag
- **ngrok URL**: The URL is public! Anyone with it can access your desktop.
- **Colab VM**: The VM resets after ~12 hours, so you need to restart.
- **No persistence**: Files are lost when VM resets. Download important work.
- **Resource limits**: Free Colab has limited CPU/RAM. Don't run heavy apps.

---

## 📋 Prerequisites

### 1. Google Colab Notebook
Create a new notebook at [colab.research.google.com](https://colab.research.google.com)

### 2. ngrok Account
1. Sign up at [ngrok.com](https://ngrok.com) (free tier available)
2. Get your auth token from the dashboard
3. Use that token as `--token` parameter

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| **"Cannot connect to display"** | Ensure `desktop.setup()` was called first |
| **ngrok not connecting** | Check your auth token, internet connection |
| **Browser says "connection closed"** | Colab may have timed out. Restart runtime. |
| **Black screen in browser** | Wait 10-15 seconds for XFCE to fully start |
| **Cannot open port 6080** | Another process using the port. Use different `--novnc-port` |
| **Import errors** | Restart Colab runtime after pip install |
| **Slow performance** | Use lower resolution (`--geometry 1024x768`) and depth (`--depth 16`) |

---

## 🧪 Testing

```python
# After starting desktop
from colab_desktop import test_desktop

result = test_desktop()
print(result)  # Should see a clock on the desktop
```

---

## 📚 API Reference

### `ColabDesktop` Class

Main class for managing the virtual desktop.

#### Methods

- `setup() -> bool`: Install dependencies and prepare environment
- `start() -> bool`: Start all services (Xvfb, XFCE, VNC, noVNC, ngrok)
- `stop()`: Stop all services and clean up
- `restart() -> bool`: Restart all services
- `get_url() -> Optional[str]`: Get the public VNC URL
- `open_in_browser()`: Open the desktop in default browser

#### Context Manager

```python
with ColabDesktop(token) as desktop:
    # Auto-starts
    # Desktop is available
    pass
# Auto-stops on exit
```

### `start_virtual_desktop()` Function

Convenience function for one-line startup:

```python
desktop = start_virtual_desktop(
    ngrok_token="YOUR_TOKEN",
    auto_open=True,
    geometry="1280x720"
)
```

---

## 📁 Project Structure

```
colab-virtual-desktop/
├── colab_desktop/
│   ├── __init__.py      # Package entry point
│   ├── core.py          # Main ColabDesktop class
│   ├── cli.py           # Command-line interface
│   └── utils.py         # Utility functions
├── examples/
│   ├── basic_usage.ipynb
│   ├── advanced.ipynb
│   └── multi_window.py
├── tests/
│   └── test_basic.py
├── docs/
│   ├── architecture.png
│   └── screenshots/
├── setup.py
├── requirements.txt
├── README.md
└── LICENSE
```

---

## 📖 Examples

### Example 1: Run Firefox Browser

```python
desktop = start_virtual_desktop("YOUR_TOKEN")
# Open URL in browser
!firefox &
# Firefox opens on virtual desktop
```

### Example 2: Python Tkinter App

```python
import tkinter as tk
from colab_desktop import start_virtual_desktop

desktop = start_virtual_desktop("YOUR_TOKEN")

# Create Tkinter app
root = tk.Tk()
root.title("Hello from Colab!")
tk.Label(root, text="Running in Colab Virtual Desktop!").pack()
root.mainloop()
```

### Example 3: PyGame

```python
import pygame
from colab_desktop import start_virtual_desktop

desktop = start_virtual_desktop("YOUR_TOKEN")

pygame.init()
screen = pygame.display.set_mode((640, 480))
pygame.display.set_caption("PyGame on Colab!")
# ... your pygame code ...
```

---

## 🧩 Advanced Usage

### Custom Ports

```python
desktop = ColabDesktop(
    ngrok_auth_token="TOKEN",
    vnc_port=5902,      # Different VNC port
    novnc_port=6081,    # Different noVNC port
)
desktop.start()
```

### High Performance Mode

```python
desktop = ColabDesktop(
    ngrok_auth_token="TOKEN",
    geometry="1024x768",  # Lower resolution
    depth=16,             # Less color depth
)
```

### Region Selection

```python
desktop = ColabDesktop(
    ngrok_auth_token="TOKEN",
    ngrok_region="eu"  # Options: us, eu, ap, au, sa, jp, in
)
```

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Inspired by standard Colab VNC setup methods
- Uses [noVNC](https://github.com/novnc/novnc) for web-based VNC
- Uses [ngrok](https://ngrok.com) for secure tunneling
- Built for the AI/ML community needing GUI access in Colab

---

## 📧 Contact

For issues and feature requests, please use the GitHub Issues page.

**Note**: This tool is designed for Google Colab. While it may work in other Jupyter environments, full functionality is not guaranteed outside Colab.

---

## 🎉 Start Using Now!

```python
!pip install colab-virtual-desktop
from colab_desktop import start_virtual_desktop
desktop = start_virtual_desktop("YOUR_NGROK_TOKEN")
# Open the printed URL in your browser and enjoy your virtual desktop!
```
