# CLAUDE.md

Guidance for Claude Code and Codex CLI in this repo (CLAUDE.md and AGENTS.md are identical; edit both).

## Commands

- `make setup` / `make run` / `make test` / `make test-fast` / `make perft` / `make lint` / `make fmt`
- Single test: `uv run pytest -q tests/modes/test_modes.py::test_remote_resign`
- UI tests need a display (they skip without one); headless: `xvfb-run -a uv run pytest -q tests/ui`

## Architecture

Every mode plays through `rcm.core.Game` (a python-chess wrapper). Only `rcm/core` implements
rules. `rcm.modes.Session` subclasses are UI-agnostic controllers; the UI calls `session.pump()`
on a timer to drain work posted from engine and network threads. `rcm.ui` must not touch rules.

## Gotchas

- Always close `chess.engine.SimpleEngine` (non-daemon thread): an unclosed engine hangs pytest at exit.
- Tk `event_generate` needs a mapped widget: call `root.update()` after `pack()` in UI tests.
- Relay default port is 8790 (8765 is used on rik-ai-vm). The relay is deployed at wss://chess.rik-kisnah.ai (see docs/relay.md).
- Lessons in `lessons/` were generated once and are now hand-editable YAML; `tests/tutorial` validates and solves them.
