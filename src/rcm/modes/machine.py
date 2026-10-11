from __future__ import annotations

import chess

from rcm.core import Game
from rcm.engine import EngineWorker, MinimaxEngine, make_engine
from rcm.modes.session import Session

LEVEL_NAMES = {"beginner": "Beginner", "club": "Club", "master": "Master"}


class MachineSession(Session):
    mode = "vs_machine"

    def __init__(
        self,
        level: str = "club",
        human_color: bool = chess.WHITE,
        game: Game | None = None,
        engine=None,
        seed: int | None = None,
        player_name: str = "Player",
        **kw,
    ):
        super().__init__(game, **kw)
        if engine is None:
            engine, notice = make_engine(level, seed=seed)
        else:
            notice = None
        self.notice = notice
        self.level = level if notice is None else "club"
        self.engine = engine
        self.worker = EngineWorker(engine)
        self.human_color = human_color
        self.thinking = False
        self.hint_move: chess.Move | None = None
        self._hinter: MinimaxEngine | None = None
        label = f"Machine ({LEVEL_NAMES[self.level]})"
        h = self.game.headers
        h["RCM_Level"] = self.level
        if h.get("White") in (None, "White"):
            h["White"] = player_name if human_color == chess.WHITE else label
        if h.get("Black") in (None, "Black"):
            h["Black"] = player_name if human_color == chess.BLACK else label

    @classmethod
    def resume(cls, game: Game, **kw) -> MachineSession:
        level = game.headers.get("RCM_Level", "club")
        white = game.headers.get("White", "")
        human = chess.BLACK if white.startswith("Machine") else chess.WHITE
        return cls(level=level, human_color=human, game=game, **kw)

    def user_can_move(self) -> bool:
        return not self.game.is_over() and self.turn == self.human_color and not self.thinking

    def start(self) -> None:
        """Kick the engine if it is to move (e.g. human plays Black, or a resumed game)."""
        self.maybe_engine_move()

    def maybe_engine_move(self) -> None:
        if self.game.is_over() or self.turn == self.human_color or self.thinking:
            return
        self.thinking = True
        self.hint_move = None
        self.notify()
        self.worker.request(self.game, lambda r: self.post(lambda: self._engine_done(r)))

    def _engine_done(self, result: chess.Move | Exception) -> None:
        self.thinking = False
        if isinstance(result, Exception):
            self.message = f"Engine error: {result}"
            self.notify()
            return
        if self.game.is_over() or not self.game.is_legal(result):
            return
        self.apply(result)

    def after_move(self, san: str) -> None:
        self.hint_move = None
        super().after_move(san)
        if san != "resign":
            self.maybe_engine_move()

    def undo(self) -> bool:
        """Take back the human's last move (and the engine's reply)."""
        if self.thinking:
            self.worker.cancel()
            self.thinking = False
        n = 2 if self.turn == self.human_color else 1
        n = min(n, len(self.game.moves))
        if n == 0:
            return False
        for _ in range(n):
            self.game.pop()
        self.hint_move = None
        self.save_autosave()
        self.notify()
        self.maybe_engine_move()
        return True

    def request_hint(self, callback=None) -> None:
        """Compute the best move for the human on a worker thread; sets .hint_move."""
        if not self.user_can_move():
            return
        import threading

        def run() -> None:
            hinter = self.engine if self.level == "master" else self._club_hinter()
            try:
                mv = hinter.best_move(self.game.copy())
            except Exception:
                return

            def done() -> None:
                if self.user_can_move():
                    self.hint_move = mv
                    self.notify()
                    if callback:
                        callback(mv)

            self.post(done)

        threading.Thread(target=run, daemon=True, name="rcm-hint").start()

    def _club_hinter(self) -> MinimaxEngine:
        if self._hinter is None:
            self._hinter = MinimaxEngine(depth=3)
        return self._hinter

    def status(self) -> str:
        if self.thinking:
            return "Machine is thinking..."
        return super().status()

    def close(self) -> None:
        self.worker.close()
