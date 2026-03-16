"""
Helper functions for quick setup in Colab notebooks

These functions can be directly pasted into a Colab cell for one-liner setup.
"""

from .core import ColabDesktop


def start_virtual_desktop(
    ngrok_token: str,
    auto_open: bool = True,
    geometry: str = "1280x720",
    **kwargs
) -> ColabDesktop:
    """
    Quick one-liner to start virtual desktop in Colab

    Usage in Colab:
        from colab_desktop import start_virtual_desktop
        desktop = start_virtual_desktop("YOUR_NGROK_TOKEN")

    Then open desktop.url in browser.

    Args:
        ngrok_token: Your ngrok auth token
        auto_open: Open browser automatically
        geometry: Screen resolution
        **kwargs: Additional ColabDesktop options

    Returns:
        Running ColabDesktop instance
    """
    desktop = ColabDesktop(
        ngrok_auth_token=ngrok_token,
        geometry=geometry,
        auto_open=auto_open,
        **kwargs
    )

    print("🚀 Setting up virtual desktop...")
    if not desktop.setup():
        raise RuntimeError("Setup failed - check logs")

    print("▶️ Starting services...")
    if not desktop.start():
        raise RuntimeError("Start failed - check logs")

    return desktop


def test_desktop() -> str:
    """
    Launch a test application on the virtual desktop

    This function should be called after desktop.start() to verify GUI works.

    Returns:
        Status message
    """
    try:
        # Test with xclock (simple X11 app)
        import subprocess
        subprocess.Popen(["xclock"], env={"DISPLAY": ":1"})
        return "✅ xclock launched - you should see a clock on the desktop"
    except Exception as e:
        return f"❌ Failed to launch test app: {e}"


def install_all_dependencies() -> bool:
    """
    Install all required system and Python dependencies

    This can be called at the top of your Colab notebook.

    Returns:
        True if successful
    """
    desktop = ColabDesktop(install_deps=True, ngrok_auth_token="dummy")
    return desktop.setup()


# Pre-defined configurations for common use cases
PRESETS = {
    'default': {
        'geometry': '1280x720',
        'depth': 24,
        'description': 'Standard HD desktop'
    },
    'hd': {
        'geometry': '1920x1080',
        'depth': 24,
        'description': 'Full HD desktop (more resources)'
    },
    'low-res': {
        'geometry': '1024x768',
        'depth': 16,
        'description': 'Low resolution for faster performance'
    },
    'performance': {
        'geometry': '1280x720',
        'depth': 16,
        'description': 'Optimized for performance'
    },
}