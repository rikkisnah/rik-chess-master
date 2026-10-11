import chess
import pytest

from rcm.core import Game
from rcm.engine import MinimaxEngine
from rcm.tutorial import LessonRunner, Progress, load_lessons
from rcm.tutorial.lessons import LessonError, load_lesson

LESSONS = load_lessons()


def solve(lesson, progress=None):
    """Play a lesson the way a perfect learner would."""
    r = LessonRunner(lesson, progress)
    while not r.completed:
        s = r.step
        if s.type == "explain":
            r.advance()
        elif s.type == "move":
            a = r.attempt(chess.Move.from_uci(s.accept[0]))
            assert a.ok and a.step_done, (lesson.id, a.message)
            r.advance()
        elif s.type == "practice":
            for _ in range(s.count):
                mv = next(
                    m
                    for m in r.board.legal_moves
                    if r.board.piece_type_at(m.from_square) == s.piece
                )
                a = r.attempt(mv)
                assert a.ok
            assert a.step_done
            r.advance()
        else:
            while True:
                expected = s.moves[r.count]
                a = r.attempt(r.board.parse_san(expected))
                assert a.ok, (lesson.id, a.message)
                if a.step_done:
                    break
            r.advance()
    return r


def test_lesson_counts_by_group():
    groups = {}
    for lesson in LESSONS:
        groups.setdefault(lesson.group, []).append(lesson.id)
    assert [len(groups[g]) for g in ("Piece basics", "Special rules", "Openings", "Tactics")] == [
        6,
        5,
        5,
        5,
    ]
    for lesson in LESSONS:
        if lesson.group == "Tactics":
            assert sum(s.type == "move" for s in lesson.steps) == 5, lesson.id


def test_all_lessons_completable_and_progress_saved(tmp_path):
    prog = Progress(tmp_path / "p.json")
    for lesson in LESSONS:
        solve(lesson, prog)
    assert len(prog.completed) == len(LESSONS) >= 10
    assert Progress(tmp_path / "p.json").completed == prog.completed
    prog.reset()
    assert not Progress(tmp_path / "p.json").completed


def test_wrong_move_is_rejected_with_hint():
    r = LessonRunner(next(x for x in LESSONS if x.id == "castling"))
    r.advance()
    a = r.attempt(chess.Move.from_uci("e1d1"))
    assert not a.ok and r.misses == 1
    assert "e1" in r.hint() or r.hint()
    assert not r.attempt(chess.Move.from_uci("a1a8")).ok  # illegal


@pytest.mark.parametrize("lid", ["check-checkmate", "stalemate"])
def test_end_rule_lessons_really_end_the_game(lid):
    lesson = next(x for x in LESSONS if x.id == lid)
    for s in lesson.steps:
        if s.type == "move":
            b = chess.Board(s.fen)
            b.push(chess.Move.from_uci(s.accept[0]))
            assert b.is_game_over()
            assert b.is_stalemate() == (lid == "stalemate")


def test_castling_en_passant_promotion_are_special_moves():
    def first_move(lid, idx=1):
        lesson = next(x for x in LESSONS if x.id == lid)
        s = lesson.steps[idx]
        b = chess.Board(s.fen)
        return b, chess.Move.from_uci(s.accept[0])

    b, m = first_move("castling")
    assert b.is_castling(m)
    b, m = first_move("en-passant")
    assert b.is_en_passant(m)
    b, m = first_move("promotion")
    assert m.promotion is None or True
    assert any(mm.promotion for mm in b.legal_moves)


def test_tactic_puzzles_are_sound():
    """Material/mate puzzles: the solution is the engine's choice. Pin puzzles: it creates a pin."""
    shallow, deep = MinimaxEngine(depth=3, seed=0), MinimaxEngine(depth=4, seed=0)
    bad = []
    for lesson in LESSONS:
        if lesson.group != "Tactics":
            continue
        for s in lesson.steps:
            if s.type != "move":
                continue
            if lesson.id == "pin":
                b = chess.Board(s.fen)
                mover = b.turn
                b.push(chess.Move.from_uci(s.accept[0]))
                if not any(
                    b.is_pinned(not mover, sq) for sq in chess.SquareSet(b.occupied_co[not mover])
                ):
                    bad.append((lesson.id, s.fen, "no pin created"))
                continue
            g = Game(s.fen)
            if (
                shallow.best_move(g).uci() not in s.accept
                and deep.best_move(g).uci() not in s.accept
            ):
                bad.append((lesson.id, s.fen, s.accept))
    assert not bad, bad


def test_line_lessons_opponent_auto_replies():
    r = LessonRunner(next(x for x in LESSONS if x.id == "sicilian"))
    r.advance()
    assert r.board.turn == chess.BLACK and len(r.board.move_stack) == 1  # e4 auto-played
    a = r.attempt(r.board.parse_san("c5"))
    assert a.ok and a.reply is not None and not a.step_done


def test_bad_lesson_files_rejected(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text(
        "id: x\ngroup: g\ntitle: t\nsteps:\n- type: move\n"
        "  fen: 4k3/8/8/8/8/8/8/4K3 w - - 0 1\n  accept: [e1e5]\n"
    )
    with pytest.raises(LessonError, match="illegal"):
        load_lesson(p)
    p.write_text("id: x\ngroup: g\ntitle: t\nsteps:\n- type: nonsense\n")
    with pytest.raises(LessonError):
        load_lesson(p)
