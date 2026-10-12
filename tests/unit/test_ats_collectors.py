"""S03.01: Ashby, Lever, Workable collectors map their APIs onto the common payload shape."""
import httpx

from future.collectors.ats import AshbyCollector, LeverCollector, WorkableCollector
from future.pipeline import normalize as n

ASHBY = {"jobs": [
    {"id": "a1", "title": "Research Engineer, Speech", "location": "Bengaluru", "isRemote": False, "workplaceType": "OnSite",
     "jobUrl": "https://jobs.ashbyhq.com/sarvam/a1", "descriptionHtml": "<p>Train speech LLMs.</p>",
     "secondaryLocations": [{"location": "Delhi"}], "department": "Research", "team": "Speech", "isListed": True,
     "compensation": {"scrapeableCompensationSalarySummary": "₹30L – ₹45L"}, "publishedAt": "2026-10-01"},
    {"id": "a2", "title": "Unlisted", "jobUrl": "https://x/a2", "isListed": False},
    {"id": "a3", "title": "ML Engineer", "location": "", "isRemote": True, "jobUrl": "https://x/a3", "descriptionHtml": ""},
]}
LEVER = [
    {"id": "l1", "text": "Machine Learning Engineer", "hostedUrl": "https://jobs.lever.co/meesho/l1",
     "categories": {"location": "Bangalore, Karnataka", "allLocations": ["Bangalore, Karnataka"], "team": "ML"},
     "workplaceType": "onsite", "description": "<p>Ranking models.</p>",
     "lists": [{"text": "What you'll do", "content": "<li>Ship models</li>"}], "additional": "<p>Benefits</p>"},
    {"id": "l2", "text": "No URL"},
]
WORKABLE_LIST = {"jobs": [{"shortcode": "W1", "title": "Open-Source ML Engineer", "url": "https://apply.workable.com/j/W1",
                           "telecommuting": True, "locations": [{"city": "Paris", "country": "France"}]}]}
WORKABLE_DETAIL = {"description": "<p>Work on transformers.</p>", "requirements": "<p>Python</p>"}


def client(routes):
    def handler(req):
        for frag, body in routes.items():
            if frag in str(req.url):
                return httpx.Response(200, json=body)
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def collect(cls, routes, boards):
    c = cls(boards=boards, client=client(routes), delay_s=0, sleep=lambda s: None)
    return c, list(c.collect())


def test_ashby_maps_fields_skips_unlisted_and_marks_remote():
    c, recs = collect(AshbyCollector, {"job-board/sarvam": ASHBY}, ["sarvam"])
    assert [r.external_id for r in recs] == ["sarvam:a1", "sarvam:a3"]
    p = recs[0].payload
    assert p["offices"] == ["Delhi"] and p["departments"] == ["Research", "Speech"]
    assert "Compensation: ₹30L – ₹45L" in p["content_html"]
    assert recs[1].payload["location"].endswith("Remote")


def test_lever_builds_content_from_sections_and_skips_bad_rows():
    _, recs = collect(LeverCollector, {"postings/meesho": LEVER}, ["meesho"])
    assert len(recs) == 1
    p = recs[0].payload
    assert p["title"] == "Machine Learning Engineer" and p["location"] == "Bangalore, Karnataka"
    assert "Ship models" in p["content_html"] and "Benefits" in p["content_html"]


def test_workable_fetches_detail_and_marks_remote():
    _, recs = collect(WorkableCollector, {"widget/accounts/huggingface": WORKABLE_LIST,
                                          "accounts/huggingface/jobs/W1": WORKABLE_DETAIL}, ["huggingface"])
    p = recs[0].payload
    assert "transformers" in p["content_html"] and "Python" in p["content_html"]
    assert p["location"] == "Paris, France | Remote"


def test_failing_board_recorded_others_continue():
    c, recs = collect(LeverCollector, {"postings/meesho": LEVER}, ["gone", "meesho"])
    assert len(recs) == 1 and c.report.units_failed == 1


def test_common_payload_normalises_through_one_path():
    _, recs = collect(AshbyCollector, {"job-board/sarvam": ASHBY}, ["sarvam"])
    o = n.from_ats({"url": recs[0].url, "content_hash": recs[0].content_hash, "payload": recs[0].payload})
    assert o.org == "Sarvam AI" and "IN" in o.countries and o.eligibility.result in ("pass", "unclear")
