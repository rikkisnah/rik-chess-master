"""Engine protocol, level factory, and the worker thread that keeps the UI responsive."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

import chess

from rcm.core import Game

LEVELS = ("beginner", "club", "master")
INSTALL_HINT = "Install it with `make stockfish` (or set RCM_STOCKFISH=/path/to/stockfish)."


class Engine(Protocol):
    name: str

    def best_move(self, game: Game) -> chess.Move: ...

    def close(self) -> None: ...


def make_engine(level: str, seed: int | None = None, depth: int = 3) -> tuple[Engine, str | None]:
    """Return (engine, notice). Master falls back to Club when Stockfish is missing."""
    from rcm.engine.minimax import MinimaxEngine
    from rcm.engine.random_engine import RandomEngine
    from rcm.engine.uci import UciEngine, find_stockfish

    if level == "beginner":
        return RandomEngine(seed), None
    if level == "club":
        return MinimaxEngine(depth=depth, seed=seed), None
    if level == "master":
        path = find_stockfish()
        if path:
            try:
                return UciEngine(path), None
            except Exception as e:  # engine failed to start
                return MinimaxEngine(depth=depth, seed=seed), (
                    f"Stockfish failed to start ({e}); using Club level."
                )
        return MinimaxEngine(depth=depth, seed=seed), (
            f"Stockfish not found; using Club level instead. {INSTALL_HINT}"
        )
    raise ValueError(f"unknown level {level!r}")


class EngineWorker:
    """Runs engine.best_move on a background thread; delivers via callback(move | Exception).

    A generation counter discards stale answers (e.g. after undo or new game)."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self._gen = 0
        self._lock = threading.Lock()

    def request(self, game: Game, callback: Callable[[chess.Move | Exception], None]) -> None:
        snapshot = game.copy()
        with self._lock:
            self._gen += 1
            gen = self._gen

        def run() -> None:
            try:
                result: chess.Move | Exception = self.engine.best_move(snapshot)
            except Exception as e:
                result = e
            with self._lock:
                if gen != self._gen:
                    return
            callback(result)

        threading.Thread(target=run, daemon=True, name="rcm-engine").start()

    def cancel(self) -> None:
        with self._lock:
            self._gen += 1

    def close(self) -> None:
        self.cancel()
        self.engine.close()
