import datetime as dt
import json

import httpx
import pytest

from future.collectors import hackathons as h
from future.collectors.hackathons import KaggleCollector, MLHCollector

TODAY = dt.date(2026, 10, 13)
FAKE = "fake-token-for-tests"


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------- shared filter ----------

@pytest.mark.parametrize("title,org", [
    ("Smart India Hackathon 2026", "AICTE"),
    ("SIH 2025 Grand Finale", "MoE"),
    ("iDEX Open Challenge", "Ministry of Defence"),
    ("DISC 13", "Innovations for Defence Excellence"),
    ("Defence India Startup Challenge 12", "Acme"),
])
def test_gov_hackathons_are_excluded(title, org):
    assert h.drop_reason({"title": title, "org": org, "deadline": "2026-12-01"}, TODAY) == "government"


@pytest.mark.parametrize("title", ["HackMIT", "Index Fund Hackathon", "Siheung Code Jam", "Disco Hacks"])
def test_non_gov_titles_are_kept(title):
    assert h.drop_reason({"title": title, "org": "Acme", "deadline": "2026-12-01"}, TODAY) is None


def test_expired_and_missing_deadlines():
    assert h.drop_reason({"title": "X", "deadline": "2026-10-12"}, TODAY) == "expired"
    assert h.drop_reason({"title": "X", "deadline": "2026-10-13"}, TODAY) is None     # due today still counts
    assert h.drop_reason({"title": "X", "deadline": None}, TODAY) is None
    assert h.drop_reason({"title": "X", "deadline": "soon"}, TODAY) is None


def test_mlh_season_rolls_over_in_august():
    assert h.current_mlh_season(dt.date(2026, 10, 13)) == 2027
    assert h.current_mlh_season(dt.date(2027, 3, 1)) == 2027
    assert h.current_mlh_season(dt.date(2027, 8, 1)) == 2028


# ---------- MLH ----------

def mlh_event(slug, name, starts="2026-10-16T19:00:00Z", fmt="physical", status="pending"):
    return {"id": f"id-{slug}", "slug": slug, "name": name, "status": status, "startsAt": starts,
            "endsAt": "2026-10-18T19:00:00Z", "url": f"/events/{slug}/prizes", "location": "Gainesville, Florida",
            "formatType": fmt, "websiteUrl": f"https://{slug}.com/", "region": "AMER",
            "customFields": {"underserved_types": [], "hackathon_focus": ["Software"]},
            "venueAddress": {"city": "Gainesville", "state": "Florida", "country": "US"}}


def mlh_page(upcoming, past=()):
    data = {"component": "SeasonEvents/Index",
            "props": {"upcomingEvents": list(upcoming), "pastEvents": list(past)}}
    return ('<html><body><div id="app"></div><script data-page="app" type="application/json">'
            + json.dumps(data) + "</script></body></html>")


def test_mlh_parses_events_modes_and_filters():
    events = [mlh_event("swamphacks-xii", "SwampHacks XII"),
              mlh_event("technica", "Technica Hacks", fmt="hybrid_physical"),
              mlh_event("old-hack", "Old Hack", starts="2026-10-01T10:00:00Z"),           # expired
              mlh_event("sih", "Smart India Hackathon Nodal Round"),                       # government
              mlh_event("done", "Done Hacks", status="ended"),
              mlh_event("swamphacks-xii", "SwampHacks XII")]                               # duplicate
    urls = []

    def handler(req):
        urls.append(str(req.url))
        return httpx.Response(200, text=mlh_page(events, [mlh_event("past", "Past Hack", status="ended")]))
    c = MLHCollector(client=client(handler), today=TODAY)
    recs = list(c.collect())
    assert urls == ["https://www.mlh.com/seasons/2027/events"]
    assert [r.external_id for r in recs] == ["swamphacks-xii", "technica"]
    p = recs[0].payload
    assert p["track"] == "hackathon" and p["opp_type"] == "hackathon" and p["board"] == "mlh"
    assert p["deadline"] == "2026-10-16" and p["mode"] == "in-person" and p["prize"] is None
    assert p["location"] == "Gainesville, Florida, US" and p["departments"] == ["Software"]
    assert recs[0].url == "https://swamphacks-xii.com/"
    assert "https://www.mlh.com/events/swamphacks-xii/prizes" in p["content_html"]
    assert recs[1].payload["mode"] == "hybrid"
    assert c.dropped == {"expired": 1, "government": 1}
    assert c.report.units_ok == 1 and c.report.records == 2 and c.report.ok_units == ["season-2027"]


def test_mlh_content_hash_is_stable_and_changes_with_content():
    def run(name):
        page = mlh_page([mlh_event("a", name)])
        return list(MLHCollector(season=2027, client=client(lambda r: httpx.Response(200, text=page)),
                                 today=TODAY).collect())[0].content_hash
    assert run("A Hacks") == run("A Hacks") != run("A Hacks 2")


