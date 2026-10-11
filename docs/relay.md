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

## Hosted instance

Deployed 2026-10-11 on rik-ai-vm at `wss://chess.rik-kisnah.ai` (the client default).

- Code: `/opt/rik-chess-master` (venv in `.venv`); update with `git pull` then
  `uv pip install --python .venv/bin/python .` and `sudo systemctl restart rcm-relay`.
- `rcm-relay.service` (DynamicUser) listens on 127.0.0.1:8790. Port 8765 belongs to the MCP service.
- nginx site `chess.rik-kisnah.ai` proxies with WebSocket upgrade; certbot manages the cert
  (renews automatically).
- Cloudflare DNS: A record `chess` -> 129.146.101.64, DNS only (not proxied).
- Check: `systemctl is-active rcm-relay`; `sudo journalctl -u rcm-relay -n 50`.

Read `oci-runbooks/runbooks/personal/rik-ai-vms.md` before touching the host.
