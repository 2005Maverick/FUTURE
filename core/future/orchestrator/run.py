"""Orchestrator entry point: `python -m future.orchestrator.run --stage <name>`.

Every invocation takes the single-instance lock, records a `runs` row with an
event stream, and exits non-zero only on unexpected errors. Stages are added as
the build progresses; unknown stages fail loudly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from future import config
from future.orchestrator.budget import BudgetGuard
from future.orchestrator.runlog import run_stage
from future.orchestrator.stages import InstanceLock, LockHeld
from future.orchestrator import trijya
from future.store import MemoryStore, Store, SupabaseStore

LOCK_DIR = config.REPO_ROOT / "private" / "locks"
LOCAL_LOG = config.REPO_ROOT / "private" / "logs" / "runs.jsonl"


LOCAL_STATE = config.REPO_ROOT / "private" / "data" / "state.json"


def make_store() -> tuple[Store, str]:
    cfg = config.load()
    if cfg.has_db_write_access:
        return SupabaseStore(cfg.supabase_url, cfg.supabase_secret_key), "supabase"
    from future.store_local import LocalFileStore
    return LocalFileStore(LOCAL_STATE), "local"   # until H11: persistent JSON snapshot in private/


def jobs_plan():
    """All job-board collectors (public APIs, no auth; terms allow automated reads of public boards)."""
    from future.collectors.ats import AshbyCollector, LeverCollector, WorkableCollector
    from future.collectors.greenhouse import GreenhouseCollector
    from future.collectors.remote_boards import HimalayasCollector, RemotiveCollector
    from future.orchestrator.collect import SourceSpec

    def spec(method, url):
        return SourceSpec(kind="ats", track="job", method=method, url=url, terms_verdict="allowed")
    return [
        (GreenhouseCollector(), spec("greenhouse_job_board_api", "https://boards-api.greenhouse.io")),
        (AshbyCollector(), spec("ashby_posting_api", "https://api.ashbyhq.com/posting-api")),
        (LeverCollector(), spec("lever_postings_api", "https://api.lever.co/v0/postings")),
        (WorkableCollector(), spec("workable_widget_api", "https://apply.workable.com/api")),
        (HimalayasCollector(), SourceSpec(kind="api", track="job", method="himalayas_search_api",
                                          url="https://himalayas.app/jobs/api", terms_verdict="allowed")),
        (RemotiveCollector(), SourceSpec(kind="api", track="job", method="remotive_api_2_calls_per_run",
                                         url="https://remotive.com/api/remote-jobs", terms_verdict="allowed")),
    ]


def stage_daily(store: Store, max_evals: int = 40) -> dict:
    from dataclasses import asdict
    from future.orchestrator.daily import run_daily
    return asdict(run_daily(store, jobs_plan(), today=dt.date.today(), max_evals=max_evals))


def stage_healthcheck(store: Store) -> dict:
    """Cheap, model-free check of every dependency the pipeline needs."""
    with run_stage(store, "healthcheck") as ctx:
        st = trijya.probe()
        budget = BudgetGuard(store).status()
        cfg = config.load()
        report = {
            "trijya_awake": st.awake, "trijya_services": st.services,
            "budget_used": budget.used, "budget_cap": budget.cap,
            "db_write_access": cfg.has_db_write_access,
            "keys": {"openalex": bool(cfg.openalex_api_key), "exa": bool(cfg.exa_api_key),
                     "kaggle": bool(cfg.kaggle_api_token)},
        }
        ctx.event("health", "healthcheck complete", **report)
        ctx.items_out = 1
    return report


def stage_collect(store: Store) -> dict:
    from future.collectors.greenhouse import GreenhouseCollector
    from future.orchestrator.collect import SourceSpec, run_collector

    plan = [(GreenhouseCollector(), SourceSpec(kind="ats", track="job", method="greenhouse_job_board_api",
                                               url="https://boards-api.greenhouse.io", terms_verdict="allowed"))]
    results = {}
    with run_stage(store, "collect") as ctx:
        for collector, spec in plan:
            try:
                results[collector.name] = run_collector(store, ctx, collector, spec)
            except Exception as exc:  # one source failing must not stop the others
                results[collector.name] = {"error": f"{type(exc).__name__}: {exc}"}
                ctx.event("source_failed", collector.name, level="error", error=str(exc)[:300])
    return results


def dump_local_raw(store: Store, stage: str) -> Path | None:
    """Until H11 (DB writes), persist MemoryStore raw items to private/data/raw/."""
    raw = {k: v for k, v in (getattr(store, "raw", None) or {}).items() if "payload" in v}
    if not raw:
        return None
    out = config.REPO_ROOT / "private" / "data" / "raw" / f"{dt.date.today().isoformat()}-{stage}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for row in raw.values():
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out


def stage_registry(store: Store) -> dict:
    """Weekly: discover ATS boards from Common Crawl, validate, keep India/remote-relevant ones. No model calls."""
    import httpx
    from future.collectors import registry as reg

    client = reg.polite_client(timeout_s=60)
    log = reg.ProgressLog(config.REPO_ROOT / "private" / "logs" / f"registry-{dt.date.today().isoformat()}.log")
    crawls = [c["id"] for c in httpx.get("https://index.commoncrawl.org/collinfo.json", timeout=60).json()[:2]]
    log(f"start: crawls={crawls}")
    with run_stage(store, "registry") as ctx:
        pairs = []
        for ats in reg.URL_PATTERNS:
            log(f"harvesting {ats}…")
            slugs = reg.harvest_slugs(ats, crawls, client)
            log(f"harvested {ats}: {len(slugs)} slugs")
            ctx.event("harvested", f"{ats}: {len(slugs)} slugs", ats=ats, count=len(slugs))
            pairs += [(ats, s) for s in sorted(slugs)]
        stats = reg.validate_all(pairs, client, progress=log)
        log("done")
        reg.save_registry(stats)
        chosen = reg.selected(stats)
        ctx.items_in, ctx.items_out = len(pairs), sum(len(v) for v in chosen.values())
    return {"crawls": crawls, "harvested": len(pairs),
            "live_boards": sum(1 for s in stats if s.error is None and s.jobs > 0),
            "selected": {k: len(v) for k, v in chosen.items()}}


STAGES = {"healthcheck": stage_healthcheck, "collect": stage_collect, "daily": stage_daily,
          "registry": stage_registry}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="future-run")
    parser.add_argument("--stage", required=True, choices=sorted(STAGES))
    parser.add_argument("--max-evals", type=int, default=None, help="daily: cap model evaluations this run")
    args = parser.parse_args(argv)
    store, backend = make_store()
    kwargs = {"max_evals": args.max_evals} if args.stage == "daily" and args.max_evals is not None else {}
    # With the local JSON store, two stages loading then saving the same file would
    # silently overwrite each other (last writer wins), so local mode is one-stage-at-a-time.
    lock_name = "local-state" if backend == "local" else args.stage
    try:
        with InstanceLock(LOCK_DIR / f"{lock_name}.lock"):
            try:
                result = STAGES[args.stage](store, **kwargs)
            finally:
                if hasattr(store, "save"):
                    store.save()          # persist even if a stage failed midway
    except LockHeld as exc:
        print(f"skip: {exc}")
        return 0
    if backend in ("memory", "local"):
        dumped = dump_local_raw(store, args.stage)
        if dumped:
            result = {**result, "local_raw_file": str(dumped)}
    LOCAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": dt.datetime.now().isoformat(timespec="seconds"), "stage": args.stage,
                             "backend": backend, "result": result}) + "\n")
    print(json.dumps({"stage": args.stage, "backend": backend, "result": result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
