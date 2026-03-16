"""
Colab Virtual Desktop - Turn Google Colab into a remote desktop with VNC access

A complete solution for running GUI applications in Google Colab and accessing them
via browser using VNC + noVNC + ngrok tunneling.

Quick usage:
    from colab_desktop import start_virtual_desktop
    
    desktop = start_virtual_desktop("YOUR_NGROK_TOKEN")
    print(desktop.get_url())
    # Open URL in browser...
    # desktop.stop()

Advanced usage:
    from colab_desktop import ColabDesktop

    desktop = ColabDesktop(geometry="1280x720")
    desktop.setup()  # Install dependencies and start services
    desktop.start()  # Start XFCE, VNC, noVNC, ngrok
    print(desktop.get_url())  # Get the public URL
    desktop.open_in_browser()  # Optional: auto-open

    # When done
    desktop.stop()
"""

from .core import ColabDesktop
from .utils import is_colab, kill_processes_on_port, get_environment_summary
from .helpers import start_virtual_desktop, test_desktop, install_all_dependencies, PRESETS

__version__ = "1.0.0"
__author__ = "AI Agent"
__email__ = "agent@stepfun.com"

__all__ = [
    "ColabDesktop",
    "start_virtual_desktop",
    "test_desktop",
    "install_all_dependencies",
    "is_colab",
    "kill_processes_on_port",
    "get_environment_summary",
    "PRESETS"
]
