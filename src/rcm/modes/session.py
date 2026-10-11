"""Session: the UI-agnostic controller shared by every playable mode."""

from __future__ import annotations

import queue
from collections.abc import Callable
from datetime import date
from pathlib import Path

import chess

from rcm import paths
from rcm.core import Game, read_file, write_file


class Session:
    mode = "local"

    def __init__(
        self,
        game: Game | None = None,
        autosave: Path | None | bool = True,
    ):
        self.game = game or Game(headers={"Date": date.today().strftime("%Y.%m.%d")})
        self.autosave = paths.autosave_path() if autosave is True else (autosave or None)
        self.listeners: list[Callable[[], None]] = []
        self.message = ""
        self._inbox: queue.Queue[Callable[[], None]] = queue.Queue()
        self.game.headers["RCM_Mode"] = self.mode

    # --- observers ---------------------------------------------------
    def notify(self) -> None:
        for fn in list(self.listeners):
            fn()

    def pump(self) -> None:
        """Run work queued by background threads. The UI calls this on a timer."""
        while True:
            try:
                fn = self._inbox.get_nowait()
            except queue.Empty:
                return
            fn()

    def post(self, fn: Callable[[], None]) -> None:
        self._inbox.put(fn)

    # --- state -------------------------------------------------------
    @property
    def board(self) -> chess.Board:
        return self.game.board

    @property
    def turn(self) -> bool:
        return self.game.turn

    def user_can_move(self) -> bool:
        """True when a person may move for the side to play."""
        return not self.game.is_over()

    def status(self) -> str:
        end = self.game.end()
        if end:
            return f"Game over: {end.reason} ({end.result})"
        side = "White" if self.turn == chess.WHITE else "Black"
        check = " - check!" if self.board.is_check() else ""
        return f"{side} to move{check}"

    # --- moves -------------------------------------------------------
    def legal_targets(self, square: int) -> list[chess.Move]:
        return self.game.legal_targets(square) if self.user_can_move() else []

    def move(self, from_sq: int, to_sq: int, promotion: int | None = None) -> bool:
        if not self.user_can_move():
            return False
        if self.game.needs_promotion(from_sq, to_sq) and promotion is None:
            promotion = chess.QUEEN
        mv = chess.Move(from_sq, to_sq, promotion)
        if not self.game.is_legal(mv):
            return False
        self.apply(mv)
        return True

    def apply(self, mv: chess.Move) -> str:
        san = self.game.push(mv)
        self.after_move(san)
        return san

    def after_move(self, san: str) -> None:
        self.save_autosave()
        self.notify()

    def resign(self, color: bool | None = None) -> None:
        self.game.resign(self.turn if color is None else color)
        self.after_move("resign")

    def undo(self) -> bool:
        if not self.game.moves:
            return False
        self.game.pop()
        self.save_autosave()
        self.notify()
        return True

    # --- persistence -------------------------------------------------
    def save_autosave(self) -> None:
        if self.autosave:
            try:
                write_file(self.game, self.autosave, overwrite=True)
            except OSError:
                pass  # autosave is best-effort

    def save(self, path: str | Path, overwrite: bool = False) -> None:
        """Raises FileExistsError unless overwrite=True (the UI prompts first)."""
        write_file(self.game, path, overwrite=overwrite)

    @staticmethod
    def load_game(path: str | Path) -> Game:
        return read_file(path)

    def close(self) -> None:
        pass
