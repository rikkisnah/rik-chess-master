"""Famous Games: step through a bundled PGN with auto-play and commentary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chess

from rcm import paths
from rcm.core import Game, PgnError, read_file


@dataclass
class GameInfo:
    path: Path
    title: str
    white: str
    black: str
    date: str
    result: str


def games_dir() -> Path:
    return paths.resource_root() / "games"


def list_games(directory: Path | None = None) -> list[GameInfo]:
    out = []
    for p in sorted((directory or games_dir()).glob("*.pgn")):
        try:
            g = read_file(p)
        except (PgnError, OSError):
            continue
        h = g.headers
        out.append(
            GameInfo(
                p,
                h.get("Event", p.stem),
                h.get("White", "?"),
                h.get("Black", "?"),
                h.get("Date", ""),
                h.get("Result", "*"),
            )
        )
    return out


class ReplaySession:
    """Read-only. `position` = number of plies played from the start (0..len)."""

    mode = "famous_game"

    def __init__(self, game: Game, interval: float = 2.0):
        self.source = game
        self.moves = game.moves
        self.position = 0
        self.interval = interval
        self.playing = False
        self.view = Game(game.start_fen, dict(game.headers))
        self.listeners = []

    @classmethod
    def from_path(cls, path: str | Path, **kw) -> ReplaySession:
        return cls(read_file(path), **kw)

    def notify(self) -> None:
        for fn in list(self.listeners):
            fn()

    @property
    def board(self) -> chess.Board:
        return self.view.board

    @property
    def finished(self) -> bool:
        return self.position >= len(self.moves)

    def goto(self, n: int) -> None:
        n = max(0, min(n, len(self.moves)))
        while self.position > n:
            self.view.board.pop()
            self.position -= 1
        while self.position < n:
            self.view.board.push(self.moves[self.position])
            self.position += 1
        if self.finished:
            self.playing = False
        self.notify()

    def forward(self) -> bool:
        if self.finished:
            return False
        self.goto(self.position + 1)
        return True

    def back(self) -> bool:
        if self.position == 0:
            return False
        self.goto(self.position - 1)
        return True

    def set_interval(self, seconds: float) -> None:
        self.interval = max(0.2, min(10.0, seconds))

    def play(self) -> None:
        if self.finished:
            self.goto(0)
        self.playing = True
        self.notify()

    def pause(self) -> None:
        self.playing = False
        self.notify()

    def tick(self) -> None:
        """Called by the UI timer every `interval` seconds while playing."""
        if self.playing:
            self.forward()

    @property
    def last_move(self) -> chess.Move | None:
        return self.moves[self.position - 1] if self.position else None

    @property
    def commentary(self) -> str:
        """Comment attached to the last played move (empty if none)."""
        return self.source.comments.get(self.position - 1, "") if self.position else ""

    def move_label(self) -> str:
        if not self.position:
            return "Start position"
        sans = self.source.san_moves()
        n = (self.position + 1) // 2
        dots = "." if self.position % 2 == 1 else "..."
        return f"{n}{dots} {sans[self.position - 1]}"

    def close(self) -> None:
        self.playing = False
