"""PGN read/write with RCM_* app tags."""

from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path

import chess
import chess.pgn

from rcm.core.game import SEVEN_TAGS, Game, GameEnd, clean_comment


class PgnError(ValueError):
    """Raised when a PGN cannot be loaded; message says which move failed."""


def dumps(game: Game, saved: datetime | None = None) -> str:
    out = chess.pgn.Game()
    headers = dict(game.headers)
    headers["Result"] = game.result()
    headers["RCM_Saved"] = (saved or datetime.now().astimezone()).isoformat(timespec="seconds")
    ordered = {k: headers.pop(k) for k in SEVEN_TAGS if k in headers}
    ordered.update(headers)
    for k, v in ordered.items():
        out.headers[k] = v
    if game.start_fen != chess.STARTING_FEN:
        out.headers["SetUp"] = "1"
        out.headers["FEN"] = game.start_fen
        out.setup(chess.Board(game.start_fen))
    node = out
    for i, move in enumerate(game.board.move_stack):
        node = node.add_variation(move)
        if i in game.comments:
            node.comment = game.comments[i]
    buf = io.StringIO()
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
    buf.write(out.accept(exporter))
    return buf.getvalue() + "\n"


def _build(pgn_game: chess.pgn.Game) -> Game:
    fen = pgn_game.headers.get("FEN") if pgn_game.headers.get("SetUp") == "1" else None
    try:
        game = Game(fen)
    except ValueError as e:
        raise PgnError(f"invalid FEN tag: {e}") from e
    game.headers.update({k: v for k, v in pgn_game.headers.items() if k not in ("FEN", "SetUp")})
    for i, node in enumerate(pgn_game.mainline()):
        game.board.push(node.move)
        c = clean_comment(node.comment)
        if c:
            game.comments[i] = c
    if pgn_game.errors:
        side = "White" if game.board.turn == chess.WHITE else "Black"
        raise PgnError(
            f"illegal move at move {game.board.fullmove_number} ({side} to move): "
            f"{pgn_game.errors[0]}"
        ) from None
    result = game.headers.get("Result", "*")
    if result in ("1-0", "0-1", "1/2-1/2") and game.end() is None:
        game.forced_end = GameEnd(result, "recorded result")
    return game


def load_all(text: str) -> list[Game]:
    stream = io.StringIO(text.lstrip("﻿"))
    games = []
    while True:
        g = chess.pgn.read_game(stream)
        if g is None:
            break
        games.append(_build(g))
    return games


def loads(text: str) -> Game:
    games = load_all(text)
    if not games:
        raise PgnError("no game found in PGN")
    return games[0]


def read_file(path: str | os.PathLike) -> Game:
    return loads(Path(path).read_text(encoding="utf-8"))


def write_file(game: Game, path: str | os.PathLike, overwrite: bool = False) -> None:
    p = Path(path)
    if p.exists() and not overwrite:
        raise FileExistsError(str(p))
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(dumps(game), encoding="utf-8")
    tmp.replace(p)
