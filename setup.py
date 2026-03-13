#!/usr/bin/env python3
"""
Setup script for colab-virtual-desktop

Build: python setup.py sdist bdist_wheel
Publish: pip install .
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding='utf-8') if readme_file.exists() else ""

# Read version
version_file = Path(__file__).parent / "colab_desktop" / "__init__.py"
version = "1.0.0"
if version_file.exists():
    for line in version_file.read_text().split('\n'):
        if line.startswith('__version__'):
            version = line.split('=')[1].strip().strip('"\'')
            break

setup(
    name="colab-virtual-desktop",
    version=version,
    author="AI Agent",
    author_email="agent@stepfun.com",
    description="Turn Google Colab into a remote desktop with VNC access",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/unn-Known1/colab-virtual-desktop",
    project_urls={
        "Bug Tracker": "https://github.com/unn-Known1/colab-virtual-desktop/issues",
        "Documentation": "https://github.com/unn-Known1/colab-virtual-desktop#readme",
    },
    packages=find_packages(exclude=["tests", "examples"]),
    install_requires=[
        "pyngrok>=3.0.0",
    ],
    extras_require={
        "dev": ["pytest", "black", "flake8"],
    },
    entry_points={
        "console_scripts": [
            "colab-desktop=colab_desktop.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: System :: Emulators",
        "Topic :: System :: Distributed Computing",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    keywords="colab google-colab vnc virtual-desktop remote-desktop gui xfce xvfb novnc ngrok",
)
