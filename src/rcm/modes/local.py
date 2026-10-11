from __future__ import annotations

from rcm.core import Game
from rcm.modes.session import Session


class LocalSession(Session):
    """Two players sharing one screen. The board may auto-flip after each move."""

    mode = "two_player_local"

    def __init__(self, game: Game | None = None, auto_flip: bool = False, **kw):
        super().__init__(game, **kw)
        self.auto_flip = auto_flip
        self.flipped = False
        self._sync_flip()

    def _sync_flip(self) -> None:
        if self.auto_flip:
            self.flipped = self.turn is False

    def after_move(self, san: str) -> None:
        self._sync_flip()
        super().after_move(san)

    def set_auto_flip(self, on: bool) -> None:
        self.auto_flip = on
        self._sync_flip()
        self.notify()
