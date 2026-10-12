"""Evaluator: deterministic guards around the model (no model calls here)."""
import json
import pytest

from future.agents import evaluator as ev
from future.llm.claude_runner import ClaudeResult
from future.orchestrator.budget import BudgetExhausted, BudgetGuard, CAP_KEY, RESERVE_KEY
from future.store import MemoryStore

POSTING = "We need an ML engineer with experience fine-tuning LLMs using PyTorch. Visa sponsorship is available."


def base(**kw):
    d = {"fit": 4, "value": 4, "eligibility": "pass", "eligibility_reason": "ok", "legitimacy": "ok",
         "legitimacy_signal": "none", "gaps": [], "recommendation": "apply", "one_line": "x",
         "evidence": [{"quote": "experience fine-tuning LLMs using PyTorch", "supports": "fit"}]}
    d.update(kw)
    return d


def test_verbatim_quote_kept_whitespace_and_case_insensitive():
    data, dropped, flags = ev.validate(base(evidence=[{"quote": "Experience  fine-tuning LLMs", "supports": "f"}]), POSTING)
    assert len(data["evidence"]) == 1 and not dropped and not flags


def test_invented_quote_dropped_and_flagged():
    data, dropped, flags = ev.validate(base(evidence=[
        {"quote": "experience fine-tuning LLMs using PyTorch", "supports": "f"},
        {"quote": "competitive salary of 40 LPA", "supports": "value"}]), POSTING)
    assert len(data["evidence"]) == 1 and dropped == ["competitive salary of 40 LPA"]
    assert any("non-verbatim" in f for f in flags)


def test_all_quotes_invented_flags_no_evidence():
    _, _, flags = ev.validate(base(evidence=[{"quote": "made up", "supports": "f"}]), POSTING)
    assert "no verifiable evidence" in flags


@pytest.mark.parametrize("fit,elig,rec,expected", [
    (5, "pass", "maybe", "apply"), (4, "fail", "apply", "skip"), (3, "pass", "apply", "maybe"),
    (2, "pass", "apply", "skip"), (4, "unclear", "maybe", "maybe"), (4, "unclear", "apply", "apply"),
])
def test_recommendation_consistency(fit, elig, rec, expected):
    data, _, _ = ev.validate(base(fit=fit, eligibility=elig, recommendation=rec), POSTING)
    assert data["recommendation"] == expected


def test_prompt_marks_posting_as_untrusted_and_truncates():
    p = ev.user_prompt("ML Eng", "Acme", "Remote", ["unclear: x"], "A" * 20_000)
    assert "untrusted data" in p
    assert "A" * ev.MAX_POSTING_CHARS in p and "A" * (ev.MAX_POSTING_CHARS + 1) not in p


def fake_runner(*outputs, tokens=1000):
    """Returns each output in turn as plain text (single-turn JSON mode, no --json-schema)."""
    seq = list(outputs)
    calls = []

    def run(prompt, **kw):
        assert kw["json_schema"] is None and kw["model"] == "sonnet" and kw["effort"] == "medium"
        assert "OUTPUT FORMAT" in kw["system_prompt"]
        calls.append(prompt)
        out = seq.pop(0)
        text = out if isinstance(out, str) else json.dumps(out)
        return ClaudeResult(text=text, data=None, model="claude-sonnet-5-5", usage={"input_tokens": tokens},
                            cost_usd=0.0, duration_s=0.1, session_id=None)
    run.calls = calls
    return run


def test_invalid_json_gets_one_repair_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(ev, "PROFILE_FILE", tmp_path / "p.md")
    (tmp_path / "p.md").write_text("profile")
    runner = fake_runner(base(fit=9), base())        # fit=9 violates schema, then a valid answer
    out = ev.evaluate("ML Eng", "Acme", "Remote", [], POSTING, runner=runner)
    assert out.data["fit"] == 4 and out.tokens == 2000
    assert "PREVIOUS OUTPUT WAS INVALID" in runner.calls[1] and "fit" in runner.calls[1]
    assert any("attempt 1 invalid" in f for f in out.flags)


def test_invalid_twice_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(ev, "PROFILE_FILE", tmp_path / "p.md")
    (tmp_path / "p.md").write_text("profile")
    with pytest.raises(ValueError, match="invalid after retry"):
        ev.evaluate("ML Eng", "Acme", "Remote", [], POSTING, runner=fake_runner("not json", "still not"))


def test_evaluate_records_budget_and_returns_validated(monkeypatch, tmp_path):
    monkeypatch.setattr(ev, "PROFILE_FILE", tmp_path / "p.md")
    (tmp_path / "p.md").write_text("profile")
    store = MemoryStore()
    guard = BudgetGuard(store)
    out = ev.evaluate("ML Eng", "Acme", "Remote", [], POSTING, guard=guard, runner=fake_runner(base()))
    assert out.data["recommendation"] == "apply" and store.budget[0].total_tokens == 1000


def test_evaluate_refuses_when_budget_exhausted(monkeypatch, tmp_path):
    monkeypatch.setattr(ev, "PROFILE_FILE", tmp_path / "p.md")
    (tmp_path / "p.md").write_text("profile")
    store = MemoryStore()
    store.set_setting(CAP_KEY, 100)
    store.set_setting(RESERVE_KEY, 0)
    with pytest.raises(BudgetExhausted):
        ev.evaluate("ML Eng", "Acme", "Remote", [], POSTING, guard=BudgetGuard(store),
                    runner=fake_runner(base()))
