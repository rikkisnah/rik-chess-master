import re
from datetime import UTC, datetime

import pytest

from rcm.core import Game, PgnError, dumps, loads, read_file, write_file
from tests.conftest import FIXTURES, ROOT

SPEC_EXAMPLE = """[Event "Casual game"]
[Site "rik-chess-master"]
[Date "2026.10.10"]
[Round "-"]
[White "Rik"]
[Black "Machine (Club)"]
[Result "*"]
[RCM_Mode "vs_machine"]
[RCM_Level "club"]
[RCM_Saved "2026-10-10T21:43:00-07:00"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 {Morphy defence} 4. Ba4 Nf6 *
"""


def roundtrip(g):
    g2 = loads(dumps(g))
    assert [m.uci() for m in g2.moves] == [m.uci() for m in g.moves]
    assert g2.fen() == g.fen()
    return g2


def test_spec_example_roundtrip_and_tags():
    g = loads(SPEC_EXAMPLE)
    assert g.headers["RCM_Mode"] == "vs_machine"
    assert g.comments[5] == "Morphy defence"
    assert g.result() == "*" and not g.is_over()
    text = dumps(g, saved=datetime(2026, 10, 10, 21, 43, tzinfo=UTC))
    assert text.index("[Event") < text.index("[Result") < text.index("[RCM_Mode")
    assert "{ Morphy defence }" in text
    roundtrip(g)


def test_custom_start_position_roundtrip():
    fen = "8/P6k/8/8/8/8/8/K7 w - - 0 1"
    g = Game(fen)
    g.push_san("a8=Q")
    text = dumps(g)
    assert '[SetUp "1"]' in text and "[FEN" in text
    g2 = roundtrip(g)
    assert g2.start_fen == fen


def test_finished_game_result_and_resign():
    g = Game()
    for s in "f3 e5 g4 Qh4#".split():
        g.push_san(s)
    assert '[Result "0-1"]' in dumps(g)
    r = Game()
    r.push_san("e4")
    r.resign(False)  # black resigns
    g2 = loads(dumps(r))
    assert g2.result() == "1-0" and g2.is_over()


@pytest.mark.parametrize("name,n", [("lichess.pgn", 7), ("chesscom.pgn", 8)])
def test_external_exports_load(name, n):
    g = read_file(FIXTURES / name)
    assert len(g.moves) == n
    assert not re.search(r"%clk|%eval", dumps(g))
    roundtrip(g)


def test_lichess_result_and_chesscom_resignation():
    assert read_file(FIXTURES / "lichess.pgn").result() == "1-0"
    g = read_file(FIXTURES / "chesscom.pgn")
    assert g.result() == "0-1" and g.is_over()


def test_illegal_move_reports_position():
    with pytest.raises(PgnError, match=r"move 3.*White"):
        read_file(FIXTURES / "illegal.pgn")


def test_no_game():
    with pytest.raises(PgnError):
        loads("   \n")


def test_never_overwrite_without_flag(tmp_path):
    p = tmp_path / "g.pgn"
    g = Game()
    write_file(g, p)
    with pytest.raises(FileExistsError):
        write_file(g, p)
    write_file(g, p, overwrite=True)
    assert not list(tmp_path.glob("*.tmp"))


def test_bundled_games_roundtrip():
    files = sorted((ROOT / "games").glob("*.pgn"))
    for f in files:
        roundtrip(read_file(f))
