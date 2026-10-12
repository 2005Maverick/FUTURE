"""S02.05b: the daily run end-to-end with a fake collector and fake model, on the
persistent local store. No network, no tokens."""
import datetime as dt
import json

from future.collectors.base import CollectorReport, RawRecord, content_hash
from future.llm.claude_runner import ClaudeResult
from future.orchestrator import daily
from future.orchestrator.budget import CAP_KEY, RESERVE_KEY
from future.orchestrator.collect import SourceSpec
from future.store_local import LocalFileStore

TODAY = dt.date(2026, 10, 12)
SPEC = SourceSpec("ats", "job", "greenhouse", None, "allowed")


def job(jid, title, location, content="<p>Build ML systems with PyTorch.</p>"):
    payload = {"board": "acme", "title": title, "location": location, "offices": [], "content_html": content,
               "departments": [], "updated_at": None, "first_published": None}
    return RawRecord("greenhouse", f"acme:{jid}", f"https://x/{jid}", payload,
                     content_hash("greenhouse", f"acme:{jid}", payload))


class FakeCollector:
    name = "greenhouse"

    def __init__(self, records, board_ok=True):
        self.records = records
        self.board_ok = board_ok
        self.report = CollectorReport(source="greenhouse")

    def collect(self):
        self.report = CollectorReport(source="greenhouse", units_ok=1, records=len(self.records),
                                      ok_units=["acme"] if self.board_ok else [])
        yield from self.records


def fake_runner(calls):
    def run(prompt, **kw):
        calls.append(prompt)
        loc = prompt.split("Location: ")[1].split("\n")[0]
        data = {"fit": 4, "value": 4, "eligibility": "pass", "eligibility_reason": "ok", "legitimacy": "ok",
                "legitimacy_signal": "none", "gaps": [], "recommendation": "apply",
                "one_line": f"good fit in {loc}",
                "evidence": [{"quote": "Build ML systems with PyTorch.", "supports": "fit"}]}
        return ClaudeResult(text=json.dumps(data), data=None, model="claude-sonnet-5-5",
                            usage={"input_tokens": 5000}, cost_usd=0, duration_s=0.1, session_id=None)
    return run


DATA = [job(1, "Machine Learning Engineer", "Bengaluru, India"),
        job(2, "Software Engineer, Intern", "Bengaluru, India"),
        job(3, "Software Engineer, Intern", "Toronto, Canada"),          # same title, other country
        job(4, "Senior Staff Engineer", "Bengaluru, India")]             # ineligible: never evaluated


def run(store, records, calls, **kw):
    return daily.run_daily(store, [(FakeCollector(records), SPEC)], today=TODAY, runner=fake_runner(calls),
                           write_file=False, **kw)


def test_first_run_evaluates_eligible_and_builds_digest(tmp_path):
    store, calls = LocalFileStore(tmp_path / "s.json"), []
    r = run(store, DATA, calls)
    assert r.opportunities == 4 and r.skipped == 1
    assert r.evaluated_now == 3 and r.evaluated_cached == 0
    assert len(calls) == 3 and r.shortlisted == 3
    md = store.digests[TODAY.isoformat()]
    assert "Machine Learning Engineer" in md and "Senior Staff" not in md


def test_same_title_different_city_keeps_correct_location(tmp_path):
    """Regression for the S02.04 Stripe bug: evals must be keyed by dedup_key, not org+title."""
    store, calls = LocalFileStore(tmp_path / "s.json"), []
    run(store, DATA, calls)
    md = store.digests[TODAY.isoformat()]
    for line in [l for l in md.splitlines() if "Software Engineer, Intern" in l]:
        city = "Toronto" if "Toronto" in line else "Bengaluru"
        follow = md.split(line, 1)[1].splitlines()[1]
        assert f"good fit in {city}" in follow, (line, follow)


def test_second_run_uses_cache_and_persists_across_restart(tmp_path):
    path, calls = tmp_path / "s.json", []
    store = LocalFileStore(path)
    run(store, DATA, calls)
    store.save()
    reloaded = LocalFileStore(path)                       # simulates the next day's process
    r = run(reloaded, DATA, calls)
    assert r.evaluated_now == 0 and r.evaluated_cached == 3 and len(calls) == 3


def test_save_keeps_previous_snapshot_as_backup(tmp_path):
    path, calls = tmp_path / "s.json", []
    store = LocalFileStore(path)
    run(store, DATA, calls)
    store.save()
    store.save()
    backup = LocalFileStore(tmp_path / "s.bak.json")
    assert len(backup.evals) == 3            # cached evaluations survive in the backup


def test_changed_posting_is_reevaluated_only_once(tmp_path):
    store, calls = LocalFileStore(tmp_path / "s.json"), []
    run(store, DATA, calls)
    changed = [job(1, "Machine Learning Engineer", "Bengaluru, India", "<p>Build ML systems with PyTorch. New: LLM evals.</p>")] + DATA[1:]
    r = run(store, changed, calls)
    assert r.evaluated_now == 1 and r.evaluated_cached == 2


def test_budget_exhaustion_leaves_rest_pending_and_still_digests(tmp_path):
    store, calls = LocalFileStore(tmp_path / "s.json"), []
    store.set_setting(CAP_KEY, 5500)   # first eval (estimate < 5.5k) fits; after it records 5k, nothing else does
    store.set_setting(RESERVE_KEY, 0)
    r = run(store, DATA, calls)
    assert r.evaluated_now == 1 and r.pending == 2
    assert "waiting for budget" in store.digests[TODAY.isoformat()]


def test_max_evals_cap(tmp_path):
    store, calls = LocalFileStore(tmp_path / "s.json"), []
    r = run(store, DATA, calls, max_evals=2)
    assert r.evaluated_now == 2 and r.pending == 1


def test_closed_posting_expires_only_when_board_fetched_ok(tmp_path):
    store, calls = LocalFileStore(tmp_path / "s.json"), []
    run(store, DATA, calls)
    ml_key = next(k for k, o in store.opps.items() if o["title"] == "Machine Learning Engineer")
    # board fetch FAILED today and the job is absent → must stay open
    daily.run_daily(store, [(FakeCollector(DATA[1:], board_ok=False), SPEC)], today=TODAY,
                    runner=fake_runner(calls), write_file=False)
    assert store.opps[ml_key]["status"] != "expired"
    # board fetched OK and the job is absent → closed
    daily.run_daily(store, [(FakeCollector(DATA[1:]), SPEC)], today=TODAY, runner=fake_runner(calls), write_file=False)
    assert store.opps[ml_key]["status"] == "expired"
    assert "no longer listed" in store.opps[ml_key]["skip_reason"]


def test_advanced_status_is_not_reset_or_reevaluated(tmp_path):
    store, calls = LocalFileStore(tmp_path / "s.json"), []
    run(store, DATA, calls)
    key = next(k for k, o in store.opps.items() if o["title"] == "Machine Learning Engineer")
    store.update_opportunity(key, {"status": "submitted"})
    changed = [job(1, "Machine Learning Engineer", "Bengaluru, India", "<p>Build ML systems with PyTorch. v2</p>")] + DATA[1:]
    r = run(store, changed, calls)
    assert store.opps[key]["status"] == "submitted" and r.evaluated_now == 0
