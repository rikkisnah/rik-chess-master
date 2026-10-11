import random
import time

import chess
import pytest

from rcm.core import Game
from rcm.engine import EngineWorker, MinimaxEngine, RandomEngine, make_engine
from rcm.engine.minimax import evaluate


def test_random_engine_legal_and_prefers_captures():
    g = Game("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
    e = RandomEngine(seed=1)
    picks = [e.best_move(g) for _ in range(40)]
    assert all(g.is_legal(m) for m in picks)
    assert sum(g.board.is_capture(m) for m in picks) > 20


@pytest.mark.parametrize(
    "fen,mate",
    [
        ("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1", "Ra8#"),  # back-rank mate in 1
        ("k7/8/1K6/8/8/8/8/7R w - - 0 1", "Rh8#"),
        ("7k/5Q2/8/8/8/8/8/K5R1 w - - 0 1", None),
    ],
)
def test_mate_in_one(fen, mate):
    g = Game(fen)
    m = MinimaxEngine(depth=2, seed=0).best_move(g)
    if mate:
        assert g.board.san(m) == mate


def test_mate_in_two():
    # Black king h8, white Kg6? classic: two rooks ladder
    g = Game("7k/8/8/8/8/8/R7/1R4K1 w - - 0 1")
    eng = MinimaxEngine(depth=3, seed=0)
    m1 = eng.best_move(g)
    g.push(m1)
    replies = g.legal_moves()
    for r in replies:  # whatever Black plays, White mates next
        g2 = g.copy()
        g2.push(r)
        m2 = eng.best_move(g2)
        g2.push(m2)
        assert g2.end() and g2.end().reason == "checkmate"


def test_takes_hanging_queen_and_avoids_blunder():
    g = Game("4k3/8/8/3q4/8/8/8/3RK3 w - - 0 1")
    assert g.board.san(MinimaxEngine(depth=2, seed=0).best_move(g)) == "Rxd5"


def test_evaluate_symmetry():
    b = chess.Board()
    assert evaluate(b) == 0
    b.push_san("e4")
    assert evaluate(b) == evaluate(b.mirror())


def play_game(white, black, max_plies=160):
    g = Game()
    engines = (white, black)
    while not g.is_over() and len(g.moves) < max_plies:
        g.push(engines[len(g.moves) % 2].best_move(g))
    return g


def material(board):
    vals = {1: 1, 2: 3, 3: 3, 4: 5, 5: 9}
    return sum(
        vals.get(p.piece_type, 0) * (1 if p.color else -1) for p in board.piece_map().values()
    )


def test_club_beats_beginner_9_of_10():
    wins = 0
    start = time.time()
    for i in range(10):
        club = MinimaxEngine(depth=2, seed=i)
        rnd = RandomEngine(seed=100 + i)
        club_white = i % 2 == 0
        g = play_game(club, rnd) if club_white else play_game(rnd, club)
        res = g.result()
        if res == "*":  # adjudicate unfinished games on material
            diff = material(g.board) * (1 if club_white else -1)
            won = diff >= 5
        else:
            won = res == ("1-0" if club_white else "0-1")
        wins += won
    assert wins >= 9, f"Club only won {wins}/10"
    assert time.time() - start < 180


def test_worker_threaded_and_cancel():
    import threading

    class Slow(RandomEngine):
        def best_move(self, game):
            time.sleep(0.3)
            return super().best_move(game)

    w = EngineWorker(Slow(seed=3))
    got = []
    ev = threading.Event()
    w.request(Game(), lambda r: (got.append(r), ev.set()))
    assert ev.wait(5) and isinstance(got[0], chess.Move)
    got.clear()
    w.request(Game(), lambda r: got.append(r))
    w.cancel()
    time.sleep(0.6)
    assert not got  # stale answer discarded
    w.close()


def test_master_falls_back_without_stockfish(monkeypatch):
    monkeypatch.setattr("rcm.engine.uci.find_stockfish", lambda: None)
    eng, notice = make_engine("master", seed=1)
    assert isinstance(eng, MinimaxEngine) and "Stockfish" in notice
    assert "make stockfish" in notice
    eng, notice = make_engine("beginner")
    assert notice is None
    with pytest.raises(ValueError):
        make_engine("grandmaster")


def test_random_seed_deterministic():
    g = Game()
    assert RandomEngine(5).best_move(g) == RandomEngine(5).best_move(g)
    assert random.Random  # keep import used


FAKE_UCI = """
import sys, chess
board = chess.Board()
for line in sys.stdin:
    line = line.strip()
    if line == "uci":
        print("id name fake"); print("uciok")
    elif line == "isready":
        print("readyok")
    elif line.startswith("position"):
        parts = line.split()
        board = chess.Board()
        if "moves" in parts:
            for u in parts[parts.index("moves") + 1:]:
                board.push_uci(u)
    elif line.startswith("go"):
        print("bestmove", sorted(board.legal_moves, key=lambda m: m.uci())[0].uci())
    elif line == "quit":
        break
    sys.stdout.flush()
"""


def test_uci_engine_adapter_with_fake_engine(tmp_path):
    import sys

    from rcm.engine import UciEngine

    script = tmp_path / "fake_uci.py"
    script.write_text(FAKE_UCI)
    eng = UciEngine([sys.executable, str(script)], think_time=0.05)
    g = Game()
    g.push_san("e4")
    try:
        mv = eng.best_move(g)
        assert g.is_legal(mv) and mv.uci() == sorted(m.uci() for m in g.legal_moves())[0]
    finally:
        eng.close()


def test_find_stockfish_env_override(tmp_path, monkeypatch):
    from rcm.engine import find_stockfish

    fake = tmp_path / "sf"
    fake.write_text("")
    monkeypatch.setenv("RCM_STOCKFISH", str(fake))
    assert find_stockfish() == str(fake)
