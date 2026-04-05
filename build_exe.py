"""Build script to create a standalone Windows .exe using PyInstaller.

Run this on a Windows machine (or cross-compile environment):
    pip install pyinstaller anthropic
    python build_exe.py
"""

import subprocess
import sys
from pathlib import Path


def build():
    # Ensure PyInstaller is available
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Ensure anthropic SDK is available
    try:
        import anthropic
    except ImportError:
        print("Installing anthropic SDK...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic"])

    src_dir = Path(__file__).parent / "src" / "cnc_zh_map_maker"
    main_script = src_dir / "gui.py"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",  # No console window
        "--name", "ZH-Map-Maker",
        "--icon", "NONE",  # Add custom icon later if desired
        # Include all source modules
        "--add-data", f"{src_dir};cnc_zh_map_maker",
        # Hidden imports that PyInstaller might miss
        "--hidden-import", "cnc_zh_map_maker",
        "--hidden-import", "cnc_zh_map_maker.map_file",
        "--hidden-import", "cnc_zh_map_maker.builder",
        "--hidden-import", "cnc_zh_map_maker.binary_io",
        "--hidden-import", "cnc_zh_map_maker.data_model",
        "--hidden-import", "cnc_zh_map_maker.refpack",
        "--hidden-import", "cnc_zh_map_maker.ai_generator",
        "--hidden-import", "cnc_zh_map_maker.installer",
        "--hidden-import", "anthropic",
        # Collect the anthropic package properly
        "--collect-all", "anthropic",
        str(main_script),
    ]

    print(f"Building: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    print()
    print("=" * 60)
    print("Build complete!")
    print(f"Executable: dist/ZH-Map-Maker.exe")
    print("=" * 60)


if __name__ == "__main__":
    build()
