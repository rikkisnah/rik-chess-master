# Decisions

Resolved from the spec's open decisions (2026-10-10):

| Decision | Choice |
| --- | --- |
| Rules core | `python-chess`, wrapped by `rcm.core.Game` (only place rules live) |
| UI toolkit | Tkinter |
| Remote play | Relay with room codes, speaking WebSocket (instead of raw TCP lines) |
| Relay host | rik-ai-vm (code only; deployment left as a deliberate manual step) |
| Master level | Stockfish if installed (`RCM_STOCKFISH` overrides the path), else Club with a notice |
| Tutorial scope | All 4 groups: 6 + 5 + 5 + 5 lessons, 5 puzzles per tactic |
| Clocks | Out of v1. `RCM_Clock` is accepted and preserved on load but unused |
| Piece art | Cburnett |
| Names | package and command `rcm`, relay command `rcm-relay` |
| Famous-game commentary | Drafted by Claude, approved for now; edit freely |

Deviations from the spec text:

* Dependencies are `python-chess`, `pyyaml` and `websockets`, not "none in v0.1".
* `make test-fast` runs the core tests (about 1 s). Perft depth 4 and 5 and Kiwipete depth 4
  carry a `slow` marker and run with `make perft` (about 20 s).
* Draw by threefold repetition and the 50-move rule are applied automatically rather than claimed.
* The relay default port is 8790 because 8765 is taken on rik-ai-vm.
