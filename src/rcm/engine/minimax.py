"""Club engine: alpha-beta minimax with material + piece-square tables."""

from __future__ import annotations

import random

import chess

from rcm.core import Game

VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}
MATE = 100_000

# Tables are written from White's view with rank 8 at the top.
_PST_ROWS = {
    chess.PAWN: [
        [0, 0, 0, 0, 0, 0, 0, 0],
        [50, 50, 50, 50, 50, 50, 50, 50],
        [10, 10, 20, 30, 30, 20, 10, 10],
        [5, 5, 10, 25, 25, 10, 5, 5],
        [0, 0, 0, 20, 20, 0, 0, 0],
        [5, -5, -10, 0, 0, -10, -5, 5],
        [5, 10, 10, -20, -20, 10, 10, 5],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ],
    chess.KNIGHT: [
        [-50, -40, -30, -30, -30, -30, -40, -50],
        [-40, -20, 0, 0, 0, 0, -20, -40],
        [-30, 0, 10, 15, 15, 10, 0, -30],
        [-30, 5, 15, 20, 20, 15, 5, -30],
        [-30, 0, 15, 20, 20, 15, 0, -30],
        [-30, 5, 10, 15, 15, 10, 5, -30],
        [-40, -20, 0, 5, 5, 0, -20, -40],
        [-50, -40, -30, -30, -30, -30, -40, -50],
    ],
    chess.BISHOP: [
        [-20, -10, -10, -10, -10, -10, -10, -20],
        [-10, 0, 0, 0, 0, 0, 0, -10],
        [-10, 0, 5, 10, 10, 5, 0, -10],
        [-10, 5, 5, 10, 10, 5, 5, -10],
        [-10, 0, 10, 10, 10, 10, 0, -10],
        [-10, 10, 10, 10, 10, 10, 10, -10],
        [-10, 5, 0, 0, 0, 0, 5, -10],
        [-20, -10, -10, -10, -10, -10, -10, -20],
    ],
    chess.ROOK: [
        [0, 0, 0, 0, 0, 0, 0, 0],
        [5, 10, 10, 10, 10, 10, 10, 5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5],
        [0, 0, 0, 5, 5, 0, 0, 0],
    ],
    chess.QUEEN: [
        [-20, -10, -10, -5, -5, -10, -10, -20],
        [-10, 0, 0, 0, 0, 0, 0, -10],
        [-10, 0, 5, 5, 5, 5, 0, -10],
        [-5, 0, 5, 5, 5, 5, 0, -5],
        [0, 0, 5, 5, 5, 5, 0, -5],
        [-10, 5, 5, 5, 5, 5, 0, -10],
        [-10, 0, 5, 0, 0, 0, 0, -10],
        [-20, -10, -10, -5, -5, -10, -10, -20],
    ],
    chess.KING: [
        [-30, -40, -40, -50, -50, -40, -40, -30],
        [-30, -40, -40, -50, -50, -40, -40, -30],
        [-30, -40, -40, -50, -50, -40, -40, -30],
        [-30, -40, -40, -50, -50, -40, -40, -30],
        [-20, -30, -30, -40, -40, -30, -30, -20],
        [-10, -20, -20, -20, -20, -20, -20, -10],
        [20, 20, 0, 0, 0, 0, 20, 20],
        [20, 30, 10, 0, 0, 10, 30, 20],
    ],
}
_KING_END = [
    [-50, -40, -30, -20, -20, -30, -40, -50],
    [-30, -20, -10, 0, 0, -10, -20, -30],
    [-30, -10, 20, 30, 30, 20, -10, -30],
    [-30, -10, 30, 40, 40, 30, -10, -30],
    [-30, -10, 30, 40, 40, 30, -10, -30],
    [-30, -10, 20, 30, 30, 20, -10, -30],
    [-30, -30, 0, 0, 0, 0, -30, -30],
    [-50, -30, -30, -30, -30, -30, -30, -50],
]


