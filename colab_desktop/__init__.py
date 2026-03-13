"""
Colab Virtual Desktop - Turn Google Colab into a remote desktop with VNC access

A complete solution for running GUI applications in Google Colab and accessing them
via browser using VNC + noVNC + ngrok tunneling.

Example usage:
    from colab_desktop import ColabDesktop

    desktop = ColabDesktop()
    desktop.setup()  # Install dependencies and start services
    desktop.start()  # Start XFCE, VNC, noVNC, ngrok
    print(desktop.url)  # Get the public URL

    # Open the URL in browser to see desktop
    # desktop.open_in_browser()

    # When done
    desktop.stop()
"""

from .core import ColabDesktop
from .utils import is_colab, kill_processes_on_port, get_environment_summary

__version__ = "1.0.0"
__author__ = "AI Agent"
__email__ = "agent@stepfun.com"

__all__ = ["ColabDesktop", "is_colab", "kill_processes_on_port", "get_environment_summary"]
