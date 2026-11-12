"""Where KaupBudget keeps its data, and server-level options.

Everything is overridable with environment variables so the same code runs on
your PC or on an AWS EC2 instance:

    KAUP_DATA_DIR   folder for the database and receipt images
    KAUP_PASSWORD   if set, the app asks for this password (use it on EC2)
"""
import os
import sys
from pathlib import Path

APP_NAME = "KaupBudget"


def _default_data_dir() -> Path:
    if os.environ.get("KAUP_DATA_DIR"):
        return Path(os.environ["KAUP_DATA_DIR"]).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME / "data"
    return Path.home() / ".kaupbudget"


DATA_DIR = _default_data_dir()
DB_PATH = DATA_DIR / "kaupbudget.db"
RECEIPTS_DIR = DATA_DIR / "receipts"
PASSWORD = os.environ.get("KAUP_PASSWORD") or None
