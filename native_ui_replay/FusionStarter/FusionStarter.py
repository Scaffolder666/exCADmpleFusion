"""Fusion Scripts and Add-Ins entrypoint. Select THIS FOLDER with the + button."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fusion_starter import run  # noqa: E402
