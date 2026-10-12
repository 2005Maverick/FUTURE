"""Tracks stage end to end with fake collectors and a fake Extractor (no network, no model)."""
import datetime as dt
import json

from future.collectors.base import CollectorReport, RawRecord
from future.llm.claude_runner import ClaudeResult
from future.orchestrator import tracks
from future.orchestrator.collect import SourceSpec
from future.store import MemoryStore

TODAY = dt.date(2026, 10, 13)
SPEC = SourceSpec(kind="api", track="hackathon", method="fake", url="https://x", terms_verdict="allowed")
PAGE_TEXT = "ETH Student Summer Research Fellowship. Apply by 15 January 2027 at https://inf.ethz.ch/ssrf"


class Fake:
    def __init__(self, name, records):
        self.name, self._records = name, records
        self.report = CollectorReport(source=name)

    def collect(self):
        self.report.units_ok += 1
        self.report.records = len(self._records)
        yield from self._records


def hack(title, mode, location):
    p = {"board": "mlh", "org": title, "title": title, "location": location, "offices": [], "content_html": "",
         "departments": [], "track": "hackathon", "opp_type": "hackathon", "deadline": "2026-11-01",
         "prize": None, "mode": mode}
    return RawRecord("mlh", title, f"https://{title.lower()}.example", p, f"h-{title}")


def page(h="p1"):
    p = {"board": "eth-ssrf", "org": "ETH Zurich", "title": "SSRF", "location": "", "offices": [],
         "content_html": PAGE_TEXT, "departments": ["research"], "page_kind": "fellowship", "track": "research"}
    return RawRecord("pagewatch", "eth-ssrf", "https://inf.ethz.ch/ssrf", p, h)


def extractor_runner(calls):
    def run(prompt, **kw):
        calls.append(prompt)
        out = {"opportunities": [{
            "type": "fellowship", "title": "Student Summer Research Fellowship",
            "title_quote": "Student Summer Research Fellowship", "org": "ETH", "org_quote": "ETH Student",
            "url": "https://inf.ethz.ch/ssrf", "location": None, "location_quote": None, "remote": None,
            "deadline": "2027-01-15", "deadline_quote": "Apply by 15 January 2027", "pay": None, "pay_quote": None,
            "eligibility_notes": [], "scam_signals": []}]}
        return ClaudeResult(text=json.dumps(out), data=None, model="claude-haiku-5-5",
                            usage={"input_tokens": 1000}, cost_usd=0, duration_s=0.1, session_id=None)
    return run


def plan(*records_by_source):
    return [(Fake(name, recs), SPEC) for name, recs in records_by_source]


def test_hackathons_normalised_and_pages_extracted(tmp_path):
    store, calls = MemoryStore(), []
    res = tracks.run_tracks(store, plan(("mlh", [hack("OnlineHack", "online", "Online"),
                                                  hack("FarHack", "in-person", "Austin, Texas, US")]),
                                        ("pagewatch", [page()])),
                            today=TODAY, runner=extractor_runner(calls), data_dir=tmp_path, write_file=False)
    assert (res.opportunities, res.eligible, res.pages_extracted, res.extracted_opportunities) == (2, 1, 1, 1)
    tracks_seen = {o["track"] for o in store.opps.values()}
    assert tracks_seen == {"hackathon", "research"}
    research = next(o for o in store.opps.values() if o["track"] == "research")
    assert research["deadline"] == "2027-01-15" and research["type"] == "fellowship"
    assert len(calls) == 1


def test_extraction_is_idempotent_and_resumes_after_cap(tmp_path):
    store, calls = MemoryStore(), []
    p = plan(("pagewatch", [page("p1"), page("p2"), page("p3")]))
    r1 = tracks.run_tracks(store, p, today=TODAY, runner=extractor_runner(calls), data_dir=tmp_path,
                           max_pages=2, write_file=False)
    assert (r1.pages_extracted, r1.pages_waiting) == (2, 1)
    # next run: the watcher emits nothing new, the queued page is still processed
    r2 = tracks.run_tracks(store, plan(("pagewatch", [])), today=TODAY, runner=extractor_runner(calls),
                           data_dir=tmp_path, max_pages=2, write_file=False)
    assert (r2.pages_extracted, r2.pages_waiting) == (1, 0)
    r3 = tracks.run_tracks(store, plan(("pagewatch", [])), today=TODAY, runner=extractor_runner(calls),
                           data_dir=tmp_path, write_file=False)
    assert r3.pages_extracted == 0 and len(calls) == 3


def test_failed_extraction_stays_queued(tmp_path):
    store = MemoryStore()

    def broken(prompt, **kw):
        raise RuntimeError("model down")
    r1 = tracks.run_tracks(store, plan(("pagewatch", [page()])), today=TODAY, runner=broken, data_dir=tmp_path,
                           write_file=False)
    assert (r1.pages_extracted, r1.pages_waiting) == (0, 1)
    r2 = tracks.run_tracks(store, plan(("pagewatch", [])), today=TODAY, runner=extractor_runner([]),
                           data_dir=tmp_path, write_file=False)
    assert r2.pages_extracted == 1


def test_one_source_failing_does_not_stop_the_others(tmp_path):
    class Boom(Fake):
        def collect(self):
            raise RuntimeError("layout changed")
            yield
    store = MemoryStore()
    p = [(Boom("kaggle", []), SPEC), (Fake("mlh", [hack("OnlineHack", "online", "Online")]), SPEC)]
    res = tracks.run_tracks(store, p, today=TODAY, runner=extractor_runner([]), data_dir=tmp_path, write_file=False)
    assert res.opportunities == 1
    assert any(e.get("type") == "source_failed" or "source_failed" in json.dumps(e) for e in store.events)


def test_digest_lists_open_hackathons_and_skips_failed(tmp_path):
    hk = [tracks.tn.from_hackathon({"url": r.url, "content_hash": r.content_hash, "payload": r.payload,
                                    "source": "mlh"}) for r in (hack("OnlineHack", "online", "Online"),
                                                                hack("FarHack", "in-person", "Austin, US"))]
    md = tracks.build_tracks_digest(TODAY, hk, [], waiting=2)
    assert "OnlineHack" in md and "FarHack" not in md and "1 open to you" in md and "2 changed page" in md


def test_labs_stage_keeps_senior_and_writes_no_digest_when_asked(tmp_path):
    def lab(name, h):
        p = {"board": "openalex", "org": "MIT", "title": f"Research outreach: {name}", "location": "United States",
             "offices": [], "content_html": "", "departments": ["embodied AI"], "track": "research",
             "opp_type": "lab_outreach", "works": 3, "author_name": name, "author_id": name, "h_index": h}
        return RawRecord("openalex", name, f"https://orcid.org/{name}", p, f"l-{name}")
    store = MemoryStore()
    out = tracks.run_labs(store, today=TODAY, collector=Fake("openalex", [lab("Prof", 40), lab("Student", 3)]),
                          write_file=False)
    assert out["records"] == 2 and out["kept"] == 1
