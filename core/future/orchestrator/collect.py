"""Collect stage: run every enabled collector, store raw items (deduped by
content hash), record per-source health. No model calls."""
from __future__ import annotations

from dataclasses import dataclass

from future.collectors.base import Collector
from future.orchestrator.runlog import RunContext
from future.store import Store


@dataclass(frozen=True)
class SourceSpec:
    kind: str
    track: str
    method: str
    url: str | None
    terms_verdict: str


def health_for(success_rate: float) -> str:
    # Thresholds from ROADMAP §4.1 (collector run success).
    if success_rate >= 0.95:
        return "ok"
    if success_rate >= 0.85:
        return "degraded"
    return "failing"


def run_collector(store: Store, ctx: RunContext, collector: Collector, spec: SourceSpec) -> dict:
    source_id = store.ensure_source(collector.name, kind=spec.kind, track=spec.track, method=spec.method,
                                    url=spec.url, terms_verdict=spec.terms_verdict)
    records = list(collector.collect())
    new = store.add_raw_items(source_id, records) if records else 0
    rep = collector.report
    stats = {"units_ok": rep.units_ok, "units_failed": rep.units_failed, "records": rep.records, "new": new,
             "success_rate": round(rep.success_rate, 3)}
    store.update_source_health(source_id, health_for(rep.success_rate), stats)
    ctx.items_in += rep.records
    ctx.items_out += new
    ctx.event("source_collected", f"{collector.name}: {rep.records} records, {new} new", **stats,
              errors=rep.errors[:10])
    return stats
