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


def make_store() -> tuple[Store, str]:
    cfg = config.load()
    if cfg.has_db_write_access:
        return SupabaseStore(cfg.supabase_url, cfg.supabase_secret_key), "supabase"
    return MemoryStore(), "memory"  # until H11: results also go to the local JSONL log


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
    raw = getattr(store, "raw", None)
    if not raw:
        return None
    out = config.REPO_ROOT / "private" / "data" / "raw" / f"{dt.date.today().isoformat()}-{stage}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for row in raw.values():
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out


STAGES = {"healthcheck": stage_healthcheck, "collect": stage_collect}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="future-run")
    parser.add_argument("--stage", required=True, choices=sorted(STAGES))
    args = parser.parse_args(argv)
    store, backend = make_store()
    try:
        with InstanceLock(LOCK_DIR / f"{args.stage}.lock"):
            result = STAGES[args.stage](store)
    except LockHeld as exc:
        print(f"skip: {exc}")
        return 0
    if backend == "memory":
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
