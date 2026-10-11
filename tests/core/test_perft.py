import chess
import pytest

KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
POS3 = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
POS4 = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"


def perft(board: chess.Board, depth: int) -> int:
    if depth == 0:
        return 1
    if depth == 1:
        return board.legal_moves.count()
    n = 0
    for m in list(board.legal_moves):
        board.push(m)
        n += perft(board, depth - 1)
        board.pop()
    return n


@pytest.mark.parametrize(
    "fen,depth,expected",
    [
        (chess.STARTING_FEN, 1, 20),
        (chess.STARTING_FEN, 2, 400),
        (chess.STARTING_FEN, 3, 8902),
        (KIWIPETE, 1, 48),
        (KIWIPETE, 2, 2039),
        (KIWIPETE, 3, 97862),
        (POS3, 1, 14),
        (POS3, 2, 191),
        (POS3, 3, 2812),
        (POS3, 4, 43238),
        (POS4, 1, 6),
        (POS4, 2, 264),
        (POS4, 3, 9467),
    ],
)
def test_perft(fen, depth, expected):
    assert perft(chess.Board(fen), depth) == expected


@pytest.mark.slow
def test_perft_start_depth4():
    assert perft(chess.Board(), 4) == 197_281


@pytest.mark.slow
def test_perft_start_depth5():
    assert perft(chess.Board(), 5) == 4_865_609


@pytest.mark.slow
def test_perft_kiwipete_depth4():
    assert perft(chess.Board(KIWIPETE), 4) == 4_085_603
