import time

import chess
import pytest

from rcm import paths
from rcm.core import Game, read_file
from rcm.engine import RandomEngine
from rcm.modes import LocalSession, MachineSession, RemoteSession, ReplaySession, list_games
from rcm.net import NetSession, Relay


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("RCM_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def pump_until(cond, *sessions, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        for s in sessions:
            s.pump()
        if cond():
            return True
        time.sleep(0.01)
    return False


def mv(s, uci):
    m = chess.Move.from_uci(uci)
    assert s.move(m.from_square, m.to_square, m.promotion), uci


def test_local_play_autosave_and_flip(home):
    s = LocalSession(auto_flip=True)
    assert not s.flipped
    mv(s, "e2e4")
    assert s.flipped
    assert (home / "autosave.pgn").exists()
    assert not s.move(chess.E2, chess.E5)  # illegal
    assert s.undo() and s.board.fen() == chess.STARTING_FEN
    assert read_file(home / "autosave.pgn").headers["RCM_Mode"] == "two_player_local"


def test_save_never_overwrites(tmp_path):
    s = LocalSession(autosave=False)
    mv(s, "e2e4")
    s.save(tmp_path / "a.pgn")
    with pytest.raises(FileExistsError):
        s.save(tmp_path / "a.pgn")
    s.save(tmp_path / "a.pgn", overwrite=True)


def test_promotion_defaults_to_queen_and_choice():
    s = LocalSession(Game("8/P6k/8/8/8/8/8/K7 w - - 0 1"), autosave=False)
    assert s.move(chess.A7, chess.A8, chess.KNIGHT)
    assert s.board.piece_at(chess.A8).piece_type == chess.KNIGHT


def test_machine_session_replies_and_blocks_input():
    s = MachineSession(level="beginner", seed=1, autosave=False)
    mv(s, "e2e4")
    assert s.thinking and not s.user_can_move()
    assert pump_until(lambda: not s.thinking, s)
    assert len(s.game.moves) == 2 and s.turn == chess.WHITE
    assert s.game.headers["Black"] == "Machine (Beginner)"
    assert s.undo() and len(s.game.moves) == 0
    s.close()


def test_machine_plays_white_when_human_black():
    s = MachineSession(level="beginner", human_color=chess.BLACK, seed=2, autosave=False)
    s.start()
    assert pump_until(lambda: len(s.game.moves) == 1, s)
    assert s.user_can_move()
    s.close()


def test_machine_hint_and_master_fallback(monkeypatch):
    monkeypatch.setattr("rcm.engine.uci.find_stockfish", lambda: None)
    s = MachineSession(level="master", seed=1, autosave=False)
    assert "Stockfish" in s.notice and s.level == "club"
    s.request_hint()
    assert pump_until(lambda: s.hint_move is not None, s, timeout=30)
    assert s.game.is_legal(s.hint_move)
    mv(s, "e2e4")
    assert s.hint_move is None
    s.close()


def test_machine_resume_from_game():
    g = Game(headers={"White": "Machine (Club)", "RCM_Level": "beginner"})
    s = MachineSession.resume(g, engine=RandomEngine(1), autosave=False)
    assert s.human_color == chess.BLACK
    s.start()
    assert pump_until(lambda: len(g.moves) == 1, s)
    s.close()


# --- remote ----------------------------------------------------------
@pytest.fixture
def relay():
    r = Relay("127.0.0.1", 0)
    r.start()
    yield f"ws://127.0.0.1:{r.port}"
    r.stop()


def connect_pair(url, host_autosave, guest_autosave):
    h = RemoteSession.host(NetSession(url), name="Hosty", autosave=host_autosave)
    g = RemoteSession.join(NetSession(url), h.room, name="Guesty", autosave=guest_autosave)
    assert pump_until(lambda: h.connected and g.connected, h, g)
    return h, g


def test_remote_ten_move_game(relay, tmp_path):
    h, g = connect_pair(relay, tmp_path / "h.pgn", tmp_path / "g.pgn")
    assert h.my_color == chess.WHITE and g.my_color == chess.BLACK
    assert g.game.headers["White"] == "Hosty" and h.game.headers["Black"] == "Guesty"
    line = "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 d2d3 f8c5 e1g1 d7d6 c2c3 e8g8 b2b4 c5b6 a2a4 a7a6".split()
    assert len(line) >= 10
    for i, u in enumerate(line):
        mover, other = (h, g) if i % 2 == 0 else (g, h)
        assert not other.user_can_move() or other is mover
        assert pump_until(mover.user_can_move, h, g)
        mv(mover, u)
        assert pump_until(lambda i=i, other=other: len(other.game.moves) == i + 1, h, g)
    assert h.game.fen() == g.game.fen()
    h.close()
    g.close()


def test_remote_rejects_moves_out_of_turn(relay, tmp_path):
    h, g = connect_pair(relay, False, False)
    assert not g.move(chess.E7, chess.E5)  # not black's turn
    h.close()
    g.close()


def test_remote_resign_draw_takeback(relay):
    h, g = connect_pair(relay, False, False)
    mv(h, "e2e4")
    assert pump_until(lambda: g.user_can_move(), h, g)
    # takeback: host asks, guest declines, then accepts
    h.request_takeback()
    assert pump_until(lambda: g.takeback_pending, h, g)
    g.answer_takeback(False)
    assert pump_until(lambda: not h.takeback_requested_by_me, h, g)
    assert len(h.game.moves) == 1
    h.request_takeback()
    assert pump_until(lambda: g.takeback_pending, h, g)
    g.answer_takeback(True)
    assert pump_until(lambda: len(h.game.moves) == 0 and len(g.game.moves) == 0, h, g)
    # draw
    mv(h, "d2d4")
    assert pump_until(g.user_can_move, h, g)
    g.offer_draw()
    assert pump_until(lambda: h.draw_offer_pending, h, g)
    h.answer_draw(True)
    assert pump_until(lambda: g.game.is_over() and h.game.is_over(), h, g)
    assert h.game.result() == "1/2-1/2" == g.game.result()
    h.close()
    g.close()


def test_remote_resign(relay):
    h, g = connect_pair(relay, False, False)
    g.resign()
    assert pump_until(lambda: h.game.is_over(), h, g)
    assert h.game.result() == "1-0" and g.game.result() == "1-0"
    h.close()
    g.close()


def test_remote_drop_autosaves_and_guest_reconnects(relay, tmp_path, monkeypatch):
    h, g = connect_pair(relay, tmp_path / "h.pgn", tmp_path / "g.pgn")
    for i, u in enumerate("e2e4 e7e5 g1f3".split()):
        mover = h if i % 2 == 0 else g
        assert pump_until(mover.user_can_move, h, g)
        mv(mover, u)
        assert pump_until(lambda i=i: len(h.game.moves) == i + 1 == len(g.game.moves), h, g)
    g.net.close()  # guest vanishes
    assert pump_until(lambda: not h.connected and h.peer_gone, h)
    assert "auto-saved" in h.message
    saved = read_file(tmp_path / "h.pgn")
    assert len(saved.moves) == 3 and saved.fen() == h.game.fen()
    g.net.role = "guest"
    g.reconnect()
    assert pump_until(lambda: h.connected and g.connected, h, g)
    assert g.game.fen() == h.game.fen()
    h.close()
    g.close()


def test_remote_resume_from_file_with_moves(relay, tmp_path):
    first = LocalSession(autosave=False)
    for u in "e2e4 e7e5".split():
        mv(first, u)
    resumed = first.game
    h = RemoteSession.host(NetSession(relay), game=resumed, autosave=False)
    g = RemoteSession.join(NetSession(relay), h.room, autosave=False)
    assert pump_until(lambda: h.connected and g.connected, h, g)
    assert len(g.game.moves) == 2 and g.game.fen() == h.game.fen()
    h.close()
    g.close()


# --- replay ----------------------------------------------------------
def test_famous_games_listed_and_replay():
    games = list_games()
    assert len(games) >= 6
    opera = next(x for x in games if "opera" in x.path.stem)
    r = ReplaySession.from_path(opera.path)
    assert r.move_label() == "Start position"
    r.forward()
    assert r.move_label() == "1. e4"
    r.goto(len(r.moves))
    assert r.finished and r.board.is_checkmate()
    assert r.back() and not r.board.is_checkmate()
    r.goto(31)
    assert "queen sacrifice" in r.commentary.lower()
    r.goto(0)
    r.play()
    r.tick()
    assert r.position == 1
    r.pause()
    r.tick()
    assert r.position == 1
    r.set_interval(100)
    assert r.interval == 10.0


def test_all_bundled_games_replay_to_end():
    for info in list_games():
        r = ReplaySession.from_path(info.path)
        r.goto(10_000)
        assert r.finished
        assert r.board.fen() == read_file(info.path).fen()
        assert paths.resource_root().exists()
