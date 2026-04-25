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

    # Path-separator for --add-data is OS-dependent (Windows uses ';', POSIX ':')
    sep = ";" if sys.platform == "win32" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",  # No console window
        "--name", "ZH-Map-Maker",
        "--icon", "NONE",
        "--add-data", f"{src_dir}{sep}cnc_zh_map_maker",
        # Hidden imports that PyInstaller might miss
        "--hidden-import", "cnc_zh_map_maker",
        "--hidden-import", "cnc_zh_map_maker.map_file",
        "--hidden-import", "cnc_zh_map_maker.builder",
        "--hidden-import", "cnc_zh_map_maker.binary_io",
        "--hidden-import", "cnc_zh_map_maker.data_model",
        "--hidden-import", "cnc_zh_map_maker.refpack",
        "--hidden-import", "cnc_zh_map_maker.ai_generator",
        "--hidden-import", "cnc_zh_map_maker.installer",
        "--hidden-import", "cnc_zh_map_maker.gui",
        "--hidden-import", "anthropic",
        "--collect-all", "anthropic",
        # Force-bundle Tcl/Tk runtime so the GUI actually launches on Windows.
        # Without this, _tkinter.pyd loads but the tcl86t.dll / tk86t.dll plus
        # the tcl/ and tk/ library folders are missing and import crashes at startup.
        "--collect-all", "tkinter",
        # Drop heavy deps PyInstaller pulls in transitively but the app doesn't use
        "--exclude-module", "numpy",
        "--exclude-module", "PIL",
        "--exclude-module", "Pillow",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
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