@pytest.mark.parametrize("response", [httpx.Response(503), httpx.Response(200, text="<html>no data</html>"),
                                      httpx.Response(200, text='<script data-page="app">{"props": {}}</script>')])
def test_mlh_failure_is_recorded_not_raised(response):
    c = MLHCollector(season=2027, client=client(lambda r: response), today=TODAY)
    assert list(c.collect()) == []
    assert c.report.units_failed == 1 and c.report.units_ok == 0 and c.report.errors


# ---------- Kaggle ----------

def comp(i, deadline="2026-11-02T23:59:00Z", entry="2026-10-26T11:59:00Z", category="Featured",
         reward="850,000 Usd", title=None, org="Abstraction and Reasoning Corpus"):
    return {"id": i, "ref": f"https://www.kaggle.com/competitions/c{i}", "url": f"https://www.kaggle.com/competitions/c{i}",
            "title": title or f"Comp {i}", "description": "Create an AI", "organizationName": org,
            "category": category, "reward": reward, "deadline": deadline, "newEntrantDeadline": entry,
            "enabledDate": "2026-03-25T17:38:23.913Z", "maxTeamSize": 8, "evaluationMetric": "Accuracy",
            "teamCount": 4214, "tags": [{"name": "artificial intelligence"}, {"name": "custom metric"}]}


def test_kaggle_parses_sends_bearer_and_stops_on_short_page():
    pages = {1: [comp(i) for i in range(1, 21)], 2: [comp(21), comp(22)]}
    seen = []

    def handler(req):
        seen.append((req.url.params["page"], req.headers.get("authorization")))
        return httpx.Response(200, json=pages.get(int(req.url.params["page"]), []))
    slept = []
    c = KaggleCollector(token=FAKE, client=client(handler), delay_s=1, sleep=slept.append, today=TODAY)
    recs = list(c.collect())
    assert [p for p, _ in seen] == ["1", "2"]                     # short page 2 ends paging, no page 3
    assert all(a == f"Bearer {FAKE}" for _, a in seen)
    assert slept == [1] and len(recs) == 22 and c.report.units_ok == 2
    p = recs[0].payload
    assert p["opp_type"] == "competition" and p["track"] == "hackathon" and p["mode"] == "online"
    assert p["deadline"] == "2026-10-26" and p["final_deadline"] == "2026-11-02"
    assert p["prize"] == "850,000 USD" and p["org"] == "Abstraction and Reasoning Corpus"
    assert p["departments"] == ["artificial intelligence", "custom metric"]
    assert "4214" not in p["content_html"]                         # volatile counts stay out of the hash


def test_kaggle_stops_on_empty_page_and_respects_max_pages():
    calls = []

    def full(req):
        calls.append(req.url.params["page"])
        return httpx.Response(200, json=[comp(int(req.url.params["page"]) * 100 + i) for i in range(20)])
    list(KaggleCollector(token=FAKE, client=client(full), max_pages=3, sleep=lambda s: None, today=TODAY).collect())
    assert calls == ["1", "2", "3"]

    empty_calls = []

    def empty(req):
        empty_calls.append(1)
        return httpx.Response(200, json=[])
    c = KaggleCollector(token=FAKE, client=client(empty), sleep=lambda s: None, today=TODAY)
    assert list(c.collect()) == [] and empty_calls == [1]


def test_kaggle_filters_tutorials_expired_gov_and_no_prize():
    data = [comp(1),
            comp(2, category="Getting Started", reward="Knowledge", deadline="2030-01-01T00:00:00Z", entry=None),
            comp(3, deadline="2026-10-14T23:59:00Z", entry="2026-10-07T23:59:00Z"),     # entry closed
            comp(4, title="Smart India Hackathon ML Track"),
            comp(5, category="Playground", reward="Kudos", entry=None)]
    c = KaggleCollector(token=FAKE, client=client(lambda r: httpx.Response(200, json=data)), today=TODAY)
    recs = list(c.collect())
    assert [r.external_id for r in recs] == ["1", "5"]
    assert recs[1].payload["prize"] is None and recs[1].payload["deadline"] == "2026-11-02"   # falls back to final
    assert c.dropped == {"expired": 1, "government": 1}


def test_kaggle_without_token_records_failure_and_makes_no_request():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json=[])
    c = KaggleCollector(token="", client=client(handler), today=TODAY)
    assert list(c.collect()) == [] and calls == [] and c.report.units_failed == 1


@pytest.mark.parametrize("response", [httpx.Response(401, json={"code": 401}), httpx.Response(500),
                                      httpx.Response(200, json={"error": "x"})])
def test_kaggle_failure_is_recorded_not_raised_and_token_not_leaked(response):
    c = KaggleCollector(token=FAKE, client=client(lambda r: response), sleep=lambda s: None, today=TODAY)
    assert list(c.collect()) == []
    assert c.report.units_failed == 1 and c.report.units_ok == 0
    assert not any(FAKE in e for e in c.report.errors)
