"""UI smoke tests: window opens, board renders, click-move registers (needs a display)."""

import tkinter as tk

import chess
import pytest

from rcm.engine import RandomEngine
from rcm.modes import LocalSession, MachineSession, ReplaySession
from rcm.ui.app import App
from rcm.ui.board import SQUARE
from rcm.ui.frames import PlayFrame, ReplayFrame, TutorialFrame, move_rows

pytestmark = pytest.mark.ui


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("RCM_HOME", str(tmp_path / "home"))
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    r.geometry("+0+0")
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def click(frame, sq):
    bv = frame.board_view
    x, y = bv.square_xy(sq)
    bv.event_generate("<Button-1>", x=x + SQUARE // 2, y=y + SQUARE // 2)
    frame.update()


def test_move_rows():
    assert move_rows(["e4", "e5", "Nf3"]) == ["1. e4  e5", "2. Nf3"]
    assert move_rows(["e5", "Nf3"], start_white=False) == ["1... e5", "2. Nf3"]


def test_app_opens_and_local_game_click_move(root):
    app = App(root)
    root.update()
    app.start_local()
    root.update()
    frame = app.frame
    assert isinstance(frame, PlayFrame)
    assert len(frame.board_view.find_all()) > 64  # squares + pieces rendered
    click(frame, chess.E2)
    assert frame.selected == chess.E2
    click(frame, chess.E4)
    assert frame.session.board.move_stack == [chess.Move.from_uci("e2e4")]
    assert frame.moves.get(0) == "1. e4"
    assert "Black to move" in frame.status.cget("text")


def test_click_selects_only_own_pieces_and_deselects(root):
    s = LocalSession(autosave=False)
    f = PlayFrame(root, s, lambda: None)
    f.pack()
    root.update()
    click(f, chess.E7)  # Black piece on White's turn
    assert f.selected is None
    click(f, chess.G1)
    click(f, chess.F3)
    assert s.board.piece_at(chess.F3).piece_type == chess.KNIGHT


def test_promotion_dialog_choice(root):
    from rcm.core import Game

    s = LocalSession(Game("8/P6k/8/8/8/8/8/K7 w - - 0 1"), autosave=False)
    f = PlayFrame(root, s, lambda: None, ask_promo=lambda parent: chess.ROOK)
    f.pack()
    root.update()
    click(f, chess.A7)
    click(f, chess.A8)
    assert s.board.piece_at(chess.A8).piece_type == chess.ROOK


def test_machine_frame_replies(root):
    s = MachineSession("beginner", engine=RandomEngine(1), autosave=False)
    f = PlayFrame(root, s, lambda: None)
    f.pack()
    root.update()
    click(f, chess.E2)
    click(f, chess.E4)
    for _ in range(100):
        root.update()
        if len(s.game.moves) == 2:
            break
        root.after(20)
    assert len(s.game.moves) == 2
    s.close()


def test_replay_frame_steps(root):
    from rcm.modes import list_games

    path = next(g.path for g in list_games() if "opera" in g.path.stem)
    r = ReplaySession.from_path(path)
    f = ReplayFrame(root, r, lambda: None)
    f.pack()
    root.update()
    r.forward()
    root.update()
    assert "1. e4" in f.label.cget("text")
    r.goto(31)
    root.update()
    assert "queen sacrifice" in f.comment.get("1.0", "end").lower()


def test_tutorial_frame_plays_a_lesson(root):
    f = TutorialFrame(root, lambda: None)
    f.pack()
    root.update()
    f.start("castling")
    root.update()
    f.next()
    root.update()
    assert f.board_view.interactive
    click(f, chess.E1)
    click(f, chess.G1)
    assert "king" in f.feedback.cget("text").lower()


def test_save_never_overwrites_without_prompt_and_load_errors(root, tmp_path, monkeypatch):
    from tkinter import messagebox

    from tests.conftest import FIXTURES

    asked, errors = [], []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a) or False)
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: errors.append(a))
    app = App(root)
    app.start_local()
    root.update()
    click(app.frame, chess.E2)
    click(app.frame, chess.E4)
    target = tmp_path / "game.pgn"
    assert app.save_to(target) and target.exists()
    before = target.read_text()
    assert not app.save_to(target)  # user said "no" to the overwrite prompt
    assert asked and target.read_text() == before
    assert not app.load_from(FIXTURES / "illegal.pgn")  # illegal move reported, nothing opened
    assert errors and "move 3" in errors[0][1]
    assert app.load_from(target)
    assert app.frame.session.board.move_stack == [chess.Move.from_uci("e2e4")]


def test_offer_resume_loads_autosave(root, tmp_path, monkeypatch):
    from tkinter import messagebox

    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s = LocalSession()  # autosaves into RCM_HOME
    s.move(chess.E2, chess.E4)
    app = App(root)
    app.offer_resume()
    root.update()
    assert isinstance(app.frame, PlayFrame)
    assert len(app.frame.session.game.moves) == 1
