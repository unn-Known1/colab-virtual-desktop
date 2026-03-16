#!/usr/bin/env python3
"""
Command-line interface for Colab Virtual Desktop (Improved)

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
import signal
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from colab_desktop.core import ColabDesktop, is_colab
from colab_desktop.utils import get_environment_summary
from colab_desktop.helpers import quick_health_check


def signal_handler(signum, frame):
    """Handle signals for graceful shutdown"""
    print("\n\n🛑 Received interrupt signal. Shutting down...")
    sys.exit(130)


class ColabDesktopCLI:
    """Improved CLI with better error handling and user experience"""

    def __init__(self):
        self.desktop: Optional[ColabDesktop] = None
        self.setup_parser()

    def setup_parser(self):
        """Setup argument parser"""
        self.parser = argparse.ArgumentParser(
            description="Colab Virtual Desktop - Run GUI apps in Google Colab via browser",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s --token YOUR_NGROK_TOKEN
  %(prog)s --token YOUR_TOKEN --geometry 1920x1080 --auto-open
  %(prog)s --check-deps  # Check if dependencies are installed
  %(prog)s --preset hd  # Use HD preset configuration

Quick Start in Colab:
  1. Get ngrok token from https://ngrok.com
  2. Run: colab-desktop --token YOUR_TOKEN
  3. Open the printed URL in your browser

For more info: https://github.com/your-repo/colab-virtual-desktop
            """
        )

        self.parser.add_argument(
            '--token', '-t',
            help='ngrok auth token (get from https://ngrok.com)',
            default=os.environ.get('NGROK_AUTH_TOKEN')
        )
        self.parser.add_argument(
            '--geometry', '-g',
            help='Screen resolution (default: 1280x720)',
            default='1280x720'
        )
        self.parser.add_argument(
            '--depth',
            help='Color depth: 8, 16, 24, or 32 (default: 24)',
            type=int,
            default=24,
            choices=[8, 16, 24, 32]
        )
        self.parser.add_argument(
            '--vnc-port',
            help='VNC server port (default: 5901)',
            type=int,
            default=5901
        )
        self.parser.add_argument(
            '--novnc-port',
            help='noVNC web port (default: 6080)',
            type=int,
            default=6080
        )
        self.parser.add_argument(
            '--password', '-p',
            help='VNC password (min 8 chars, default: colab123)',
            default='colab123'
        )
        self.parser.add_argument(
            '--display', '-d',
            help='X display number (default: :1)',
            default=':1'
        )
        self.parser.add_argument(
            '--region', '-r',
            help='ngrok region (us, eu, ap, au, sa, jp, in)',
            default='us',
            choices=['us', 'eu', 'ap', 'au', 'sa', 'jp', 'in']
        )
        self.parser.add_argument(
            '--auto-open', '-a',
            help='Automatically open browser',
            action='store_true'
        )
        self.parser.add_argument(
            '--no-install',
            help='Skip dependency installation',
            action='store_true'
        )
        self.parser.add_argument(
            '--preset',
            help='Use a preset configuration (default, hd, low-res, performance, ultra-low)',
            choices=['default', 'hd', 'low-res', 'performance', 'ultra-low']
        )
        self.parser.add_argument(
            '--check-deps',
            help='Check if dependencies are installed and exit',
            action='store_true'
        )
        self.parser.add_argument(
            '--verbose', '-v',
            help='Verbose logging (show DEBUG messages)',
            action='store_true'
        )
        self.parser.add_argument(
            '--quiet', '-q',
            help='Quiet mode (only show essential output)',
            action='store_true'
        )
        self.parser.add_argument(
            '--version',
            help='Show version and exit',
            action='store_true'
        )
        self.parser.add_argument(
            '--health',
            help='Show health status after starting',
            action='store_true'
        )

    def run(self):
        """Main CLI entry point"""
        args = self.parser.parse_args()

        # Setup signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Configure logging level
        if args.quiet:
            os.environ['COLAB_DESKTOP_QUIET'] = '1'
        if args.verbose:
            os.environ['COLAB_DESKTOP_DEBUG'] = '1'

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

        # Colab warning
        if not env_summary['is_colab']:
            print("⚠️  WARNING: Not running in Google Colab.")
            print("   This tool is optimized for Google Colab.")
            print("   It may work in other environments but full compatibility is not guaranteed.")
            response = input("Continue anyway? (y/N): ").strip().lower()
            if response != 'y':
                sys.exit(1)

        # Check dependencies only
        if args.check_deps:
            self.check_dependencies()
            sys.exit(0)

        # Get ngrok token
        if not args.token:
            self.parser.error(
                "ngrok token required. Provide via --token or set NGROK_AUTH_TOKEN environment variable"
            )

        # Apply preset if specified
        if args.preset:
            from colab_desktop.helpers import PRESETS
            preset = PRESETS.get(args.preset)
            if preset:
                # Override geometry and depth from preset
                args.geometry = preset['geometry']
                args.depth = preset['depth']
                print(f"✅ Using preset '{args.preset}': {preset['description']}")
            else:
                print(f"⚠️  Unknown preset: {args.preset}, using defaults")

        # Create desktop instance
        try:
            self.desktop = ColabDesktop(
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
        except Exception as e:
            print(f"❌ Failed to create desktop instance: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

        # Run setup if needed
        if not args.no_install:
            print("\n" + "="*60)
            print("SETUP PHASE")
            print("="*60)
            if not self.desktop.setup():
                print("\n❌ Setup failed. Exiting.")
                sys.exit(1)
        else:
            print("Skipping setup (--no-install)")

        # Start desktop
        print("\n" + "="*60)
        print("STARTING VIRTUAL DESKTOP")
        print("="*60)

        if not self.desktop.start():
            print("\n❌ Failed to start desktop. Exiting.")
            sys.exit(1)

        # Show health if requested
        if args.health:
            print("\n" + quick_health_check(self.desktop))

        # Monitor until interrupted
        try:
            print("\n" + "="*60)
            print("✅ DESKTOP IS RUNNING")
            print("="*60)
            print("\nPress Ctrl+C to stop the virtual desktop...")
            print("Desktop URL:", self.desktop.get_url())
            print("="*60 + "\n")

            # Monitor loop
            while True:
                time.sleep(60)
                if self.desktop.is_running:
                    url = self.desktop.get_url()
                    timestamp = time.strftime("%H:%M:%S")
                    print(f"[{timestamp}] Desktop active: {url}")
                else:
                    print("Desktop stopped unexpectedly!")
                    break

        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down...")
        finally:
            self.shutdown()

    def check_dependencies(self):
        """Check and report on dependencies"""
        print("Checking dependencies...")
        print()

        desktop = ColabDesktop(
            install_deps=False,
            ngrok_auth_token="dummy"
        )

        missing = desktop.validate_environment()

        # Check system
        print("System packages:")
        system_ok = True
        for cmd in ['Xvfb', 'xset', 'vncserver', 'websockify']:
            found = desktop.runner.which(cmd) is not None
            icon = "✅" if found else "❌"
            print(f"  {icon} {cmd}")
            if not found:
                system_ok = False

        # Check desktop environments
        print("\nDesktop environments:")
        de = desktop._detect_desktop_environment()
        for env in ['xfce4', 'gnome', 'kde']:
            found = env in de
            icon = "✅" if found else "❌"
            print(f"  {icon} {env}")

        # Check Python packages
        print("\nPython packages:")
        try:
            import pyngrok
            print("  ✅ pyngrok")
        except ImportError:
            print("  ❌ pyngrok (install: pip install pyngrok)")
            system_ok = False

        print("\n" + "="*60)
        if missing:
            print("❌ Some dependencies are missing:")
            for m in missing:
                print(f"  - {m}")
            print("\nTo install automatically, run:")
            print("  colab-desktop --token YOUR_TOKEN")
            print("(without --no-install flag)")
            return False
        else:
            print("✅ All dependencies are installed!")
            return True

    def shutdown(self):
        """Clean shutdown"""
        if self.desktop:
            self.desktop.stop()
        print("✅ Virtual desktop stopped")
        sys.exit(0)


def main():
    """Entry point"""
    try:
        cli = ColabDesktopCLI()
        cli.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()