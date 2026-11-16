"""Offline tests for shared/llm.py and shared/pii_guard.py. No network or API key needed."""
import json
from types import SimpleNamespace

import pytest

from shared import llm
from shared.pii_guard import PIIError, assert_no_pii, find_pii


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "LOG_FILE", tmp_path / "llm_calls.jsonl")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    monkeypatch.setattr(llm, "_client", None)


def fake_client(message, captured=None):
    def create(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], model="test/model",
                               usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 7}))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def no_network():
    raise AssertionError("network client was used")


# ---------- llm.py ----------

def test_pii_is_blocked_before_anything_is_sent(monkeypatch):
    monkeypatch.setattr(llm, "_get_client", no_network)
    with pytest.raises(PIIError):
        llm.ask([{"role": "user", "content": "Call Jane on 0491 570 156"}])
    log = llm.LOG_FILE.read_text()
    assert "BLOCKED_REQUEST" in log and "0491" not in log  # logged, but without the PII


def test_missing_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(llm.LLMError, match="OPENROUTER_API_KEY"):
        llm.ask([{"role": "user", "content": "hi"}])


def test_text_reply_uses_temperature_zero_and_is_logged(monkeypatch):
    captured = {}
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client(
        SimpleNamespace(content="Score is 63 (HIGH).", tool_calls=None), captured))
    reply = llm.ask([{"role": "user", "content": "Explain cust_af4200"}], purpose="explain")
    assert reply.text == "Score is 63 (HIGH)." and reply.tool_calls == []
    assert captured["temperature"] == 0 and captured["model"] == "test/model"
    entry = json.loads(llm.LOG_FILE.read_text().splitlines()[-1])
    assert entry["event"] == "OK" and entry["purpose"] == "explain"


def test_tool_calls_are_parsed(monkeypatch):
    tc = SimpleNamespace(id="call_1", function=SimpleNamespace(name="account_score_all", arguments="{}"))
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client(SimpleNamespace(content=None, tool_calls=[tc])))
    tools = [{"type": "function", "function": {"name": "account_score_all", "parameters": {"type": "object"}}}]
    reply = llm.ask([{"role": "user", "content": "go"}], tools=tools, purpose="runbook:a_account")
    assert reply.tool_calls[0].name == "account_score_all" and reply.tool_calls[0].arguments == {}
    assert reply.message["tool_calls"][0]["function"]["name"] == "account_score_all"


def test_reply_with_pii_is_blocked(monkeypatch):
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client(
        SimpleNamespace(content="Email jane.citizen@example.com", tool_calls=None)))
    with pytest.raises(PIIError):
        llm.ask([{"role": "user", "content": "hi"}])


def test_explain_sends_facts_only(monkeypatch):
    captured = {}
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client(
        SimpleNamespace(content=" Salary stopped. ", tool_calls=None), captured))
    out = llm.explain({"customer_token": "cust_af4200", "score": 63, "reasons": ["SALARY_STOPPED"]})
    assert out == "Salary stopped."
    assert "cust_af4200" in captured["messages"][1]["content"]


# ---------- pii_guard.py ----------

@pytest.mark.parametrize("text,kind", [
    ("jane.citizen@example.com", "EMAIL"),
    ("0491 570 156", "AU_MOBILE"),
    ("+61 491 570 156", "AU_MOBILE"),
    ("02 9876 5432", "AU_LANDLINE"),
    ("BSB 032-101", "BSB"),
    ("DOB 14/03/1988", "DATE_OF_BIRTH"),
    ("card 4111 1111 1111 1111", "CARD_NUMBER"),
])
def test_guard_catches_pii(text, kind):
    assert kind in find_pii(text)


def test_guard_allows_normal_pipeline_data():
    clean = {"customer_token": "cust_af4200", "staff": "staff_b38", "score": 63, "band": "HIGH",
             "timestamp": "2026-11-16T10:00:00", "balance_after": "-405700.00", "promise_id": "P-0042",
             "hash": "9f2c1e0b7a6d5c4b3a291807f6e5d4c3b2a19087f6e5d4c3b2a1908776655443"}
    assert_no_pii(clean)  # must not raise


def test_guard_never_reveals_the_pii():
    with pytest.raises(PIIError) as e:
        assert_no_pii({"text": "call 0491 570 156"})
    assert "0491" not in str(e.value)


def test_mock_outputs_are_clean():
    """Everything in mock_input_output/*/output must pass the guard; the raw inputs must not."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "mock_input_output"
    for f in root.glob("*/output/*"):
        assert_no_pii(f.read_text())
    assert find_pii((root / "A_account/input/transactions_raw.csv").read_text())
    assert find_pii((root / "B_interaction/input/form_submissions.json").read_text())
