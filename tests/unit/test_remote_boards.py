import httpx

from future.collectors.remote_boards import HimalayasCollector, RemotiveCollector
from future.pipeline import normalize as n


def h_job(i, restr, title="Machine Learning Engineer"):
    return {"guid": f"https://himalayas.app/j/{i}", "title": title, "companyName": f"Co{i}", "companySlug": f"co{i}",
            "locationRestrictions": restr, "description": "<p>Build ML.</p>", "minSalary": 40000, "maxSalary": 60000,
            "currency": "USD", "salaryPeriod": "year", "seniority": ["Entry-level"]}


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_himalayas_maps_location_pay_org_and_dedups_across_queries():
    page = {"jobs": [h_job(1, []), h_job(2, ["India"]), h_job(3, ["United States"])]}
    c = HimalayasCollector(queries=["ml", "ai"], client=client(lambda r: httpx.Response(200, json=page)),
                           delay_s=0, sleep=lambda s: None)
    recs = list(c.collect())
    assert len(recs) == 3                                     # same jobs from 2 queries counted once
    assert recs[0].payload["location"] == "Remote - Worldwide" and recs[0].payload["org"] == "Co1"
    assert "Salary: 40000–60000 USD per year" in recs[0].payload["content_html"]
    elig = [n.from_ats({"url": r.url, "content_hash": r.content_hash, "payload": r.payload}).eligibility.result for r in recs]
    assert elig[0] in ("pass", "unclear") and elig[1] in ("pass", "unclear") and elig[2] == "fail"


def test_himalayas_stops_paging_on_short_page():
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, json={"jobs": [h_job(len(calls), [])]})
    list(HimalayasCollector(queries=["ml"], client=client(handler), max_pages=3, delay_s=0, sleep=lambda s: None).collect())
    assert len(calls) == 1


def test_remotive_dedups_respects_rate_limit_and_uses_org():
    slept = []
    body = {"jobs": [{"id": 7, "url": "https://remotive.com/remote-jobs/x-7", "title": "AI Engineer",
                      "company_name": "Acme", "candidate_required_location": "Worldwide", "description": "<p>x</p>"}]}
    c = RemotiveCollector(client=client(lambda r: httpx.Response(200, json=body)), delay_s=31, sleep=slept.append)
    recs = list(c.collect())
    assert len(recs) == 1 and recs[0].payload["org"] == "Acme"
    assert slept == [31]                                       # one pause between the two queries


def test_remotive_failure_is_recorded_not_raised():
    c = RemotiveCollector(queries=["ml"], client=client(lambda r: httpx.Response(429)), sleep=lambda s: None)
    assert list(c.collect()) == [] and c.report.units_failed == 1
