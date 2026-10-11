"""Optional "Explain this move": asks Claude to describe the last move in plain language.

Stockfish/Club still choose every move. This only writes commentary, and only when the user
clicks the button, so the position is sent to the Anthropic API on request and never otherwise.

Settings come from environment variables, then from KEY=value lines in
``~/.config/rik-chess-master/anthropic.env`` (override the folder with ``RCM_CONFIG_DIR``)::

    ANTHROPIC_API_KEY=sk-ant-...
    ANTHROPIC_MODEL=claude-sonnet-5-5
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import chess

from rcm.core import Game

DEFAULT_MODEL = "claude-sonnet-5-5"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
ENV_FILE = "anthropic.env"
LEGACY_KEY_FILE = "anthropic_api_key"  # a file holding just the bare key
SETUP_HINT = (
    "Explain is off. Put ANTHROPIC_API_KEY=... (and optionally ANTHROPIC_MODEL=...) "
    f"in ~/.config/rik-chess-master/{ENV_FILE}, or set them in the environment."
)

SYSTEM = (
    "You are a friendly chess coach for a beginner. You are given a position and the move just "
    "played. In 2-4 short sentences explain what the move does and why it is good, bad or "
    "ordinary. Mention only what you can verify from the position given; if unsure, say so. "
    "Do not invent variations. Plain text only."
)


class ExplainError(Exception):
    """A user-presentable failure. Never contains the API key."""


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    model: str = DEFAULT_MODEL

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def config_dir() -> Path:
    env = os.environ.get("RCM_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".config" / "rik-chess-master"


def parse_env(text: str) -> dict[str, str]:
    """KEY=value lines. Accepts `export`, quotes and # comments; a bare sk-... line is the key."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            if line.startswith("sk-"):
                out["ANTHROPIC_API_KEY"] = line
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        out[key.strip()] = value
    return out


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    values: dict[str, str] = {}
    for name in (LEGACY_KEY_FILE, ENV_FILE):  # the .env file wins over the bare-key file
        try:
            values.update(parse_env((config_dir() / name).read_text(encoding="utf-8")))
        except OSError:
            pass
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
        if env.get(k):
            values[k] = env[k]
    return Settings(
        api_key=values.get("ANTHROPIC_API_KEY") or None,
        model=values.get("ANTHROPIC_MODEL") or DEFAULT_MODEL,
    )


def build_prompt(game: Game) -> str:
    board = game.board.copy(stack=True)
    last = board.pop()
    san = board.san(last)
    mover = "White" if board.turn == chess.WHITE else "Black"
    after = game.board
    notes = []
    if after.is_checkmate():
        notes.append("It is checkmate.")
    elif after.is_check():
        notes.append("It gives check.")
    if board.is_capture(last):
        notes.append("It is a capture.")
    return (
        f"Position before the move (FEN): {board.fen()}\n"
        f"{mover} played {san}.\n"
        f"Position after (FEN): {after.fen()}\n"
        f"Moves so far: {' '.join(game.san_moves())}\n" + " ".join(notes)
    ).strip()


Sender = Callable[[dict, str], dict]


def _http_send(body: dict, api_key: str) -> dict:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read())["error"]["message"]
        except Exception:
            detail = e.reason
        hint = " Check ANTHROPIC_API_KEY." if e.code in (401, 403) else ""
        raise ExplainError(f"Claude API error {e.code}: {detail}.{hint}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ExplainError(f"Cannot reach the Claude API: {getattr(e, 'reason', e)}") from None


def explain_last_move(game: Game, settings: Settings, send: Sender = _http_send) -> str:
    if not settings.enabled:
        raise ExplainError(SETUP_HINT)
    if not game.moves:
        raise ExplainError("Play a move first.")
    body = {
        "model": settings.model,
        "max_tokens": 400,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": build_prompt(game)}],
    }
    reply = send(body, settings.api_key or "")
    try:
        text = "".join(b["text"] for b in reply["content"] if b.get("type") == "text").strip()
    except (KeyError, TypeError):
        raise ExplainError("Unexpected reply from the Claude API.") from None
    if not text:
        raise ExplainError("Claude returned no text.")
    return text
