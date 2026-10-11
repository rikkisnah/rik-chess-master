"""Rules core: a thin wrapper over python-chess. Only this package imports `chess`
for rules; the rest of the app talks to Game."""

from rcm.core.game import Game, GameEnd
from rcm.core.pgn import PgnError, dumps, load_all, loads, read_file, write_file

__all__ = ["Game", "GameEnd", "PgnError", "dumps", "loads", "load_all", "read_file", "write_file"]
