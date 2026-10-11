import chess
import pytest

from rcm.core import Game


def play(game, sans):
    for s in sans.split():
        game.push_san(s)
    return game


def test_checkmate_fools_mate():
    g = play(Game(), "f3 e5 g4 Qh4#")
    e = g.end()
    assert e.result == "0-1" and e.reason == "checkmate"
    assert g.result() == "0-1"


def test_scholars_mate_white_wins():
    g = play(Game(), "e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#")
    assert g.end().result == "1-0"


def test_stalemate():
    g = Game("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    e = g.end()
    assert e.reason == "stalemate" and e.result == "1/2-1/2"


def test_insufficient_material():
    assert Game("8/8/4k3/8/8/3K4/8/8 w - - 0 1").end().reason == "insufficient material"
    assert Game("8/8/4k3/8/8/3KB3/8/8 w - - 0 1").is_over()
    assert not Game("8/8/4k3/8/8/3KR3/8/8 w - - 0 1").is_over()


def test_threefold_repetition():
    g = play(Game(), "Nf3 Nf6 Ng1 Ng8 Nf3 Nf6 Ng1")
    assert not g.is_over()
    g.push_san("Ng8")
    assert g.end().reason == "threefold repetition"


def test_fifty_move_rule():
    g = Game("4k3/8/8/8/8/8/8/R3K3 w - - 99 80")
    assert not g.is_over()
    g.push_san("Ra2")
    assert g.end().reason == "fifty-move rule"


def test_castling_en_passant_promotion():
    g = play(Game(), "e4 a6 e5 d5")
    assert g.board.ep_square == chess.D6
    g.push_san("exd6")
    assert g.board.piece_at(chess.D5) is None
    g = play(Game(), "e4 e5 Nf3 Nc6 Bc4 Bc5 O-O")
    assert g.board.king(chess.WHITE) == chess.G1
    p = Game("8/P6k/8/8/8/8/8/K7 w - - 0 1")
    assert p.needs_promotion(chess.A7, chess.A8)
    p.push_uci("a7a8q")
    assert p.board.piece_at(chess.A8).piece_type == chess.QUEEN


def test_illegal_move_rejected():
    g = Game()
    with pytest.raises(ValueError):
        g.push_san("e5")
    with pytest.raises(ValueError):
        g.push(chess.Move.from_uci("e2e5"))


def test_no_moves_after_game_over_and_resign():
    g = play(Game(), "f3 e5 g4 Qh4#")
    with pytest.raises(ValueError):
        g.push_san("a3")
    g2 = Game()
    g2.resign(chess.WHITE)
    assert g2.result() == "0-1" and g2.is_over()
    with pytest.raises(ValueError):
        g2.push_san("e4")


def test_pop_clears_forced_end_and_comment():
    g = play(Game(), "e4 e5")
    g.comments[1] = "x"
    g.resign(chess.WHITE)
    g.pop()
    assert g.forced_end is None and 1 not in g.comments


def test_san_moves_and_copy():
    g = play(Game(), "e4 e5 Nf3")
    assert g.san_moves() == ["e4", "e5", "Nf3"]
    c = g.copy()
    c.push_san("Nc6")
    assert len(g.moves) == 3 and len(c.moves) == 4
    assert g.legal_targets(chess.G1) == []
    assert len(g.legal_targets(chess.B8)) == 2
