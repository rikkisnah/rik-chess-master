import random

import chess

from rcm.core import Game


class RandomEngine:
    """Beginner: random legal move, preferring captures."""

    name = "Beginner"

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def best_move(self, game: Game) -> chess.Move:
        moves = game.legal_moves()
        if not moves:
            raise ValueError("no legal moves")
        captures = [m for m in moves if game.board.is_capture(m)]
        pool = captures if captures and self.rng.random() < 0.75 else moves
        return self.rng.choice(pool)

    def close(self) -> None:
        pass
