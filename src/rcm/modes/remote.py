"""Remote two-player game over the relay. Moves travel as SAN strings in JSON frames."""

from __future__ import annotations

import chess

from rcm.core import Game
from rcm.modes.session import Session
from rcm.net import NetSession
from rcm.net.client import NetError


class RemoteSession(Session):
    mode = "two_player_remote"

    def __init__(
        self,
        net: NetSession,
        game: Game | None = None,
        my_color: bool = chess.WHITE,
        name: str = "Player",
        **kw,
    ):
        super().__init__(game, **kw)
        self.net = net
        self.my_color = my_color
        self.name = name
        self.peer_name = ""
        self.connected = False  # peer present and synced
        self.draw_offered_by_me = False
        self.draw_offer_pending = False  # opponent offered, awaiting my answer
        self.takeback_requested_by_me = False
        self.takeback_pending = False
        self.peer_gone = False
        self.room: str | None = None

    # --- construction helpers ---------------------------------------
    @classmethod
    def host(cls, net: NetSession, name: str = "Host", color: bool = chess.WHITE, game=None, **kw):
        s = cls(net, game=game, my_color=color, name=name, **kw)
        s.room = net.host()
        s._set_names()
        return s

    @classmethod
    def join(cls, net: NetSession, code: str, name: str = "Guest", **kw):
        net.join(code)
        s = cls(net, my_color=chess.BLACK, name=name, **kw)  # color fixed by 'start'
        s.room = net.room
        return s

    def _set_names(self) -> None:
        h = self.game.headers
        key = "White" if self.my_color == chess.WHITE else "Black"
        other = "Black" if key == "White" else "White"
        h[key] = self.name
        if self.peer_name:
            h[other] = self.peer_name

    # --- rules -------------------------------------------------------
    def user_can_move(self) -> bool:
        return not self.game.is_over() and self.connected and self.turn == self.my_color

    def apply(self, mv: chess.Move) -> str:
        san = self.game.board.san(mv)
        out = super().apply(mv)
        if self.net_ok():
            self._send(t="move", san=san, n=len(self.game.moves))
        return out

    def net_ok(self) -> bool:
        return self.connected

    def _send(self, **msg) -> None:
        try:
            self.net.send(**msg)
        except NetError:
            self._dropped("Connection lost")

    # --- actions -----------------------------------------------------
    def resign(self, color: bool | None = None) -> None:
        if self.game.is_over():
            return
        self._send(t="resign")
        self.game.resign(self.my_color)
        self.after_move("resign")

    def offer_draw(self) -> None:
        if self.connected and not self.game.is_over():
            self.draw_offered_by_me = True
            self._send(t="draw_offer")
            self.message = "Draw offered"
            self.notify()

    def answer_draw(self, accept: bool) -> None:
        if not self.draw_offer_pending:
            return
        self.draw_offer_pending = False
        self._send(t="draw_accept" if accept else "draw_decline")
        if accept:
            self.game.agree_draw()
            self.after_move("draw")
        else:
            self.notify()

    def request_takeback(self) -> None:
        if self.connected and self.game.moves and not self.game.is_over():
            self.takeback_requested_by_me = True
            self._send(t="takeback_req")
            self.message = "Takeback requested"
            self.notify()

    def answer_takeback(self, accept: bool) -> None:
        if not self.takeback_pending:
            return
        self.takeback_pending = False
        if accept:
            plies = self._takeback_plies(requester_is_me=False)
            self._send(t="takeback_accept", plies=plies)
            self._pop(plies)
        else:
            self._send(t="takeback_decline")
            self.notify()

    def _takeback_plies(self, requester_is_me: bool) -> int:
        """Undo up to and including the requester's last move."""
        requester = self.my_color if requester_is_me else (not self.my_color)
        n = 1 if self.turn != requester else 2
        return min(n, len(self.game.moves))

    def _pop(self, plies: int) -> None:
        for _ in range(min(plies, len(self.game.moves))):
            self.game.pop()
        self.takeback_requested_by_me = False
        self.save_autosave()
        self.notify()

    def undo(self) -> bool:
        self.request_takeback()
        return True

    # --- inbound -----------------------------------------------------
    def pump(self) -> None:
        super().pump()
        while (ev := self.net.poll()) is not None:
            if ev.kind == "peer_joined":
                self.peer_gone = False
                if self.net.role == "host":
                    self._send_start()
            elif ev.kind == "peer_left":
                self._dropped("Opponent disconnected")
            elif ev.kind == "closed":
                self._dropped("Connection lost")
            elif ev.kind == "msg":
                self._on_msg(ev.data)

    def _send_start(self) -> None:
        self._send(
            t="start",
            fen=self.game.start_fen,
            moves=self.game.san_moves(),
            host_color="white" if self.my_color == chess.WHITE else "black",
            host_name=self.name,
            headers={k: v for k, v in self.game.headers.items() if not k.startswith("RCM_")},
        )

    def _on_msg(self, m: dict) -> None:
        t = m.get("t")
        if t == "start" and self.net.role == "guest":
            self._on_start(m)
        elif t == "ready" and self.net.role == "host":
            self.peer_name = str(m.get("name", "Guest"))[:40]
            self.connected = True
            self._set_names()
            self.message = f"{self.peer_name} connected"
            self.save_autosave()
            self.notify()
        elif t == "move":
            self._on_move(m)
        elif t == "resign":
            self.game.resign(not self.my_color)
            self.after_move("resign")
        elif t == "draw_offer":
            self.draw_offer_pending = True
            self.message = "Opponent offers a draw"
            self.notify()
        elif t == "draw_accept" and self.draw_offered_by_me:
            self.draw_offered_by_me = False
            self.game.agree_draw()
            self.after_move("draw")
        elif t == "draw_decline":
            self.draw_offered_by_me = False
            self.message = "Draw declined"
            self.notify()
        elif t == "takeback_req":
            self.takeback_pending = True
            self.message = "Opponent requests a takeback"
            self.notify()
        elif t == "takeback_accept" and self.takeback_requested_by_me:
            self._pop(self._takeback_plies(requester_is_me=True))
        elif t == "takeback_decline":
            self.takeback_requested_by_me = False
            self.message = "Takeback declined"
            self.notify()

    def _on_start(self, m: dict) -> None:
        try:
            game = Game(m["fen"], {k: str(v) for k, v in m.get("headers", {}).items()})
            for san in m.get("moves", []):
                game.push_san(san)
        except (KeyError, ValueError) as e:
            self.message = f"Could not sync with host: {e}"
            self.notify()
            return
        host_white = m.get("host_color") == "white"
        self.my_color = chess.BLACK if host_white else chess.WHITE
        self.peer_name = str(m.get("host_name", "Host"))[:40]
        game.headers["RCM_Mode"] = self.mode
        self.game = game
        self._set_names()
        self.connected = True
        self._send(t="ready", name=self.name)
        self.save_autosave()
        self.message = f"Playing {self.peer_name}"
        self.notify()

    def _on_move(self, m: dict) -> None:
        if self.turn == self.my_color or self.game.is_over():
            self._desync("move out of turn")
            return
        if m.get("n") != len(self.game.moves) + 1:
            self._desync("move number mismatch")
            return
        try:
            self.game.push_san(str(m.get("san", "")))
        except ValueError:
            self._desync("illegal move from opponent")
            return
        self.after_move(str(m.get("san")))

    def _desync(self, why: str) -> None:
        self.message = f"Out of sync ({why}). Save and resume from file."
        self.save_autosave()
        self.notify()

    def _dropped(self, msg: str) -> None:
        was = self.connected
        self.connected = False
        self.peer_gone = True
        self.message = msg + " - game auto-saved; reconnect or resume from file."
        if was or self.game.moves:
            self.save_autosave()
        self.notify()

    # --- reconnect ---------------------------------------------------
    def reconnect(self) -> None:
        """Host: re-open the same room. Guest: re-join the same room code."""
        self.net.close()
        if self.net.role == "host":
            self.net.host()
        else:
            self.net.join(self.room or "")
        self.message = "Reconnected, waiting for opponent..." if self.net.role == "host" else ""
        self.notify()

    def status(self) -> str:
        if self.net.role == "host" and not self.connected and not self.game.is_over():
            return (
                f"Room {self.room}: waiting for opponent..."
                if not self.peer_gone
                else (f"Room {self.room}: opponent disconnected")
            )
        if self.peer_gone and not self.game.is_over():
            return "Disconnected"
        return super().status()

    def close(self) -> None:
        self.net.close()
