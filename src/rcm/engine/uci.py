"""Master: Stockfish (or any UCI engine) via python-chess."""

from __future__ import annotations

import os
import shutil

import chess
import chess.engine

from rcm.core import Game


def find_stockfish() -> str | None:
    env = os.environ.get("RCM_STOCKFISH")
    if env and os.path.exists(env):
        return env
    found = shutil.which("stockfish")
    if found:
        return found
    for p in ("/usr/games/stockfish", "/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish"):
        if os.path.exists(p):
            return p
    return None


class UciEngine:
    name = "Master"

    def __init__(self, path: str | list[str], think_time: float = 0.5, skill: int | None = None):
        self.think_time = think_time
        self._engine = chess.engine.SimpleEngine.popen_uci(path)
        if skill is not None and "Skill Level" in self._engine.options:
            self._engine.configure({"Skill Level": skill})

    def best_move(self, game: Game) -> chess.Move:
        result = self._engine.play(game.board, chess.engine.Limit(time=self.think_time))
        if result.move is None:
            raise ValueError("engine returned no move")
        return result.move

    def close(self) -> None:
        try:
            self._engine.quit()
        except Exception:
            pass
