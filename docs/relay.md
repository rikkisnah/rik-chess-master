# Relay

`rcm-relay` is a small WebSocket server. It pairs two clients by room code and forwards text
frames unchanged. It stores nothing but the open rooms in memory.

```bash
uv run rcm-relay --host 0.0.0.0 --port 8790
```

## Protocol

First frame from a client (JSON):

| Frame | Reply |
| --- | --- |
| `{"t":"host"}` | `{"t":"hosted","room":"K7M2QX","token":"..."}` |
| `{"t":"host","room":R,"token":T}` (reconnect) | `hosted` again |
| `{"t":"join","room":R}` | `{"t":"joined"}`; the host gets `{"t":"peer_joined"}` |

Errors are `{"t":"error","reason":"..."}` followed by a close. When one side leaves, the other
receives `{"t":"peer_left"}`. The room stays open (host holds a token, guest re-joins by code)
until it has been idle for an hour.

Game frames (between clients; the relay does not read them): `start`, `ready`, `move` (SAN),
`resign`, `draw_offer/accept/decline`, `takeback_req/accept/decline`.

## Safety limits

Room codes use 6 characters from a 32-symbol alphabet (about 10^9 codes). Frames over 4 KB are
rejected, at most 500 rooms exist, and an IP gets 10 failed joins per minute. Treat the code as a
shared secret for a casual game, not as authentication.

## Hosting it on rik-ai-vm (not done yet)

Read `oci-runbooks/runbooks/personal/rik-ai-vms.md` first. Port 8765 is already used by the MCP
service on that host, so the relay defaults to **8790**. Sketch:

1. Install the project (or just `uv run rcm-relay`) and a systemd unit running
   `rcm-relay --host 127.0.0.1 --port 8790`.
2. nginx site for e.g. `chess.rik-kisnah.ai` proxying `/` to `127.0.0.1:8790` with
   `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`
   and a long `proxy_read_timeout`.
3. DNS plus TLS, then clients use `wss://chess.rik-kisnah.ai`.

Nothing in this repo touches the host; do these steps deliberately.
