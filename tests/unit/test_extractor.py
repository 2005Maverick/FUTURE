"""Extractor guards (no model calls): verbatim-quote verification, URL grounding, retry."""
import datetime as dt
import json

import pytest

from future.agents import extractor as ex
from future.llm.claude_runner import ClaudeResult

TEXT = ("🔥 Hiring alert! Company name: micro1. Role: Machine Learning Engineer (Remote). "
        "Salary: $30 - $100 per hour. Apply: https://bit.ly/3TIOUo5 . Last date 20 Oct.")


def item(**kw):
    base = {"type": "contract", "title": "Machine Learning Engineer", "title_quote": "Role: Machine Learning Engineer",
            "org": "micro1", "org_quote": "Company name: micro1", "url": "https://bit.ly/3TIOUo5",
            "location": "Remote", "location_quote": "Machine Learning Engineer (Remote)", "remote": True,
            "deadline": "2026-10-20", "deadline_quote": "Last date 20 Oct", "pay": "$30 - $100 per hour",
            "pay_quote": "Salary: $30 - $100 per hour", "eligibility_notes": [], "scam_signals": []}
    base.update(kw)
    return base


def test_fully_grounded_item_kept_unchanged():
    kept, flags = ex.verify({"opportunities": [item()]}, TEXT)
    assert kept == [item()] and flags == []


def test_unsupported_fields_are_nulled_not_guessed():
    kept, flags = ex.verify({"opportunities": [item(org="OpenAI", org_quote="Company: OpenAI",
                                                    deadline="2026-11-01", deadline_quote="deadline Nov 1")]}, TEXT)
    assert kept[0]["org"] is None and kept[0]["deadline"] is None
    assert any("org unsupported" in f for f in flags) and any("deadline unsupported" in f for f in flags)


def test_url_not_present_in_text_is_dropped():
    kept, flags = ex.verify({"opportunities": [item(url="https://micro1.ai/jobs/ml")]}, TEXT)
    assert kept[0]["url"] is None and any("url not in text" in f for f in flags)


def test_record_without_verifiable_title_or_url_is_dropped():
    kept, _ = ex.verify({"opportunities": [item(title="Data Scientist", title_quote="Data Scientist role",
                                                url="https://nowhere.example")]}, TEXT)
    assert kept == []


def test_url_with_trailing_punctuation_matches():
    kept, _ = ex.verify({"opportunities": [item(url="https://bit.ly/3TIOUo5.")]}, TEXT)
    assert kept[0]["url"] == "https://bit.ly/3TIOUo5."


def fake(outputs):
    seq = list(outputs)

    def run(prompt, **kw):
        assert kw["model"] == "haiku" and kw["json_schema"] is None and "TODAY: 2026-10-12" in prompt
        out = seq.pop(0)
        return ClaudeResult(text=out if isinstance(out, str) else json.dumps(out), data=None,
                            model="claude-haiku-5-5", usage={"input_tokens": 1500}, cost_usd=0, duration_s=0.1, session_id=None)
    return run


def test_extract_end_to_end_with_retry_on_schema_error():
    bad = {"opportunities": [item(type="gig")]}            # invalid enum
    out = ex.extract(TEXT, source="whatsapp", today=dt.date(2026, 10, 12), runner=fake([bad, {"opportunities": [item()]}]))
    assert len(out.opportunities) == 1 and out.tokens == 3000 and any("attempt 1 invalid" in f for f in out.flags)


def test_not_an_opportunity_returns_empty():
    out = ex.extract("Good morning! Keep learning 💪", source="whatsapp", today=dt.date(2026, 10, 12),
                     runner=fake([{"opportunities": []}]))
    assert out.opportunities == []


def test_invalid_twice_raises():
    with pytest.raises(ValueError):
        ex.extract(TEXT, source="whatsapp", today=dt.date(2026, 10, 12), runner=fake(["nope", "still nope"]))
