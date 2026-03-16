# Setup Guide - Colab Virtual Desktop

Complete step-by-step setup instructions for using Colab Virtual Desktop.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Get ngrok Token](#get-ngrok-token)
3. [Installation](#installation)
4. [First Run](#first-run)
5. [Using the Desktop](#using-the-desktop)
6. [Troubleshooting](#troubleshooting)
7. [Advanced Configuration](#advanced-configuration)
8. [Uninstall](#uninstall)

---

## Prerequisites

### Required
- **Google account** - For accessing Google Colab
- **ngrok account** - Free tier is sufficient
- **Modern web browser** - Chrome, Firefox, Edge, Safari

### Optional (for development)
- Python 3.8+ installed locally (if developing)
- Git (for cloning repository)

---

## Get ngrok Token

ngrok is used to create a public URL that tunnels to your Colab VM.

1. Go to [ngrok.com](https://ngrok.com)
2. Click **"Sign up"** (free tier)
3. Verify your email
4. Go to **Dashboard** → **"Your Authtoken"**
5. Copy the token (looks like: `2vG7...`)

**Note:** The free tier has rate limits but is perfectly fine for personal use.

---

## Installation

There are three ways to install:

### Method 1: Install from PyPI (Recommended)

```bash
pip install colab-virtual-desktop
```

### Method 2: Install from source

```bash
git clone https://github.com/unn-Known1/colab-virtual-desktop.git
cd colab-virtual-desktop
pip install -e .
```

### Method 3: In Google Colab notebook

```python
!pip install -q colab-virtual-desktop
```

---

## First Run

### Step 1: Open Google Colab

1. Go to [colab.research.google.com](https://colab.research.google.com)
2. Sign in with your Google account
3. Click **"New Notebook"**

### Step 2: Install and start

In the first cell, run:

```python
!pip install -q colab-virtual-desktop
```

In the next cell, start the desktop:

```python
from colab_desktop import start_virtual_desktop

desktop = start_virtual_desktop("YOUR_NGROK_TOKEN_HERE")
```

Replace `YOUR_NGROK_TOKEN_HERE` with the token you copied from ngrok.

### Step 3: Access the desktop

- A URL will be printed: `https://xxxx.ngrok-free.app/vnc.html`
- Click it (or run `desktop.open_in_browser()`)
- You should see the XFCE desktop in your browser!

---

## Using the Desktop

### Launching Applications

Once the desktop is running, you can launch any GUI app:

```python
# Launch Firefox browser
!firefox &

# Launch text editor
!gedit &

# Launch terminal
!xterm &

# Launch calculator
!xcalc &

# Run your Python GUI app
!python3 my_app.py
```

All applications will appear in the virtual desktop.

### Running Python GUI Frameworks

#### Tkinter
```python
import tkinter as tk
root = tk.Tk()
# ... your code ...
root.mainloop()
```

#### PyGame
```python
import pygame
pygame.init()
screen = pygame.display.set_mode((640, 480))
# ... your game code ...
```

#### PyQt / PySide
```python
from PyQt5 import QtWidgets
app = QtWidgets.QApplication([])
# ... your code ...
app.exec_()
```

---

## Command Line Usage

If you installed the package globally, you can use the CLI:

```bash
# Start desktop
colab-desktop --token YOUR_NGROK_TOKEN

# With custom settings
colab-desktop --token YOUR_TOKEN --geometry 1920x1080 --auto-open

# Check dependencies first
colab-desktop --check-deps
```

---

## Configuration Options

You can customize the desktop with these parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ngrok_auth_token` | (required) | Your ngrok auth token |
| `vnc_password` | `"colab123"` | VNC server password |
| `geometry` | `"1280x720"` | Screen resolution |
| `depth` | `24` | Color depth (bits) |
| `display` | `":1"` | X display number |
| `vnc_port` | `5901` | VNC server port |
| `novnc_port` | `6080` | noVNC web port |
| `ngrok_region` | `"us"` | ngrok region (us, eu, ap, au, sa, jp, in) |
| `auto_open` | `False` | Open browser automatically |

### Example with custom config

```python
desktop = ColabDesktop(
    ngrok_auth_token="YOUR_TOKEN",
    vnc_password="secure123",
    geometry="1920x1080",
    depth=16,  # Lower depth = better performance
    auto_open=True,
    ngrok_region="eu"  # European tunnel
)
desktop.setup()
desktop.start()
```

---

## Troubleshooting

### Issue: "Cannot connect to display"
**Solution:** Make sure you called `desktop.setup()` before `desktop.start()`.

### Issue: ngrok tunnel not connecting
**Solution:** Check your ngrok token is correct and has internet access.

### Issue: Black screen in browser
**Solution:** Wait 10-15 seconds for XFCE to fully start, then refresh the page.

### Issue: Port 6080 already in use
**Solution:** Use a different port: `colab-desktop --novnc-port 6081`

### Issue: Import errors after install
**Solution:** Restart the Colab runtime: Runtime → Restart runtime

### Issue: Slow performance
**Solution:**
- Use lower resolution: `--geometry 1024x768`
- Use lower color depth: `--depth 16`
- Close unnecessary applications

### Issue: Browser says "connection closed"
**Solution:** Colab VM may have timed out. Restart runtime and try again.

---

## Advanced Configuration

### Using Context Manager

```python
from colab_desktop import ColabDesktop

with ColabDesktop(ngrok_auth_token="YOUR_TOKEN") as desktop:
    print(f"URL: {desktop.get_url()}")
    # Desktop is running
    # ... your code ...
# Auto-stops when exiting the block
```

### Manual Process Control

```python
desktop = ColabDesktop(ngrok_auth_token="YOUR_TOKEN")

# Setup (install packages)
desktop.setup()

# Start services
desktop.start()

# Pause execution while desktop runs
import time
time.sleep(600)  # Keep alive for 10 minutes

# Stop when done
desktop.stop()
```

### Save/Load Session State

```python
import pickle

# Save configuration
state = {
    'display': desktop.display,
    'geometry': desktop.geometry,
    'vnc_port': desktop.vnc_port,
    # ... other state
}
with open('session.pkl', 'wb') as f:
    pickle.dump(state, f)

# Later, restore
with open('session.pkl', 'rb') as f:
    state = pickle.load(f)
# Recreate desktop with saved state
```

---

## Security Considerations

⚠️ **Important:**

1. **Public URL** - Anyone with the ngrok URL can access your desktop. Keep it secret!
2. **VNC Password** - Change from default: `--password YOUR_SECURE_PASS`
3. **ngrok Token** - Do not share your ngrok token publicly
4. **Colab VM** - Resets after ~12 hours. No persistence.
5. **Sensitive Data** - Don't store sensitive data on the VM. Download important work.
6. **Resource Limits** - Free Colab has limited CPU/RAM. Don't run heavy workloads.

---

## Performance Tips

- **Resolution:** Lower = faster. `1024x768` is decent, `800x600` is fast.
- **Color Depth:** 16-bit is faster than 24-bit.
- **Applications:** Lightweight apps (xterm, xclock) are snappy. Firefox may be slow.
- **Network:** ngrok adds latency. Midwest US = best if you're on US East Coast.

---

## Uninstall

### Remove package
```bash
pip uninstall colab-virtual-desktop
```

### Clean up (Colab)
Restart the runtime: **Runtime → Restart runtime**

---

## Getting Help

- **Documentation:** https://github.com/unn-Known1/colab-virtual-desktop#readme
- **Issues:** https://github.com/unn-Known1/colab-virtual-desktop/issues
- **Examples:** See the `examples/` directory in the repo

---

## What's Next?

After setting up, try these:

1. Run a browser on the desktop: `!firefox &`
2. Launch a code editor: `!gedit &`
3. Try Tkinter/PyGame examples (see `examples/` folder)
4. Develop and test GUI applications in Colab
5. Share the desktop URL with collaborators (same ngrok URL)

---

## Quick Reference Card

```python
# Install
!pip install colab-virtual-desktop

# Import
from colab_desktop import start_virtual_desktop, ColabDesktop

# One-liner (recommended)
desktop = start_virtual_desktop("NGROK_TOKEN", auto_open=True)

# Full control
desktop = ColabDesktop(ngrok_auth_token="TOKEN", geometry="1280x720")
desktop.setup()
desktop.start()
print(desktop.get_url())  # Open in browser

# Launch app
!firefox &

# Stop
desktop.stop()

# Context manager (auto-cleanup)
with ColabDesktop("TOKEN") as d:
    print(d.get_url())
```

---

Enjoy your virtual desktop in the cloud! 🚀
