"""BoardView: the one board widget shared by every mode."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import chess

from rcm import paths

LIGHT, DARK = "#f0d9b5", "#b58863"
SEL, TARGET, LAST, HINT, CHECK = "#f7ec74", "#6fb36f", "#cdd26a", "#5aa0e6", "#e05a5a"
SQUARE = 80

_image_cache: dict[tuple[int, str], tk.PhotoImage] = {}


def piece_image(master: tk.Misc, piece: chess.Piece) -> tk.PhotoImage:
    name = ("w" if piece.color else "b") + piece.symbol().upper()
    key = (id(master.winfo_toplevel()), name)
    if key not in _image_cache:
        path = paths.resource_root() / "assets" / "pieces" / f"{name}.png"
        _image_cache[key] = tk.PhotoImage(master=master, file=str(path))
    return _image_cache[key]


class BoardView(tk.Canvas):
    def __init__(self, master: tk.Misc, on_square: Callable[[int], None] | None = None):
        size = SQUARE * 8
        super().__init__(master, width=size + 24, height=size + 24, highlightthickness=0)
        self.on_square = on_square
        self.flipped = False
        self.board = chess.Board()
        self.selected: int | None = None
        self.targets: set[int] = set()
        self.last_move: chess.Move | None = None
        self.hint_move: chess.Move | None = None
        self.interactive = True
        self.bind("<Button-1>", self._click)
        self.render()

    # --- geometry ----------------------------------------------------
    def square_xy(self, sq: int) -> tuple[int, int]:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        col = 7 - f if self.flipped else f
        row = r if self.flipped else 7 - r
        return 12 + col * SQUARE, row * SQUARE

    def square_at(self, x: float, y: float) -> int | None:
        col, row = int((x - 12) // SQUARE), int(y // SQUARE)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        f = 7 - col if self.flipped else col
        r = row if self.flipped else 7 - row
        return chess.square(f, r)

    def _click(self, e: tk.Event) -> None:
        sq = self.square_at(e.x, e.y)
        if sq is not None and self.on_square and self.interactive:
            self.on_square(sq)

    # --- drawing -----------------------------------------------------
    def set_state(
        self,
        board: chess.Board,
        *,
        flipped: bool | None = None,
        last_move: chess.Move | None = None,
        selected: int | None = None,
        targets=(),
        hint_move: chess.Move | None = None,
    ) -> None:
        self.board = board
        if flipped is not None:
            self.flipped = flipped
        self.last_move, self.selected = last_move, selected
        self.targets, self.hint_move = set(targets), hint_move
        self.render()

    def render(self) -> None:
        self.delete("all")
        b = self.board
        check_sq = b.king(b.turn) if b.is_check() else None
        for sq in chess.SQUARES:
            x, y = self.square_xy(sq)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            colour = LIGHT if light else DARK
            if self.last_move and sq in (self.last_move.from_square, self.last_move.to_square):
                colour = LAST
            if sq == self.selected:
                colour = SEL
            if sq == check_sq:
                colour = CHECK
            if self.hint_move and sq in (self.hint_move.from_square, self.hint_move.to_square):
                colour = HINT
            self.create_rectangle(x, y, x + SQUARE, y + SQUARE, fill=colour, outline="")
            p = b.piece_at(sq)
            if p:
                self.create_image(x + SQUARE // 2, y + SQUARE // 2, image=piece_image(self, p))
            if sq in self.targets:
                cx, cy = x + SQUARE // 2, y + SQUARE // 2
                r = 10 if not p else SQUARE // 2 - 6
                self.create_oval(
                    cx - r,
                    cy - r,
                    cx + r,
                    cy + r,
                    fill="" if p else TARGET,
                    outline=TARGET,
                    width=4 if p else 1,
                )
        # coordinates
        for i in range(8):
            f = 7 - i if self.flipped else i
            r = i if self.flipped else 7 - i
            self.create_text(
                12 + i * SQUARE + SQUARE // 2,
                SQUARE * 8 + 12,
                text="abcdefgh"[f],
                font=("TkDefaultFont", 9),
            )
            self.create_text(
                6, i * SQUARE + SQUARE // 2, text=str(r + 1), font=("TkDefaultFont", 9)
            )
