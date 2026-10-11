"""Lesson loader. Lessons are YAML in lessons/*.yaml; see docs/lessons.md for the format."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import chess
import yaml

from rcm import paths

STEP_TYPES = {"explain", "move", "practice", "line"}
PIECES = {
    "pawn": chess.PAWN,
    "knight": chess.KNIGHT,
    "bishop": chess.BISHOP,
    "rook": chess.ROOK,
    "queen": chess.QUEEN,
    "king": chess.KING,
}
GROUP_ORDER = ["Piece basics", "Special rules", "Openings", "Tactics"]


class LessonError(ValueError):
    pass


@dataclass
class Step:
    type: str
    text: str = ""
    fen: str = chess.STARTING_FEN
    accept: list[str] = field(default_factory=list)  # UCI
    reply: str | None = None
    why: str = ""
    hint: str = ""
    piece: int | None = None
    count: int = 1
    color: bool = chess.WHITE
    moves: list[str] = field(default_factory=list)  # SAN, both sides (line)
    whys: list[str] = field(default_factory=list)  # one per user move (line)


@dataclass
class Lesson:
    id: str
    group: str
    title: str
    steps: list[Step]
    path: Path | None = None


def _step(raw: dict, where: str) -> Step:
    t = raw.get("type")
    if t not in STEP_TYPES:
        raise LessonError(f"{where}: unknown step type {t!r}")
    s = Step(type=t, text=str(raw.get("text", raw.get("prompt", ""))).strip())
    s.fen = raw.get("fen", chess.STARTING_FEN)
    try:
        board = chess.Board(s.fen)
    except ValueError as e:
        raise LessonError(f"{where}: bad fen: {e}") from e
    s.why = str(raw.get("why", "")).strip()
    s.hint = str(raw.get("hint", "")).strip()
    if t == "move":
        s.accept = [str(a) for a in raw.get("accept", [])]
        if not s.accept:
            raise LessonError(f"{where}: move step needs accept")
        for u in s.accept:
            if chess.Move.from_uci(u) not in board.legal_moves:
                raise LessonError(f"{where}: accepted move {u} is illegal in {s.fen}")
        s.reply = raw.get("reply")
        if s.reply:
            b2 = board.copy()
            b2.push(chess.Move.from_uci(s.accept[0]))
            if chess.Move.from_uci(s.reply) not in b2.legal_moves:
                raise LessonError(f"{where}: reply {s.reply} is illegal")
    elif t == "practice":
        name = raw.get("piece")
        if name not in PIECES:
            raise LessonError(f"{where}: practice needs piece in {sorted(PIECES)}")
        s.piece = PIECES[name]
        s.count = int(raw.get("count", 3))
        if not any(board.piece_type_at(m.from_square) == s.piece for m in board.legal_moves):
            raise LessonError(f"{where}: no legal {name} move in {s.fen}")
    elif t == "line":
        s.color = chess.WHITE if raw.get("color", "white") == "white" else chess.BLACK
        s.moves = [str(m) for m in raw.get("moves", [])]
        b = chess.Board()
        for san in s.moves:
            try:
                b.push_san(san)
            except ValueError as e:
                raise LessonError(f"{where}: bad line move {san}: {e}") from e
        mine = sum(1 for i in range(len(s.moves)) if (i % 2 == 0) == (s.color == chess.WHITE))
        s.whys = [str(w) for w in raw.get("whys", [])]
        if len(s.whys) != mine:
            raise LessonError(f"{where}: need {mine} whys (one per user move), got {len(s.whys)}")
    return s


def load_lesson(path: Path) -> Lesson:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    where = path.name
    for key in ("id", "group", "title", "steps"):
        if key not in raw:
            raise LessonError(f"{where}: missing {key}")
    steps = [_step(s, f"{where} step {i + 1}") for i, s in enumerate(raw["steps"])]
    return Lesson(str(raw["id"]), str(raw["group"]), str(raw["title"]), steps, path)


def lessons_dir() -> Path:
    return paths.resource_root() / "lessons"


def load_lessons(directory: Path | None = None) -> list[Lesson]:
    out = [load_lesson(p) for p in sorted((directory or lessons_dir()).glob("*.yaml"))]
    ids = [lesson.id for lesson in out]
    if len(ids) != len(set(ids)):
        raise LessonError("duplicate lesson ids")

    def key(lesson: Lesson) -> tuple[int, str]:
        g = GROUP_ORDER.index(lesson.group) if lesson.group in GROUP_ORDER else 99
        return g, lesson.path.name if lesson.path else lesson.id

    return sorted(out, key=key)
