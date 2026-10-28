"""Shared by the helper scripts: finds the admin login and a demo password without storing any in source code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.config import ADMIN_EMAIL, ADMIN_PASSWORD, local_secret  # noqa: E402

DEMO_PASSWORD = __import__("os").getenv("DEMO_PASSWORD") or local_secret("DEMO_PASSWORD", 9)
