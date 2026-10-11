.PHONY: setup run test test-fast lint fmt perft relay clean
setup:
	uv sync
run:
	uv run rcm
test:
	uv run pytest -q
test-fast:
	uv run pytest -q tests/core
lint:
	uv run ruff check . && uv run ruff format --check .
fmt:
	uv run ruff format . && uv run ruff check --fix .
perft:
	uv run pytest -q -m slow tests/core/test_perft.py
relay:
	uv run rcm-relay
clean:
	rm -rf .venv .pytest_cache .ruff_cache .coverage htmlcov ~/.rik-chess-master/autosave.pgn
