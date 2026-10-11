"""Tiny WebSocket relay with room codes.

A host opens a room and gets a 6-character code; a guest joins with it. After pairing the
relay forwards every text frame verbatim to the other side and never interprets game data.

Handshake (first frame, JSON):
  {"t":"host"}                          -> {"t":"hosted","room":"K7M2QX","token":"..."}
  {"t":"host","room":R,"token":T}       -> {"t":"hosted",...}  (host reconnect)
  {"t":"join","room":R}                 -> {"t":"joined"}  and the host gets {"t":"peer_joined"}
Errors: {"t":"error","reason":"..."} then the socket closes.
When a side drops, the other receives {"t":"peer_left"}; the room stays open for rejoin.
"""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import Server, ServerConnection, serve

log = logging.getLogger("rcm.relay")

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
CODE_LEN = 6
MAX_FRAME = 4096
ROOM_TTL = 3600.0  # seconds of inactivity before a room is dropped
MAX_ROOMS = 500
JOIN_FAILS_PER_MIN = 10


@dataclass
class Room:
    code: str
    token: str
    host: ServerConnection | None = None
    guest: ServerConnection | None = None
    touched: float = field(default_factory=time.monotonic)


def _send(ws: ServerConnection | None, obj: dict | str) -> None:
    """Send a control dict (JSON-encoded) or forward a raw text frame unchanged."""
    if ws is None:
        return
    try:
        ws.send(obj if isinstance(obj, str) else json.dumps(obj))
    except ConnectionClosed:
        pass


class Relay:
    def __init__(self, host: str = "127.0.0.1", port: int = 8790, room_ttl: float = ROOM_TTL):
        self.host, self.port, self.room_ttl = host, port, room_ttl
        self.rooms: dict[str, Room] = {}
        self._lock = threading.Lock()
        self._fails: dict[str, deque[float]] = defaultdict(deque)
        self._server: Server | None = None
        self._thread: threading.Thread | None = None

    # --- lifecycle ---------------------------------------------------
    def start(self) -> int:
        """Serve in a background thread; returns the bound port."""
        self._server = serve(self._handle, self.host, self.port, max_size=MAX_FRAME, open_timeout=5)
        self.port = self._server.socket.getsockname()[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    @property
    def running(self) -> bool:
        return self._server is not None

    def serve_forever(self) -> None:
        self.start()
        try:
            assert self._thread is not None
            self._thread.join()
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()

    # --- helpers -----------------------------------------------------
    def _gc(self) -> None:
        now = time.monotonic()
        for code in [c for c, r in self.rooms.items() if now - r.touched > self.room_ttl]:
            del self.rooms[code]

    def _rate_limited(self, ip: str) -> bool:
        q = self._fails[ip]
        now = time.monotonic()
        while q and now - q[0] > 60:
            q.popleft()
        return len(q) >= JOIN_FAILS_PER_MIN

    def _new_room(self) -> Room | None:
        with self._lock:
            self._gc()
            if len(self.rooms) >= MAX_ROOMS:
                return None
            while True:
                code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
                if code not in self.rooms:
                    break
            room = Room(code, secrets.token_urlsafe(16))
            self.rooms[code] = room
            return room

    # --- connection handler -----------------------------------------
    def _handle(self, ws: ServerConnection) -> None:
        ip = ws.remote_address[0] if ws.remote_address else "?"
        try:
            hello = json.loads(ws.recv(timeout=10))
        except (ConnectionClosed, TimeoutError, ValueError):
            return
        if not isinstance(hello, dict):
            return
        kind = hello.get("t")
        room: Room | None
        role: str
        if kind == "host":
            role = "host"
            if hello.get("room"):
                with self._lock:
                    room = self.rooms.get(str(hello["room"]).upper())
                if room is None or not secrets.compare_digest(room.token, str(hello.get("token"))):
                    return _fail(ws, "unknown room or bad token")
            else:
                room = self._new_room()
                if room is None:
                    return _fail(ws, "relay is full")
            with self._lock:
                room.host = ws
                room.touched = time.monotonic()
                guest = room.guest
            _send(ws, {"t": "hosted", "room": room.code, "token": room.token})
            if guest is not None:
                _send(ws, {"t": "peer_joined"})
                _send(guest, {"t": "peer_joined"})
        elif kind == "join":
            role = "guest"
            if self._rate_limited(ip):
                return _fail(ws, "too many attempts, try again later")
            code = str(hello.get("room", "")).strip().upper()
            with self._lock:
                room = self.rooms.get(code)
                ok = room is not None and room.guest is None and room.host is not None
                if ok:
                    assert room is not None
                    room.guest = ws
                    room.touched = time.monotonic()
                    host = room.host
            if not ok:
                self._fails[ip].append(time.monotonic())
                return _fail(ws, "no such room, or it is full")
            _send(ws, {"t": "joined"})
            _send(host, {"t": "peer_joined"})
        else:
            return _fail(ws, "bad handshake")

        try:
            for frame in ws:
                if not isinstance(frame, str):
                    continue
                with self._lock:
                    room.touched = time.monotonic()
                    other = room.guest if role == "host" else room.host
                if other is not None:
                    _send(other, frame)
        except ConnectionClosed:
            pass
        finally:
            with self._lock:
                if role == "host" and room.host is ws:
                    room.host, other = None, room.guest
                elif role == "guest" and room.guest is ws:
                    room.guest, other = None, room.host
                else:
                    other = None
            _send(other, {"t": "peer_left"})


def _fail(ws: ServerConnection, reason: str) -> None:
    _send(ws, {"t": "error", "reason": reason})
    ws.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="rik-chess-master relay (WebSocket room codes)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(f"rcm-relay listening on ws://{args.host}:{args.port}")
    Relay(args.host, args.port).serve_forever()


if __name__ == "__main__":
    main()
