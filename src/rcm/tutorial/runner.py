"""LessonRunner: UI-agnostic state machine that walks a Lesson's steps."""

from __future__ import annotations

from dataclasses import dataclass

import chess

from rcm.tutorial.lessons import Lesson, Step
from rcm.tutorial.progress import Progress


@dataclass
class Attempt:
    ok: bool
    message: str
    step_done: bool = False
    reply: chess.Move | None = None  # opponent move the UI should show


class LessonRunner:
    def __init__(self, lesson: Lesson, progress: Progress | None = None):
        self.lesson = lesson
        self.progress = progress
        self.index = 0
        self.board = chess.Board()
        self.count = 0  # practice successes / line moves made
        self.misses = 0
        self.completed = False
        self._enter()

    # --- state -------------------------------------------------------
    @property
    def step(self) -> Step | None:
        return self.lesson.steps[self.index] if self.index < len(self.lesson.steps) else None

    @property
    def interactive(self) -> bool:
        return self.step is not None and self.step.type != "explain"

    def _enter(self) -> None:
        s = self.step
        self.count = 0
        self.misses = 0
        if s is None:
            return
        self.board = chess.Board(s.fen)
        if s.type == "line":
            self.board = chess.Board()
            self._auto_opponent()

    def _auto_opponent(self) -> None:
        """In a line, play the opponent's scripted moves until it is the user's turn."""
        s = self.step
        assert s is not None
        while self.count < len(s.moves) and self.board.turn != s.color:
            self.board.push_san(s.moves[self.count])
            self.count += 1

    def advance(self) -> bool:
        """Move to the next step (explain steps, or after an interactive step is done)."""
        self.index += 1
        if self.index >= len(self.lesson.steps):
            self.completed = True
            if self.progress:
                self.progress.mark_done(self.lesson.id)
            return False
        self._enter()
        return True

    def legal_targets(self, square: int) -> list[int]:
        s = self.step
        if s is None or s.type == "explain":
            return []
        return [m.to_square for m in self.board.legal_moves if m.from_square == square]

    def hint(self) -> str:
        s = self.step
        if s is None:
            return ""
        if s.type == "move":
            m = chess.Move.from_uci(s.accept[0])
            return s.hint or f"Try moving the piece on {chess.square_name(m.from_square)}."
        if s.type == "line":
            return f"Next move: {s.moves[self.count]}"
        return s.hint or "Pick the piece named in the lesson and move it."

    # --- attempts ----------------------------------------------------
    def attempt(self, move: chess.Move) -> Attempt:
        s = self.step
        if s is None or s.type == "explain":
            return Attempt(False, "Press Next to continue.")
        if move not in self.board.legal_moves:
            return Attempt(False, "That move is not legal here.")
        if s.type == "move":
            return self._attempt_move(s, move)
        if s.type == "practice":
            return self._attempt_practice(s, move)
        return self._attempt_line(s, move)

    def _miss(self, msg: str) -> Attempt:
        self.misses += 1
        return Attempt(False, msg)

    def _attempt_move(self, s: Step, move: chess.Move) -> Attempt:
        if move.uci() not in s.accept:
            return self._miss(
                "Not quite - look again." + (f" ({s.hint})" if self.misses >= 1 and s.hint else "")
            )
        self.board.push(move)
        reply = None
        if s.reply:
            reply = chess.Move.from_uci(s.reply)
            self.board.push(reply)
        return Attempt(True, s.why or "Correct!", step_done=True, reply=reply)

    def _attempt_practice(self, s: Step, move: chess.Move) -> Attempt:
        if self.board.piece_type_at(move.from_square) != s.piece:
            return self._miss("Move the piece named in the lesson.")
        self.count += 1
        if self.count >= s.count:
            return Attempt(True, f"{self.count}/{s.count} - well done!", step_done=True)
        self.board = chess.Board(s.fen)  # reset for the next repetition
        return Attempt(True, f"{self.count}/{s.count} - good, again from the start position.")

    def _attempt_line(self, s: Step, move: chess.Move) -> Attempt:
        expected = s.moves[self.count]
        if self.board.san(move) != expected:
            return self._miss("That is a legal move, but not the main line. Try again.")
        why = s.whys[sum(1 for i in range(self.count) if (i % 2 == 0) == (s.color == chess.WHITE))]
        self.board.push(move)
        self.count += 1
        reply = None
        if self.count < len(s.moves):
            reply = self.board.parse_san(s.moves[self.count])
            self.board.push(reply)
            self.count += 1
        done = self.count >= len(s.moves)
        return Attempt(True, why, step_done=done, reply=reply)
