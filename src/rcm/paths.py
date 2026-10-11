"""Filesystem locations: user data dir and bundled resources."""

from __future__ import annotations

import json
import os
from pathlib import Path


def data_dir() -> Path:
    d = Path(os.environ.get("RCM_HOME", Path.home() / ".rik-chess-master"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def autosave_path() -> Path:
    return data_dir() / "autosave.pgn"


def progress_path() -> Path:
    return data_dir() / "progress.json"


def config_path() -> Path:
    return data_dir() / "config.json"


def resource_root() -> Path:
    """Directory holding lessons/, games/, assets/ (repo root, or RCM_RESOURCES)."""
    env = os.environ.get("RCM_RESOURCES")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "lessons").is_dir() and (parent / "games").is_dir():
            return parent
    return here.parents[2]


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    config_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")


DEFAULT_RELAY_URL = "ws://127.0.0.1:8790"


def relay_url() -> str:
    return os.environ.get("RCM_RELAY_URL") or load_config().get("relay_url", DEFAULT_RELAY_URL)
