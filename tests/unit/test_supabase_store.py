"""SupabaseStore request shapes, verified offline with httpx.MockTransport."""
import datetime as dt
import json

import httpx
import pytest

from future.store import BudgetEntry, SupabaseStore


def make_store(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SupabaseStore("https://example.supabase.co", "secret-test", client=client)


def test_start_run_posts_and_returns_id():
    seen = {}

    def handler(req):
        seen.update(method=req.method, path=req.url.path, prefer=req.headers.get("prefer"),
                    auth=req.headers.get("authorization"), body=json.loads(req.content))
        return httpx.Response(201, json=[{"id": "run-1"}])

    rid = make_store(handler).start_run("collect", None, {"k": 1})
    assert rid == "run-1"
    assert seen["method"] == "POST" and seen["path"] == "/rest/v1/runs"
    assert seen["prefer"] == "return=representation" and seen["auth"] == "Bearer secret-test"
    assert seen["body"] == {"stage": "collect", "agent": None, "meta": {"k": 1}}


def test_tokens_used_since_sums_rows_with_filter():
    def handler(req):
        assert req.url.path == "/rest/v1/budget_ledger"
        assert "at=gte." in str(req.url)
        return httpx.Response(200, json=[{"total_tokens": 5}, {"total_tokens": 7}])

    assert make_store(handler).tokens_used_since(dt.datetime(2026, 10, 12, tzinfo=dt.timezone.utc)) == 12


def test_budget_entry_includes_total():
    body = {}

    def handler(req):
        body.update(json.loads(req.content))
        return httpx.Response(201)

    make_store(handler).add_budget(BudgetEntry(purpose="p", model="m", input_tokens=3, output_tokens=4))
    assert body["total_tokens"] == 7 and body["purpose"] == "p"


def test_setting_upsert_uses_merge_duplicates():
    prefer = {}

    def handler(req):
        prefer["v"] = req.headers.get("prefer")
        return httpx.Response(201)

    make_store(handler).set_setting("budget.daily_cap_tokens", 1000)
    assert prefer["v"] == "resolution=merge-duplicates"


def test_http_errors_raise_with_context():
    store = make_store(lambda req: httpx.Response(401, text="no auth"))
    with pytest.raises(RuntimeError, match="401"):
        store.get_setting("x")
