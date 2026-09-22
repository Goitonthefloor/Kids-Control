"""Make client package importable in tests without install."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client"
if str(CLIENT) not in sys.path:
    sys.path.insert(0, str(CLIENT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
