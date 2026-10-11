"""Game: board + move list + headers + end-of-game detection."""

from __future__ import annotations

import re
from dataclasses import dataclass

import chess

START_FEN = chess.STARTING_FEN
SEVEN_TAGS = ("Event", "Site", "Date", "Round", "White", "Black", "Result")
_CLK_RE = re.compile(r"\[%\w+[^\]]*\]")


@dataclass(frozen=True)
class GameEnd:
    result: str  # "1-0", "0-1", "1/2-1/2"
    reason: str  # checkmate, stalemate, repetition, fifty-move, insufficient material, resign...


def clean_comment(text: str) -> str:
    """Strip [%clk ...]-style annotations and surrounding whitespace."""
    return " ".join(_CLK_RE.sub("", text).split())


class Game:
    def __init__(self, fen: str | None = None, headers: dict[str, str] | None = None):
        self.board = chess.Board(fen or START_FEN)
        self.start_fen = self.board.fen()
        self.headers: dict[str, str] = {
            "Event": "Casual game",
            "Site": "rik-chess-master",
            "Date": "????.??.??",
            "Round": "-",
            "White": "White",
            "Black": "Black",
            "Result": "*",
        }
        if headers:
            self.headers.update(headers)
        self.comments: dict[int, str] = {}  # ply index (0-based) -> comment after that move
        self.forced_end: GameEnd | None = None  # resignation / agreed draw

    # --- moves -------------------------------------------------------
    @property
    def turn(self) -> bool:
        return self.board.turn

    @property
    def moves(self) -> list[chess.Move]:
        return list(self.board.move_stack)

    def san_moves(self) -> list[str]:
        replay = chess.Board(self.start_fen)
        out = []
        for m in self.board.move_stack:
            out.append(replay.san(m))
            replay.push(m)
        return out

    def legal_moves(self) -> list[chess.Move]:
        return list(self.board.legal_moves)

    def legal_targets(self, square: int) -> list[chess.Move]:
        return [m for m in self.board.legal_moves if m.from_square == square]

    def is_legal(self, move: chess.Move) -> bool:
        return move in self.board.legal_moves

    def push(self, move: chess.Move) -> str:
        """Play a legal move; returns its SAN. Raises ValueError if illegal or game over."""
        if self.is_over():
            raise ValueError("game is over")
        if not self.is_legal(move):
            raise ValueError(f"illegal move {move.uci()}")
        san = self.board.san(move)
        self.board.push(move)
        return san

    def push_san(self, san: str) -> chess.Move:
        if self.is_over():
            raise ValueError("game is over")
        move = self.board.parse_san(san)  # raises ValueError subclasses on illegal/ambiguous
        self.board.push(move)
        return move

    def push_uci(self, uci: str) -> str:
        return self.push(chess.Move.from_uci(uci))

    def pop(self) -> chess.Move:
        self.forced_end = None
        move = self.board.pop()
        self.comments.pop(len(self.board.move_stack), None)
        return move

    def needs_promotion(self, from_sq: int, to_sq: int) -> bool:
        return any(
            m.from_square == from_sq and m.to_square == to_sq and m.promotion
            for m in self.board.legal_moves
        )

    # --- end of game -------------------------------------------------
    def end(self) -> GameEnd | None:
        if self.forced_end:
            return self.forced_end
        b = self.board
        if b.is_checkmate():
            return GameEnd("0-1" if b.turn == chess.WHITE else "1-0", "checkmate")
        if b.is_stalemate():
            return GameEnd("1/2-1/2", "stalemate")
        if b.is_insufficient_material():
            return GameEnd("1/2-1/2", "insufficient material")
        if b.is_repetition(3):
            return GameEnd("1/2-1/2", "threefold repetition")
        if b.halfmove_clock >= 100:
            return GameEnd("1/2-1/2", "fifty-move rule")
        return None

    def is_over(self) -> bool:
        return self.end() is not None

    def resign(self, color: bool) -> GameEnd:
        self.forced_end = GameEnd("0-1" if color == chess.WHITE else "1-0", "resignation")
        return self.forced_end

    def agree_draw(self) -> GameEnd:
        self.forced_end = GameEnd("1/2-1/2", "draw agreed")
        return self.forced_end

    def result(self) -> str:
        e = self.end()
        return e.result if e else "*"

    def fen(self) -> str:
        return self.board.fen()

    def copy(self) -> Game:
        g = Game(self.start_fen, dict(self.headers))
        for m in self.board.move_stack:
            g.board.push(m)
        g.comments = dict(self.comments)
        g.forced_end = self.forced_end
        return g
