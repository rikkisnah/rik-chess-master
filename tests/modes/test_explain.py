import time

import chess
import pytest

from rcm import explain
from rcm.core import Game
from rcm.modes import LocalSession

KEY = "sk-ant-test-123"


@pytest.fixture(autouse=True)
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("RCM_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("RCM_HOME", str(tmp_path / "home"))
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path / "cfg"


def test_parse_env_forms():
    text = (
        "# comment\n"
        f'export ANTHROPIC_API_KEY="{KEY}"\n'
        "ANTHROPIC_MODEL = 'claude-haiku-4-5-20251001' \n"
        "OTHER=a b # trailing\n"
        "sk-ant-bare\n"
    )
    v = explain.parse_env(text)
    assert v["ANTHROPIC_API_KEY"] == "sk-ant-bare"  # later bare key wins, as in a file
    assert v["ANTHROPIC_MODEL"] == "claude-haiku-4-5-20251001"
    assert v["OTHER"] == "a b"


def test_settings_default_off_then_file_then_env(cfg, monkeypatch):
    s = explain.load_settings()
    assert not s.enabled and s.model == explain.DEFAULT_MODEL
    cfg.mkdir()
    (cfg / "anthropic.env").write_text(f"ANTHROPIC_API_KEY={KEY}\nANTHROPIC_MODEL=m-file\n")
    s = explain.load_settings()
    assert s.enabled and s.api_key == KEY and s.model == "m-file"
    monkeypatch.setenv("ANTHROPIC_MODEL", "m-env")
    assert explain.load_settings().model == "m-env"


def test_legacy_bare_key_file_and_empty_file(cfg):
    cfg.mkdir()
    (cfg / "anthropic_api_key").write_text("")
    assert not explain.load_settings().enabled
    (cfg / "anthropic_api_key").write_text(KEY + "\n")
    assert explain.load_settings().api_key == KEY


def test_prompt_and_request_shape():
    g = Game()
    for san in ("e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#"):
        g.push_san(san)
    seen = {}

    def send(body, key):
        seen.update(body=body, key=key)
        return {"content": [{"type": "text", "text": " Mate! "}]}

    out = explain.explain_last_move(g, explain.Settings(KEY, "m-x"), send)
    assert out == "Mate!"
    body = seen["body"]
    assert seen["key"] == KEY and body["model"] == "m-x"
    prompt = body["messages"][0]["content"]
    assert "White played Qxf7#" in prompt and "checkmate" in prompt and "capture" in prompt
    assert KEY not in str(body)  # the key only goes in a header


def test_errors_are_clean():
    g = Game()
    with pytest.raises(explain.ExplainError, match="anthropic.env"):
        explain.explain_last_move(g, explain.Settings(None))
    with pytest.raises(explain.ExplainError, match="Play a move"):
        explain.explain_last_move(g, explain.Settings(KEY))
    g.push_san("e4")
    with pytest.raises(explain.ExplainError, match="Unexpected"):
        explain.explain_last_move(g, explain.Settings(KEY), lambda b, k: {"oops": 1})
    with pytest.raises(explain.ExplainError, match="no text"):
        explain.explain_last_move(g, explain.Settings(KEY), lambda b, k: {"content": []})


def pump_until(cond, s, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        s.pump()
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_session_explain_flow_and_staleness(cfg):
    cfg.mkdir()
    (cfg / "anthropic.env").write_text(f"ANTHROPIC_API_KEY={KEY}\n")
    s = LocalSession(autosave=False)
    s.request_explain()
    assert "Play a move first" in s.message
    s.move(chess.E2, chess.E4)
    s.request_explain(lambda b, k: {"content": [{"type": "text", "text": "Opens the centre."}]})
    assert s.explaining
    assert pump_until(lambda: not s.explaining, s)
    assert s.current_explanation() == "Opens the centre."
    s.move(chess.E7, chess.E5)
    assert s.current_explanation() == ""  # stale once the position changes


def test_session_explain_without_key_sets_hint_and_no_thread():
    s = LocalSession(autosave=False)
    s.move(chess.E2, chess.E4)
    s.request_explain()
    assert not s.explaining and "anthropic.env" in s.message


def test_session_explain_error_shown(cfg):
    cfg.mkdir()
    (cfg / "anthropic.env").write_text(f"ANTHROPIC_API_KEY={KEY}\n")
    s = LocalSession(autosave=False)
    s.move(chess.E2, chess.E4)

    def boom(b, k):
        raise explain.ExplainError("Claude API error 401: bad key. Check ANTHROPIC_API_KEY.")

    s.request_explain(boom)
    assert pump_until(lambda: not s.explaining, s)
    assert "401" in s.message and KEY not in s.message
