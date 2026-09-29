"""Shared, side-effect-free JSON reader for the research page."""
import json
from pathlib import Path


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback

