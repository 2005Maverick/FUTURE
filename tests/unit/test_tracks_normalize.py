"""Non-job tracks → Opportunity: hackathons, watched-page extractions, lab outreach."""
import datetime as dt

from future.pipeline import tracks

TODAY = dt.date(2026, 10, 13)


def hack(mode, location, **kw):
    payload = {"board": "mlh", "org": "HackX", "title": "HackX 2026", "location": location, "offices": [],
               "content_html": "<p>MLH 2027 season hackathon.</p>", "departments": [], "track": "hackathon",
               "opp_type": "hackathon", "deadline": "2026-11-01", "prize": None, "mode": mode, **kw}
    return {"url": "https://hackx.example", "content_hash": "h1", "payload": payload, "source": "mlh"}


def test_online_hackathon_passes_with_deadline():
    o = tracks.from_hackathon(hack("online", "Online"))
    assert (o.track, o.type, o.eligibility.result, o.deadline) == ("hackathon", "hackathon", "pass", "2026-11-01")
    assert o.details["source"] == "mlh" and o.details["mode"] == "online"


def test_in_person_outside_india_fails_but_india_passes():
    assert tracks.from_hackathon(hack("in-person", "Gainesville, Florida, US")).eligibility.result == "fail"
    assert tracks.from_hackathon(hack("in-person", "New Delhi, Delhi, IN")).eligibility.result == "pass"


def test_hybrid_abroad_is_unclear():
    assert tracks.from_hackathon(hack("hybrid", "Toronto, CA")).eligibility.result == "unclear"


def test_kaggle_competition_type_and_prize_kept():
    raw = hack("online", "Online", prize="77,000 USD")
    raw["payload"] = {**raw["payload"], "opp_type": "competition", "board": "kaggle"}
    raw["source"] = "kaggle"
    o = tracks.from_hackathon(raw)
    assert o.type == "competition" and o.details["prize"] == "77,000 USD"


def test_dedup_key_stable_across_runs_and_distinct_per_event():
    a, b = tracks.from_hackathon(hack("online", "Online")), tracks.from_hackathon(hack("online", "Online"))
    c = tracks.from_hackathon({**hack("online", "Online"), "payload": {**hack("online", "Online")["payload"],
                                                                       "title": "Other Hack"}})
    assert a.dedup_key == b.dedup_key != c.dedup_key


PAGE = {"id": "eth-ssrf", "url": "https://inf.ethz.ch/ssrf.html", "track": "research", "org": "ETH Zurich",
        "kind": "fellowship"}


def item(**kw):
    base = {"type": "research_internship", "title": "Student Summer Research Fellowship", "org": "ETH Zurich",
            "url": None, "location": "Zurich, Switzerland", "remote": False, "deadline": "2027-01-15",
            "pay": "CHF 1,700 per month", "eligibility_notes": ["Bachelor students"], "scam_signals": []}
    base.update(kw)
    return base


def test_extracted_item_uses_page_url_when_none_and_page_track():
    o = tracks.from_extracted(item(), PAGE, content_hash="c1")
    assert (o.track, o.type, o.url, o.deadline) == ("research", "research_internship", PAGE["url"], "2027-01-15")
    assert o.eligibility.result == "unclear" and o.details["source"] == "pagewatch"
    assert "CHF 1,700" in o.description


def test_extracted_item_with_expired_deadline_fails():
    o = tracks.from_extracted(item(deadline="2026-01-01"), PAGE, content_hash="c1", today=TODAY)
    assert o.eligibility.result == "fail"


def test_extracted_item_with_scam_signals_is_unclear_with_reason():
    o = tracks.from_extracted(item(scam_signals=["asks for a fee"]), PAGE, content_hash="c1")
    assert any("scam" in r for r in o.eligibility.reasons)


def test_extracted_type_outside_track_falls_back_to_page_kind():
    o = tracks.from_extracted(item(type="job"), {**PAGE, "track": "funding", "kind": "accelerator"}, content_hash="c")
    assert o.type == "accelerator"


LAB = {"board": "openalex", "org": "UC Berkeley", "title": "Research outreach: Sergey Levine — embodied AI",
       "location": "United States", "offices": [], "content_html": "Matching recent works: 6", "departments": [],
       "track": "research", "opp_type": "lab_outreach", "works": 6, "author_name": "Sergey Levine",
       "author_id": "A1", "orcid": None, "h_index": 120, "author_works_count": 900, "top_papers": []}


def test_lab_outreach_keeps_senior_researchers():
    o = tracks.from_lab({"url": "https://openalex.org/A1", "content_hash": "l1", "payload": LAB,
                         "source": "openalex"})
    assert (o.type, o.track, o.eligibility.result) == ("lab_outreach", "research", "pass")
    assert o.details["h_index"] == 120


def test_lab_outreach_drops_likely_students():
    o = tracks.from_lab({"url": "u", "content_hash": "l2", "payload": {**LAB, "h_index": 4}, "source": "openalex"})
    assert o.eligibility.result == "fail" and "h-index" in o.eligibility.reasons[0]
