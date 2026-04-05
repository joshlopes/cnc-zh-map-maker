"""Auto-detect and install maps to the C&C Generals Zero Hour maps folder.

Handles Windows paths for:
- Steam version
- Origin/EA App version
- Classic retail version
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Optional


def get_zh_maps_folder() -> Optional[Path]:
    """Auto-detect the Zero Hour custom maps folder.

    Tries multiple known locations in order of likelihood.
    Returns None if no valid folder is found.
    """
    candidates = _get_candidate_paths()

    for path in candidates:
        if path.exists() and path.is_dir():
            return path

    # If the parent "Zero Hour Data" folder exists, create Maps inside it
    for path in candidates:
        parent = path.parent
        if parent.exists() and parent.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            return path

    return None


def _get_candidate_paths() -> list[Path]:
    """Get all candidate paths for the ZH maps folder."""
    paths = []

    if platform.system() == "Windows":
        # Standard Windows locations
        docs = _get_windows_documents()
        if docs:
            # Most common: My Documents\Command & Conquer Generals Zero Hour Data\Maps
            paths.append(docs / "Command & Conquer Generals Zero Hour Data" / "Maps")
            # Alternative naming
            paths.append(docs / "Command and Conquer Generals Zero Hour Data" / "Maps")

        # Also check USERPROFILE directly
        userprofile = os.environ.get("USERPROFILE", "")
        if userprofile:
            up = Path(userprofile)
            paths.append(up / "Documents" / "Command & Conquer Generals Zero Hour Data" / "Maps")
            paths.append(up / "My Documents" / "Command & Conquer Generals Zero Hour Data" / "Maps")

        # OneDrive Documents (some users have this)
        onedrive = os.environ.get("OneDrive", "")
        if onedrive:
            paths.append(Path(onedrive) / "Documents" / "Command & Conquer Generals Zero Hour Data" / "Maps")

    elif platform.system() == "Darwin":
        # macOS (Wine/CrossOver/Porting Kit)
        home = Path.home()
        paths.append(home / "Documents" / "Command & Conquer Generals Zero Hour Data" / "Maps")
        # Wine prefix common locations
        wine_docs = home / ".wine" / "drive_c" / "users" / os.getenv("USER", "") / "My Documents"
        paths.append(wine_docs / "Command & Conquer Generals Zero Hour Data" / "Maps")

    else:
        # Linux (Wine)
        home = Path.home()
        wine_docs = home / ".wine" / "drive_c" / "users" / os.getenv("USER", "") / "My Documents"
        paths.append(wine_docs / "Command & Conquer Generals Zero Hour Data" / "Maps")
        paths.append(home / "Documents" / "Command & Conquer Generals Zero Hour Data" / "Maps")

    return paths


def _get_windows_documents() -> Optional[Path]:
    """Get the Windows Documents folder path."""
    # Try the environment variable first
    docs = os.environ.get("USERPROFILE", "")
    if docs:
        p = Path(docs) / "Documents"
        if p.exists():
            return p
        p = Path(docs) / "My Documents"
        if p.exists():
            return p

    # Try known shell folder
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        personal, _ = winreg.QueryValueEx(key, "Personal")
        winreg.CloseKey(key)
        return Path(personal)
    except (ImportError, OSError):
        pass

    return None


def install_map(
    map_file_path: Path,
    maps_folder: Optional[Path] = None,
) -> Path:
    """Install a map to the game's maps folder.

    Args:
        map_file_path: Path to the .map file (expects MapName/MapName.map structure)
        maps_folder: Override the auto-detected maps folder

    Returns:
        Path to the installed map folder
    """
    if maps_folder is None:
        maps_folder = get_zh_maps_folder()
        if maps_folder is None:
            raise FileNotFoundError(
                "Could not find the Zero Hour maps folder. "
                "Please ensure the game is installed and has been run at least once."
            )

    map_dir = map_file_path.parent
    map_name = map_dir.name
    dest = maps_folder / map_name

    if dest.exists():
        shutil.rmtree(dest)

    shutil.copytree(map_dir, dest)
    return dest


def get_installed_maps(maps_folder: Optional[Path] = None) -> list[str]:
    """List all installed custom maps."""
    if maps_folder is None:
        maps_folder = get_zh_maps_folder()
        if maps_folder is None:
            return []

    maps = []
    for item in maps_folder.iterdir():
        if item.is_dir():
            map_file = item / f"{item.name}.map"
            if map_file.exists():
                maps.append(item.name)

    return sorted(maps)
