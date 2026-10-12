import httpx
import pytest

from future.collectors import base
from future.collectors.greenhouse import GreenhouseCollector
from future.orchestrator.collect import SourceSpec, health_for, run_collector
from future.orchestrator.runlog import run_stage
from future.store import MemoryStore

JOBS = {"jobs": [
    {"id": 1, "title": " ML Engineer ", "absolute_url": "https://x/1", "location": {"name": "Bengaluru, India"},
     "content": "&lt;p&gt;Build models&lt;/p&gt;", "departments": [{"name": "AI"}], "offices": [{"name": "BLR"}],
     "updated_at": "2026-10-01T00:00:00Z"},
    {"id": 2, "title": "No URL job"},                                  # dropped: no absolute_url
]}


def collector_for(routes, boards):
    def handler(req):
        board = req.url.path.split("/")[3]
        status, body = routes[board]
        return httpx.Response(status, json=body)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GreenhouseCollector(boards=boards, client=client, delay_s=0, sleep=lambda s: None)


def test_parses_jobs_and_unescapes_html():
    recs = list(collector_for({"acme": (200, JOBS)}, ["acme"]).collect())
    assert len(recs) == 1
    r = recs[0]
    assert r.external_id == "acme:1" and r.url == "https://x/1"
    assert r.payload["title"] == "ML Engineer" and r.payload["location"] == "Bengaluru, India"
    assert r.payload["content_html"] == "<p>Build models</p>"


def test_bad_board_is_recorded_and_others_continue():
    c = collector_for({"gone": (404, {}), "acme": (200, JOBS)}, ["gone", "acme"])
    recs = list(c.collect())
    assert len(recs) == 1 and c.report.units_failed == 1 and c.report.units_ok == 1
    assert "gone" in c.report.errors[0]


def test_hash_ignores_updated_at_churn_but_tracks_content():
    a = GreenhouseCollector._to_record("acme", JOBS["jobs"][0])
    churn = dict(JOBS["jobs"][0], updated_at="2026-10-09T00:00:00Z")
    changed = dict(JOBS["jobs"][0], content="&lt;p&gt;New scope&lt;/p&gt;")
    assert GreenhouseCollector._to_record("acme", churn).content_hash == a.content_hash
    assert GreenhouseCollector._to_record("acme", changed).content_hash != a.content_hash


def test_get_json_retries_429_then_succeeds_and_does_not_retry_404():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if req.url.path == "/missing":
            return httpx.Response(404)
        return httpx.Response(429) if calls["n"] == 1 else httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://h")
    assert base.get_json(client, "https://h/x", sleep=lambda s: None) == {"ok": True}
    calls["n"] = 0
    with pytest.raises(httpx.HTTPStatusError):
        base.get_json(client, "https://h/missing", sleep=lambda s: None)
    assert calls["n"] == 1


def test_collect_stage_dedupes_on_second_run_and_sets_health():
    store, spec = MemoryStore(), SourceSpec("ats", "job", "greenhouse", None, "allowed")
    for expected_new in (1, 0):
        with run_stage(store, "collect") as ctx:
            stats = run_collector(store, ctx, collector_for({"acme": (200, JOBS)}, ["acme"]), spec)
        assert stats["new"] == expected_new
    src = store.sources_by_name["greenhouse"]
    assert src["health"] == "ok" and src["terms_verdict"] == "allowed"


def test_health_thresholds_match_roadmap():
    assert health_for(1.0) == "ok" and health_for(0.95) == "ok"
    assert health_for(0.9) == "degraded" and health_for(0.84) == "failing"
