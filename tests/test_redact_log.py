import json
import logging

from keepsake.log import LOG_FILE, log_event, setup_logging, tail
from keepsake.redact import REDACTED, redact, redact_text


def test_sensitive_keys_redacted_whatever_the_value():
    out = redact({"access_token": "abc", "nested": {"Refresh-Token": "xyz", "ok": 1}, "user_code": "ABCD-EFGH"})
    assert out["access_token"] == REDACTED
    assert out["nested"]["Refresh-Token"] == REDACTED
    assert out["nested"]["ok"] == 1
    assert out["user_code"] == REDACTED


def test_free_text_patterns():
    # Token-shaped fixtures are assembled at runtime so the source never holds
    # a literal that secret scanners would flag.
    jwt = ".".join(["ey" + "JhbGciOiJIUzI1NiJ9", "ey" + "JzdWIiOiIxMjM0NTY3ODkwIn0", "abcdefghijk"])
    gh_token = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz0123"
    text = (
        f"Authorization: Bearer {jwt} "
        f"refresh_token=0.AAAbbbCCC token {gh_token} "
        "mail someone@example.com path /var/home/alice/.local/share/Steam and /home/bob/x"
    )
    out = redact_text(text)
    assert "ey" + "J" not in out
    assert "0.AAAbbbCCC" not in out
    assert gh_token not in out
    assert "someone@example.com" not in out
    assert "alice" not in out and "bob" not in out
    assert "~/.local/share/Steam" in out


def test_log_lines_are_json_and_redacted(tmp_path):
    setup_logging(str(tmp_path))
    log_event(logging.INFO, "auth.test", "Got token access_token=SECRET1", refresh_token="SECRET2", game="g")
    for handler in logging.getLogger("keepsake").handlers:
        handler.flush()
    raw = (tmp_path / LOG_FILE).read_text(encoding="utf-8")
    assert "SECRET1" not in raw and "SECRET2" not in raw
    records = tail(str(tmp_path))
    assert records[-1]["event"] == "auth.test"
    assert records[-1]["fields"]["game"] == "g"
    json.loads(raw.splitlines()[-1])


def test_tail_skips_bad_lines_and_limits(tmp_path):
    (tmp_path / LOG_FILE).write_text('{"a":1}\nnot json\n{"a":2}\n{"a":3}\n', encoding="utf-8")
    assert [r["a"] for r in tail(str(tmp_path), 2)] == [2, 3]
    assert [r["a"] for r in tail(str(tmp_path), 10)] == [1, 2, 3]
    assert tail(str(tmp_path / "missing")) == []
