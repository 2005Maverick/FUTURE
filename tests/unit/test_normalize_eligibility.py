"""S02.02: normaliser, dedup, and the E-02 eligibility subset (15 crafted cases)."""
import json
from pathlib import Path

import pytest

from future.pipeline import normalize as n
from future.pipeline.eligibility import check_job, max_years_required
from future.pipeline.location import parse_location

CASES = json.loads((Path(__file__).resolve().parents[2] / "evals" / "datasets" / "eligibility_e02.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_e02_eligibility(case):
    e = check_job(case["title"], parse_location(case["location"]), case["text"])
    assert e.result == case["expect"], e.reasons


def test_no_ineligible_case_passes():
    """The E-02 hard rule: zero ineligible items may pass."""
    passed_but_should_fail = [c["id"] for c in CASES if c["expect"] == "fail"
                              and check_job(c["title"], parse_location(c["location"]), c["text"]).result != "fail"]
    assert passed_but_should_fail == []


def test_years_parsing():
    assert max_years_required("5+ years of industry experience") == 5
    assert max_years_required("3-5 yrs' experience") == 3
    assert max_years_required("founded 10 years ago") is None
    # live Cloudflare formats the first version missed (cost ~15k tokens each at the model)
    assert max_years_required("Exp: 3-15yrs") == 3
    assert max_years_required("Exp : 3- 12 yrs") == 3
    assert max_years_required("Exp: 5 - 10yrs") == 5
    # en/em dashes seen live on Sarvam (Ashby) postings
    assert max_years_required("4–8 years of experience in data infrastructure") == 4
    assert max_years_required("3—5 years experience") == 3


def test_remote_scope():
    assert parse_location("Remote-Friendly, United States").remote_scope == "restricted"
    assert parse_location("Remote - India").remote_scope == "india_ok"
    assert parse_location("Remote").remote_scope == "unspecified"
    assert parse_location("Bengaluru, India").remote_scope == "none"


def test_more_countries_recognised():
    assert parse_location("Zürich, CH").countries == {"CH"}
    assert parse_location("Seoul, South Korea").countries == {"KR"}


def test_html_to_text_and_canonical_url():
    assert n.html_to_text("<p>Hi&amp;bye</p><ul><li>a</li><li>b</li></ul>") == "Hi&bye\na\nb"
    assert n.canonical_url("HTTPS://Job-Boards.Greenhouse.io/x/jobs/1/?gh_src=abc#top") == \
        "https://job-boards.greenhouse.io/x/jobs/1"


def raw(job_id, title, location, content="<p>Build ML.</p>"):
    return {"url": f"https://x/{job_id}", "content_hash": f"h{job_id}",
            "payload": {"board": "anthropic", "title": title, "location": location, "offices": [],
                        "content_html": content, "departments": []}}


def test_same_role_same_country_merges_and_keeps_both_raw_links():
    opps = n.dedupe([n.from_greenhouse(raw(1, "Applied AI Architect", "Bangalore, India")),
                     n.from_greenhouse(raw(2, "Applied AI Architect", "Mumbai, India"))])
    assert len(opps) == 1 and opps[0].raw_hashes == ["h1", "h2"]
    assert "Mumbai" in opps[0].location


def test_same_role_different_country_stays_separate():
    opps = n.dedupe([n.from_greenhouse(raw(1, "Research Engineer", "Bangalore, India")),
                     n.from_greenhouse(raw(2, "Research Engineer", "London, UK"))])
    assert len(opps) == 2


def test_type_detection_and_status():
    assert n.job_type("AI Research Intern") == "internship"
    assert n.job_type("Anthropic Fellows Program, ML Systems") == "fellowship"
    o = n.from_greenhouse(raw(9, "Senior Staff Engineer", "Bangalore, India"))
    assert o.status == "skipped" and o.org == "Anthropic"
