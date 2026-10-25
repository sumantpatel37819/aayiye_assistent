"""Locate the installed Google Chrome on Linux, Windows, or macOS."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_chrome() -> str:
    for command in ("google-chrome", "google-chrome-stable", "chrome"):
        executable = shutil.which(command)
        if executable:
            return executable
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError("Google Chrome was not found. Install Chrome and ensure it is on PATH.")


def chrome_major_version() -> int | None:
    if sys.platform == "win32":
        return None  # Let the driver perform Windows version detection.
    result = subprocess.run([find_chrome(), "--version"], capture_output=True, text=True, check=True, timeout=10)
    match = re.search(r"(\d+)\.", result.stdout)
    if not match:
        raise RuntimeError("Could not detect the installed Chrome version.")
    return int(match.group(1))


def chrome_user_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "Google/Chrome/User Data"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Google/Chrome"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "google-chrome"


def assistant_profile_dir() -> Path:
    """Keep Linux Chrome locks on the native filesystem, away from exFAT repos."""
    if sys.platform.startswith("linux"):
        data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        return data_home / "aayie" / "playwright_profile"
    return Path(__file__).resolve().parent.parent / "playwright_profile"