def _flat(rows: list[list[int]]) -> list[int]:
    """Index by chess square (a1=0): row 0 of the table is rank 8."""
    return [rows[7 - sq // 8][sq % 8] for sq in range(64)]


PST = {pt: _flat(rows) for pt, rows in _PST_ROWS.items()}
KING_END = _flat(_KING_END)


def _mirror(sq: int) -> int:
    return sq ^ 56


def evaluate(board: chess.Board) -> int:
    """Score from the side to move's point of view."""
    pieces = board.piece_map()
    material = sum(VALUES[p.piece_type] for p in pieces.values() if p.piece_type != chess.KING)
    endgame = material <= 2600
    score = 0
    for sq, p in pieces.items():
        if p.piece_type == chess.KING and endgame:
            table = KING_END
        else:
            table = PST[p.piece_type]
        if p.color == chess.WHITE:
            v = VALUES[p.piece_type] + table[_mirror(sq)]
            score += v
        else:
            v = VALUES[p.piece_type] + table[sq]
            score -= v
    if endgame:
        score += _mop_up(board, pieces, score)
    return score if board.turn == chess.WHITE else -score


def _mop_up(board: chess.Board, pieces: dict, score: int) -> int:
    """When far ahead, drive the losing king to the edge and bring the kings together."""
    if abs(score) < 300:
        return 0
    winner = chess.WHITE if score > 0 else chess.BLACK
    loser_k = board.king(not winner)
    winner_k = board.king(winner)
    if loser_k is None or winner_k is None:
        return 0
    cf, cr = chess.square_file(loser_k), chess.square_rank(loser_k)
    centre_dist = max(3 - cf, cf - 4) + max(3 - cr, cr - 4)
    king_dist = chess.square_distance(winner_k, loser_k)
    bonus = 10 * centre_dist + 4 * (14 - king_dist)
    return bonus if winner == chess.WHITE else -bonus


class MinimaxEngine:
    name = "Club"

    def __init__(self, depth: int = 3, seed: int | None = None):
        self.depth = depth
        self.rng = random.Random(seed)

    def _ordered(self, board: chess.Board) -> list[chess.Move]:
        def key(m: chess.Move) -> int:
            s = 0
            if board.is_capture(m):
                victim = board.piece_type_at(m.to_square) or chess.PAWN  # en passant
                s += 10 * VALUES[victim] - VALUES[board.piece_type_at(m.from_square)]
            if m.promotion:
                s += VALUES[m.promotion]
            if board.gives_check(m):
                s += 50
            return -s

        return sorted(board.legal_moves, key=key)

    def _search(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        if board.is_checkmate():
            return -MATE + ply
        if board.is_stalemate() or board.is_insufficient_material():
            return 0
        if depth == 0:
            return self._quiesce(board, alpha, beta, 0)
        best = -MATE
        for m in self._ordered(board):
            board.push(m)
            score = -self._search(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            if score > best:
                best = score
                if best > alpha:
                    alpha = best
                if alpha >= beta:
                    break
        return best

    def _quiesce(self, board: chess.Board, alpha: int, beta: int, qd: int) -> int:
        stand = evaluate(board)
        if qd >= 4 or stand >= beta:
            return stand if stand >= beta else max(stand, alpha)
        alpha = max(alpha, stand)
        caps = [m for m in self._ordered(board) if board.is_capture(m)]
        for m in caps:
            board.push(m)
            score = -self._quiesce(board, -beta, -alpha, qd + 1)
            board.pop()
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    def best_move(self, game: Game) -> chess.Move:
        board = game.board.copy(stack=True)
        moves = self._ordered(board)
        if not moves:
            raise ValueError("no legal moves")
        best_score = -MATE - 1
        best: list[chess.Move] = []
        for m in moves:
            board.push(m)
            # window (best_score - 1, MATE): scores equal to best_score stay exact for tie-breaking
            score = -self._search(board, self.depth - 1, -MATE, -(best_score - 1), 1)
            if score > 0 and board.is_repetition(2):
                score -= 60  # don't shuffle when ahead
            board.pop()
            if score > best_score:
                best_score, best = score, [m]
            elif score == best_score:
                best.append(m)
        return self.rng.choice(best)

    def close(self) -> None:
        pass
