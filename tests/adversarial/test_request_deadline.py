"""Regression for the 2026-10-12 hang: a daily run sat ~5h on one HTTPS connection
because httpx's timeout is per-read, not per-request. A server that trickles bytes
forever must now be cut off at the whole-request deadline, and a collector must
record the board as failed and move on."""
import itertools

import httpx
import pytest

from future.collectors import base
from future.collectors.greenhouse import GreenhouseCollector


class Trickle(httpx.SyncByteStream):
    """Sends a tiny chunk forever — never completes."""

    def __iter__(self):
        for _ in itertools.count():
            yield b" "


def trickle_client():
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, stream=Trickle())))


def fake_clock(step=1.0):
    t = itertools.count(0, step)
    return lambda: next(t)


def test_fetch_cuts_off_a_trickling_response_at_the_deadline():
    with pytest.raises(base.RequestDeadline):
        base.fetch(trickle_client(), "https://slow.example/jobs", deadline_s=30, clock=fake_clock())


def test_get_json_retries_a_deadline_only_once(monkeypatch):
    calls = []

    def stalled(c, u, d):
        calls.append(u)
        raise base.RequestDeadline("x")
    monkeypatch.setattr(base, "fetch", stalled)
    slept = []
    with pytest.raises(base.RequestDeadline):
        base.get_json(httpx.Client(), "https://slow.example", retries=3, sleep=slept.append)
    assert len(calls) == 2 and len(slept) == 1


def test_other_network_errors_still_get_all_retries(monkeypatch):
    calls = []

    def flaky(c, u, d):
        calls.append(u)
        raise httpx.ConnectError("reset")
    monkeypatch.setattr(base, "fetch", flaky)
    with pytest.raises(httpx.ConnectError):
        base.get_json(httpx.Client(), "https://flaky.example", retries=3, sleep=lambda s: None)
    assert len(calls) == 4


def test_collector_records_stalled_board_and_continues(monkeypatch):
    def fake_fetch(client, url, deadline_s=60):
        if "/stalled/" in url:
            raise base.RequestDeadline("exceeded 60s")
        return 200, b'{"jobs": [{"id": 1, "title": "ML Engineer", "absolute_url": "https://x/1"}]}'
    monkeypatch.setattr(base, "fetch", fake_fetch)
    c = GreenhouseCollector(boards=["stalled", "ok"], client=httpx.Client(), delay_s=0, sleep=lambda s: None)
    recs = list(c.collect())
    assert len(recs) == 1 and c.report.units_failed == 1 and c.report.ok_units == ["ok"]
    assert "RequestDeadline" in c.report.errors[0]


def test_normal_json_still_parses():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"a": 1})))
    assert base.get_json(client, "https://ok.example") == {"a": 1}
