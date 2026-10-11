import json

import pytest
from websockets.sync.client import connect

from rcm.net import NetSession, Relay
from rcm.net.client import NetError


@pytest.fixture
def relay():
    r = Relay("127.0.0.1", 0)
    r.start()
    yield r
    r.stop()


def url(r):
    return f"ws://127.0.0.1:{r.port}"


def test_host_join_and_forwarding(relay):
    h, g = NetSession(url(relay)), NetSession(url(relay))
    code = h.host()
    assert len(code) == 6
    g.join(code.lower())  # case-insensitive
    assert h.wait().kind == "peer_joined"
    h.send(t="move", san="e4")
    ev = g.wait()
    assert ev.kind == "msg" and ev.data == {"t": "move", "san": "e4"}
    g.send(t="move", san="e5")
    assert h.wait().data["san"] == "e5"
    g.close()
    assert h.wait().kind == "peer_left"
    h.close()


def test_unknown_room_and_full_room(relay):
    with pytest.raises(NetError):
        NetSession(url(relay)).join("ZZZZZZ")
    h = NetSession(url(relay))
    code = h.host()
    g1 = NetSession(url(relay))
    g1.join(code)
    with pytest.raises(NetError, match="full"):
        NetSession(url(relay)).join(code)
    g1.close()
    h.close()


def test_guest_can_rejoin_and_host_can_reconnect(relay):
    h, g = NetSession(url(relay)), NetSession(url(relay))
    code = h.host()
    g.join(code)
    h.wait()
    g.close()
    assert h.wait().kind == "peer_left"
    g2 = NetSession(url(relay))
    g2.join(code)
    assert h.wait().kind == "peer_joined"
    h.close()  # host drops
    assert g2.wait().kind == "peer_left"
    h2 = NetSession(url(relay))
    h2.room, h2.token = h.room, h.token
    assert h2.host() == code
    assert h2.wait().kind == "peer_joined"
    assert g2.wait().kind == "peer_joined"
    h2.close()
    g2.close()


def test_bad_token_rejected(relay):
    h = NetSession(url(relay))
    code = h.host()
    evil = NetSession(url(relay))
    evil.room, evil.token = code, "wrong"
    with pytest.raises(NetError):
        evil.host()
    h.close()


def test_rate_limit_on_guessing(relay):
    for _ in range(10):
        with pytest.raises(NetError):
            NetSession(url(relay)).join("AAAAAA")
    with pytest.raises(NetError, match="too many"):
        NetSession(url(relay)).join("AAAAAA")


def test_bad_handshake_and_oversize_frame(relay):
    with connect(url(relay)) as ws:
        ws.send(json.dumps({"t": "nope"}))
        assert json.loads(ws.recv())["t"] == "error"
    h = NetSession(url(relay))
    h.host()
    h._ws.send("x" * 10_000)  # over MAX_FRAME: relay drops the connection
    ev = h.wait()
    assert ev and ev.kind == "closed"


def test_unreachable_relay():
    with pytest.raises(NetError):
        NetSession("ws://127.0.0.1:1").host(timeout=1)
