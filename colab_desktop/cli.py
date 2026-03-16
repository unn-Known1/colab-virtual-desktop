#!/usr/bin/env python3
"""
Command-line interface for Colab Virtual Desktop

Usage:
    colab-desktop [OPTIONS]

Examples:
    colab-desktop --token YOUR_NGROK_TOKEN
    colab-desktop --token YOUR_TOKEN --geometry 1920x1080 --auto-open
    colab-desktop --check-deps  # Check if dependencies are installed
"""

import argparse
import sys
import os
from pathlib import Path

# Add parent directory to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent))

from colab_desktop import ColabDesktop, is_colab
from colab_desktop.utils import get_environment_summary


def main():
    parser = argparse.ArgumentParser(
        description="Colab Virtual Desktop - Run GUI apps in Google Colab via browser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --token YOUR_NGROK_TOKEN
  %(prog)s --token YOUR_TOKEN --geometry 1920x1080 --auto-open
  %(prog)s --check-deps  # Check if dependencies are installed
        """
    )

    parser.add_argument(
        '--token', '-t',
        help='ngrok auth token (get from https://ngrok.com)',
        default=os.environ.get('NGROK_AUTH_TOKEN')
    )
    parser.add_argument(
        '--geometry', '-g',
        help='Screen resolution (default: 1280x720)',
        default='1280x720'
    )
    parser.add_argument(
        '--password', '-p',
        help='VNC password (default: colab123)',
        default='colab123'
    )
    parser.add_argument(
        '--display', '-d',
        help='X display number (default: :1)',
        default=':1'
    )
    parser.add_argument(
        '--depth',
        help='Color depth (default: 24)',
        type=int,
        default=24
    )
    parser.add_argument(
        '--vnc-port',
        help='VNC server port (default: 5901)',
        type=int,
        default=5901
    )
    parser.add_argument(
        '--novnc-port',
        help='noVNC web port (default: 6080)',
        type=int,
        default=6080
    )
    parser.add_argument(
        '--region', '-r',
        help='ngrok region (default: us)',
        default='us'
    )
    parser.add_argument(
        '--auto-open', '-a',
        help='Automatically open browser',
        action='store_true'
    )
    parser.add_argument(
        '--no-install',
        help='Skip dependency installation',
        action='store_true'
    )
    parser.add_argument(
        '--check-deps',
        help='Check if dependencies are installed and exit',
        action='store_true'
    )
    parser.add_argument(
        '--verbose', '-v',
        help='Verbose logging',
        action='store_true'
    )
    parser.add_argument(
        '--version',
        help='Show version and exit',
        action='store_true'
    )

    args = parser.parse_args()

    # Version
    if args.version:
        from colab_desktop import __version__
        print(f"Colab Virtual Desktop v{__version__}")
        print("A tool to create a virtual desktop in Google Colab")
        sys.exit(0)

    # Environment check
    env_summary = get_environment_summary()
    if args.verbose:
        print("Environment:")
        for k, v in env_summary.items():
            print(f"  {k}: {v}")

    # Check if in Colab
    if not env_summary['is_colab']:
        print("⚠️  WARNING: Not running in Google Colab.")
        print("   This tool is designed for Google Colab and may not work elsewhere.")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)

    # Check dependencies
    if args.check_deps:
        print("Checking dependencies...")
        deps_ok = True

        # Check apt packages
        required_packages = ['xvfb', 'vncserver', 'websockify', 'xfce4']
        for pkg in required_packages:
            code, _, _ = run_command(f"which {pkg}", capture=True)
            status = "✓" if code == 0 else "✗"
            print(f"  {status} {pkg}")
            if code != 0:
                deps_ok = False

        # Check Python packages
        try:
            import pyngrok
            print("  ✓ pyngrok")
        except ImportError:
            print("  ✗ pyngrok (install: pip install pyngrok)")
            deps_ok = False

        if deps_ok:
            print("\n✅ All dependencies are installed!")
        else:
            print("\n❌ Some dependencies are missing. Run without --check-deps to install automatically.")

        sys.exit(0 if deps_ok else 1)

    # Get ngrok token
    if not args.token:
        parser.error("ngrok token required. Provide via --token or set NGROK_AUTH_TOKEN environment variable")

    # Create desktop instance
    desktop = ColabDesktop(
        ngrok_auth_token=args.token,
        vnc_password=args.password,
        display=args.display,
        geometry=args.geometry,
        depth=args.depth,
        vnc_port=args.vnc_port,
        novnc_port=args.novnc_port,
        ngrok_region=args.region,
        auto_open=args.auto_open,
        install_deps=not args.no_install,
    )

    # Run setup if needed
    if not args.no_install:
        if not desktop.setup():
            print("❌ Setup failed. Exiting.")
            sys.exit(1)

    # Start desktop
    if not desktop.start():
        print("❌ Failed to start desktop. Exiting.")
        sys.exit(1)

    # Keep running until interrupted
    try:
        print("\nPress Ctrl+C to stop the virtual desktop...")
        while True:
            # Show status periodically
            import time
            time.sleep(60)
            url = desktop.get_url()
            if url:
                print(f"[{time.strftime('%H:%M:%S')}] Desktop active: {url}")
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        desktop.stop()
        print("✅ Virtual desktop stopped")
        sys.exit(0)


def run():
    """Entry point for the CLI"""
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        if '--verbose' in sys.argv:
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    run()
