"""Client side of the relay: one WebSocket, JSON frames, events delivered on a queue."""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass, field

from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.sync.client import ClientConnection, connect


class NetError(Exception):
    pass


@dataclass
class NetEvent:
    kind: str  # "msg" | "peer_joined" | "peer_left" | "closed"
    data: dict = field(default_factory=dict)


class NetSession:
    def __init__(self, url: str):
        self.url = url
        self.events: queue.Queue[NetEvent] = queue.Queue()
        self.room: str | None = None
        self.token: str | None = None
        self.role: str | None = None
        self._ws: ClientConnection | None = None
        self._thread: threading.Thread | None = None
        self._closing = False

    # --- connect -----------------------------------------------------
    def _open(self, hello: dict, expect: str, timeout: float) -> dict:
        try:
            try:
                self._ws = connect(self.url, open_timeout=timeout, max_size=4096, legacy=True)
            except TypeError:  # older websockets without the legacy flag
                self._ws = connect(self.url, open_timeout=timeout, max_size=4096)
            self._ws.send(json.dumps(hello))
            reply = json.loads(self._ws.recv(timeout=timeout))
        except (OSError, WebSocketException, TimeoutError, ValueError) as e:
            self._ws = None
            raise NetError(f"cannot reach relay at {self.url}: {e}") from e
        if reply.get("t") == "error":
            self.close()
            raise NetError(reply.get("reason", "relay error"))
        if reply.get("t") != expect:
            self.close()
            raise NetError(f"unexpected relay reply: {reply}")
        self._closing = False
        self._thread = threading.Thread(target=self._reader, daemon=True, name="rcm-net")
        self._thread.start()
        return reply

    def host(self, timeout: float = 5.0) -> str:
        hello: dict = {"t": "host"}
        if self.room and self.token:
            hello.update(room=self.room, token=self.token)
        reply = self._open(hello, "hosted", timeout)
        self.role, self.room, self.token = "host", reply["room"], reply["token"]
        return self.room

    def join(self, code: str, timeout: float = 5.0) -> None:
        self._open({"t": "join", "room": code.strip().upper()}, "joined", timeout)
        self.role, self.room = "guest", code.strip().upper()

    # --- io ----------------------------------------------------------
    def send(self, **msg) -> None:
        if self._ws is None:
            raise NetError("not connected")
        try:
            self._ws.send(json.dumps(msg))
        except (ConnectionClosed, OSError) as e:
            raise NetError("connection lost") from e

    def _reader(self) -> None:
        ws = self._ws
        assert ws is not None
        try:
            for frame in ws:
                try:
                    msg = json.loads(frame)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                kind = msg.get("t")
                if kind in ("peer_joined", "peer_left"):
                    self.events.put(NetEvent(kind))
                else:
                    self.events.put(NetEvent("msg", msg))
        except (ConnectionClosed, OSError):
            pass
        finally:
            if not self._closing:
                self.events.put(NetEvent("closed"))

    def poll(self) -> NetEvent | None:
        try:
            return self.events.get_nowait()
        except queue.Empty:
            return None

    def wait(self, timeout: float = 5.0) -> NetEvent | None:
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._closing = True
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
