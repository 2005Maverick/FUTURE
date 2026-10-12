"""The daily run (DESIGN §6): collect → normalize/dedupe → evaluate (cached, budgeted,
priority-ordered) → rank → digest. Everything is keyed by dedup_key — never by
org+title (S02.04 finding: one title can be posted in several cities).
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
from dataclasses import dataclass
from typing import Callable

from future import config
from future.agents import evaluator as ev
from future.collectors.base import Collector, RawRecord
from future.digest.build import DigestItem, DigestStats, build
from future.llm import claude_runner
from future.orchestrator.budget import BudgetExhausted, BudgetGuard
from future.orchestrator.collect import SourceSpec, health_for
from future.orchestrator.runlog import run_stage
from future.pipeline import normalize as norm
from future.pipeline.ranking import RankInput, rank
from future.store import Store

NORMALIZERS = {"greenhouse": norm.from_greenhouse}
EVALUABLE_STATUSES = {"verified", "scored", "shortlisted"}
DIGEST_DIR = config.REPO_ROOT / "private" / "digests"


@dataclass
class DailyResult:
    collected: int
    new_raw: int
    opportunities: int
    eligible_pass: int
    eligible_unclear: int
    skipped: int
    evaluated_now: int
    evaluated_cached: int
    pending: int
    shortlisted: int
    digest_path: str | None


def input_hash(o: norm.Opportunity) -> str:
    return hashlib.sha1(f"{o.title}|{o.location}|{o.description}".encode("utf-8")).hexdigest()


def opportunity_row(o: norm.Opportunity) -> dict:
    fails = [r for r in o.eligibility.reasons if r.startswith("fail")]
    return {"type": o.type, "track": o.track, "title": o.title, "org": o.org, "url": o.url,
            "canonical_url": o.canonical_url, "dedup_key": o.dedup_key, "location": o.location,
            "remote": o.remote, "countries": o.countries, "deadline": None,
            "eligibility": {"result": o.eligibility.result, "reasons": o.eligibility.reasons},
            # descriptions only for live candidates: skipped roles never reach a model, and storing
            # ~5k of them made the local state 41 MB (S02.05b)
            "details": {**o.details, **({"description": o.description} if o.status != "skipped" else {})},
            "status": o.status,
            "skip_reason": fails[0][6:] if fails else None}


def candidate_order(o: norm.Opportunity) -> tuple:
    """Cheap pre-ranking before any model spend: eligible-pass first, India-located first."""
    return (o.eligibility.result != "pass", "IN" not in o.countries, o.title)


def run_daily(store: Store, plan: list[tuple[Collector, SourceSpec]], *, today: dt.date,
              runner: Callable = claude_runner.run, max_evals: int = 40,
              write_file: bool = True) -> DailyResult:
    guard = BudgetGuard(store)
    records: list[RawRecord] = []
    new_raw = 0

    with run_stage(store, "collect") as ctx:
        for collector, spec in plan:
            try:
                sid = store.ensure_source(collector.name, kind=spec.kind, track=spec.track, method=spec.method,
                                          url=spec.url, terms_verdict=spec.terms_verdict)
                recs = list(collector.collect())
                added = store.add_raw_items(sid, recs) if recs else 0
                rep = collector.report
                store.update_source_health(sid, health_for(rep.success_rate),
                                           {"records": rep.records, "new": added, "success_rate": rep.success_rate})
                records += recs
                new_raw += added
                ctx.event("source_collected", f"{collector.name}: {rep.records} records, {added} new")
            except Exception as exc:  # one source failing must not stop the run
                ctx.event("source_failed", collector.name, level="error", error=str(exc)[:300])
        ctx.items_in, ctx.items_out = len(records), new_raw

    with run_stage(store, "normalize") as ctx:
        opps = norm.dedupe([NORMALIZERS[r.source]({"url": r.url, "content_hash": r.content_hash, "payload": r.payload})
                            for r in records if r.source in NORMALIZERS])
        ids = store.upsert_opportunities([opportunity_row(o) for o in opps])
        ctx.items_in, ctx.items_out = len(records), len(opps)
    counts = collections.Counter(o.eligibility.result for o in opps)

    evaluations: dict[str, dict] = {}
    by_key = {o.dedup_key: o for o in opps}
    evaluated_now = cached = pending = 0
    candidates = sorted((o for o in opps if o.eligibility.result != "fail"
                         and ids.get(o.dedup_key, {}).get("status") in EVALUABLE_STATUSES), key=candidate_order)
    with run_stage(store, "evaluate", agent="evaluator") as ctx:
        budget_hit = False
        for o in candidates:
            opp_id, ih = ids[o.dedup_key]["id"], input_hash(o)
            hit = store.get_evaluation(opp_id, ev.RUBRIC_VERSION, ih)
            if hit:
                evaluations[o.dedup_key] = hit
                cached += 1
                continue
            if budget_hit or evaluated_now >= max_evals:
                pending += 1
                continue
            try:
                e = ev.evaluate(o.title, o.org, o.location, o.eligibility.reasons, o.description,
                                guard=guard, run_id=ctx.run_id, runner=runner)
            except BudgetExhausted as exc:
                budget_hit = True
                pending += 1
                ctx.event("budget_exhausted", str(exc), level="warn")
                continue
            except Exception as exc:
                ctx.event("eval_failed", o.title, level="error", error=str(exc)[:300], dedup_key=o.dedup_key)
                continue
            d = e.data
            row = {"rubric": "jobs", "rubric_version": ev.RUBRIC_VERSION, "input_hash": ih, "fit": d["fit"],
                   "value": d["value"], "eligibility": d["eligibility"], "legitimacy": d["legitimacy"],
                   "evidence": d["evidence"], "gaps": d["gaps"], "recommendation": d["recommendation"],
                   "one_line": d["one_line"], "model": e.model, "tokens": e.tokens, "run_id": ctx.run_id,
                   "details": {"eligibility_reason": d["eligibility_reason"],
                               "legitimacy_signal": d["legitimacy_signal"], "flags": e.flags}}
            store.add_evaluation(opp_id, row)
            evaluations[o.dedup_key] = row
            evaluated_now += 1
            ctx.add_usage(e.tokens)
            ctx.event("evaluated", f"{o.org}: {o.title}", fit=d["fit"], recommendation=d["recommendation"])
        ctx.items_in, ctx.items_out = len(candidates), evaluated_now

    items: list[DigestItem] = []
    shortlisted = 0
    with run_stage(store, "rank") as ctx:
        for key, row in evaluations.items():
            o = by_key[key]
            r = rank(RankInput(row["fit"], row["value"], row["recommendation"]), today)
            status = "shortlisted" if row["recommendation"] in ("apply", "maybe") else "scored"
            shortlisted += status == "shortlisted"
            store.update_opportunity(ids[key]["id"], {"status": status, "priority": r.priority})
            items.append(DigestItem(o.org, o.title, o.location, o.url, row["fit"], row["value"],
                                    row["recommendation"], r.priority, row.get("one_line") or ""))
        ctx.items_in, ctx.items_out = len(evaluations), shortlisted

    budget = guard.status()
    reasons = collections.Counter(r[6:].split(" (")[0][:40] for o in opps for r in o.eligibility.reasons
                                  if r.startswith("fail"))
    md = build(today, items, DigestStats(
        collected=len(records), new=new_raw, after_dedupe=len(opps), eligible_pass=counts["pass"],
        eligible_unclear=counts["unclear"], skipped=counts["fail"], evaluated=evaluated_now,
        budget_used=budget.used, budget_cap=budget.cap, top_skip_reasons=reasons.most_common(4),
        source_health={c.name: health_for(c.report.success_rate) for c, _ in plan}))
    md += (f"\n_Evaluations: {evaluated_now} new, {cached} cached, {pending} waiting for budget._\n")
    store.add_digest(today, md)
    path = None
    if write_file:
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        path = DIGEST_DIR / f"{today.isoformat()}.md"
        path.write_text(md, encoding="utf-8")
    return DailyResult(len(records), new_raw, len(opps), counts["pass"], counts["unclear"], counts["fail"],
                       evaluated_now, cached, pending, shortlisted, str(path) if path else None)
