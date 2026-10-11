# Lesson format

One YAML file per lesson in `lessons/`, sorted by filename within its group.

```yaml
id: castling            # unique
group: Special rules    # Piece basics | Special rules | Openings | Tactics
title: Castling
steps:
- type: explain
  text: Free text shown with a Next button.
- type: move            # one correct move (any of accept, UCI)
  fen: "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
  prompt: Castle kingside.
  accept: [e1g1]
  why: Shown after a correct move.
  hint: Shown when the learner asks.
  reply: e8e7           # optional opponent move played afterwards
- type: practice        # N legal moves with the named piece
  fen: "4k3/8/8/8/3N4/8/8/4K3 w - - 0 1"
  piece: knight
  count: 3
- type: line            # opening line played from memory
  color: white          # the learner's side; the opponent's moves are automatic
  moves: [e4, e5, Nf3, Nc6, Bc4]   # SAN, both sides, from the start position
  whys: [why e4, why Nf3, why Bc4] # one line per learner move
```

Lessons are validated on load (legal FENs, legal moves, one `why` per learner move) and
`tests/tutorial` plays every lesson through to the end.
