"""Non-job tracks stage (S05): hackathons/competitions + watched programme pages, and
the weekly lab-outreach finder.

Watched pages: the page watcher emits a page only when its text changed, and stores
the new hash straight away. So every emitted page is first appended to a durable
queue, and extraction works through the queue with an idempotent progress ledger:
a run that stops (budget, crash) leaves the rest for the next run, nothing is lost.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from future import config
from future.agents import extractor
from future.collectors.base import Collector, RawRecord
from future.llm import claude_runner
from future.orchestrator.budget import BudgetGuard
from future.orchestrator.collect import SourceSpec, health_for
from future.orchestrator.daily import opportunity_row
from future.orchestrator.runlog import run_stage
from future.orchestrator.stages import JsonlProgress, process_items
from future.pipeline import tracks as tn
from future.store import Store

DATA_DIR = config.REPO_ROOT / "private" / "data" / "pagewatch"
DIGEST_DIR = config.REPO_ROOT / "private" / "digests"


@dataclass
class TracksResult:
    collected: int
    opportunities: int
    eligible: int
    pages_changed: int
    pages_extracted: int
    pages_waiting: int
    extracted_opportunities: int
    digest_path: str | None


def _collect(store: Store, ctx, plan: list[tuple[Collector, SourceSpec]]) -> list[RawRecord]:
    records: list[RawRecord] = []
    for collector, spec in plan:
        try:
            sid = store.ensure_source(collector.name, kind=spec.kind, track=spec.track, method=spec.method,
                                      url=spec.url, terms_verdict=spec.terms_verdict)
            recs = list(collector.collect())
            added = store.add_raw_items(sid, recs) if recs else 0
            rep = collector.report
            store.update_source_health(sid, health_for(rep.success_rate),
                                       {"records": rep.records or len(recs), "new": added,
                                        "success_rate": rep.success_rate})
            records += recs
            ctx.event("source_collected", f"{collector.name}: {len(recs)} records, {added} new",
                      errors=rep.errors[:3])
        except Exception as exc:  # one source failing must not stop the others
            ctx.event("source_failed", collector.name, level="error", error=str(exc)[:300])
    return records


class PageQueue:
    """Append-only queue of changed pages awaiting extraction (survives restarts)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, recs: list[RawRecord]) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps({"content_hash": r.content_hash, "url": r.url, "payload": r.payload},
                                    ensure_ascii=False) + "\n")

    def items(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # torn last line from a crash
        return out


def _page_of(item: dict) -> dict:
    p = item["payload"]
    return {"id": p["board"], "url": item["url"], "track": p["track"], "org": p["org"],
            "kind": p.get("page_kind", "programme")}


def extract_pages(store: Store, ctx, queue: PageQueue, progress: JsonlProgress, *, today: dt.date,
                  max_pages: int, guard: BudgetGuard, runner: Callable) -> tuple[list, int, int]:
    """Run the Extractor over queued pages not yet done. Returns (opportunities, done_now, waiting)."""
    done = progress.done_keys("extract_pages")
    todo = [i for i in queue.items() if i["content_hash"] not in done]
    todo = list({i["content_hash"]: i for i in todo}.values())       # same page text queued twice → once
    batch, waiting = todo[:max_pages], max(0, len(todo) - max_pages)
    found: list = []

    def handle(item: dict) -> None:
        page = _page_of(item)
        out = extractor.extract(item["payload"]["content_html"], source=f"pagewatch:{page['id']}", today=today,
                                guard=guard, run_id=ctx.run_id, runner=runner)
        ctx.add_usage(out.tokens)
        opps = [tn.from_extracted(o, page, content_hash=item["content_hash"], today=today)
                for o in out.opportunities]
        if opps:
            store.upsert_opportunities([opportunity_row(o) for o in opps])
        found.extend(opps)
        ctx.event("page_extracted", f"{page['org']}: {len(opps)} opportunities", page=page["id"],
                  tokens=out.tokens, flags=out.flags[:3])

    result = process_items("extract_pages", batch, key=lambda i: i["content_hash"], handler=handle,
                           progress=progress)
    for key, err in result.failed:
        ctx.event("page_extract_failed", key[:12], level="error", error=str(err)[:300])
    return found, result.processed, waiting + len(result.failed)


def run_tracks(store: Store, plan: list[tuple[Collector, SourceSpec]], *, today: dt.date,
               runner: Callable = claude_runner.run, max_pages: int = 8, data_dir: Path = DATA_DIR,
               write_file: bool = True) -> TracksResult:
    guard = BudgetGuard(store)
    queue, progress = PageQueue(data_dir / "queue.jsonl"), JsonlProgress(data_dir / "extract_progress.jsonl")
    with run_stage(store, "collect_tracks") as ctx:
        records = _collect(store, ctx, plan)
        pages = [r for r in records if r.source == "pagewatch"]
        queue.add(pages)
        ctx.items_in, ctx.items_out = len(records), len(records)

    with run_stage(store, "normalize_tracks") as ctx:
        opps = [tn.from_hackathon({"url": r.url, "content_hash": r.content_hash, "payload": r.payload,
                                   "source": r.source}, today=today)
                for r in records if r.payload.get("track") == "hackathon"]
        store.upsert_opportunities([opportunity_row(o) for o in opps])
        ctx.items_in, ctx.items_out = len(records), len(opps)

    with run_stage(store, "extract_pages", agent="extractor") as ctx:
        extracted, done_now, waiting = extract_pages(store, ctx, queue, progress, today=today,
                                                     max_pages=max_pages, guard=guard, runner=runner)
        ctx.items_in, ctx.items_out = done_now + waiting, len(extracted)

    md = build_tracks_digest(today, opps, extracted, waiting)
    store.add_digest(today, md)
    path = None
    if write_file:
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        path = DIGEST_DIR / f"{today.isoformat()}-tracks.md"
        path.write_text(md, encoding="utf-8")
    eligible = sum(o.eligibility.result != "fail" for o in opps)
    return TracksResult(len(records), len(opps), eligible, len(pages), done_now, waiting, len(extracted),
                        str(path) if path else None)


def _row(o) -> str:
    bits = [o.deadline and f"deadline {o.deadline}", o.details.get("mode"), o.details.get("prize"), o.location]
    return f"- **{o.title}** ({o.org}) — {' · '.join(b for b in bits if b)}  \n  [{o.url}]({o.url})"


def build_tracks_digest(today: dt.date, hackathons: list, extracted: list, waiting: int) -> str:
    keep = sorted((o for o in hackathons if o.eligibility.result != "fail"),
                  key=lambda o: (o.eligibility.result != "pass", o.deadline or "9999"))
    counts = collections.Counter(o.eligibility.result for o in hackathons)
    lines = [f"# FUTURE tracks digest — {today.isoformat()}", "",
             f"## Hackathons and competitions ({counts['pass']} open to you, {counts['unclear']} to check, "
             f"{counts['fail']} skipped)", ""]
    lines += [_row(o) for o in keep[:25]] or ["_None today._"]
    lines += ["", f"## New on watched pages ({len(extracted)})", ""]
    lines += [_row(o) + ("  \n  ⚠ " + "; ".join(o.details["scam_signals"]) if o.details.get("scam_signals") else "")
              for o in extracted] or ["_No watched page changed with a new opportunity._"]
    if waiting:
        lines += ["", f"_{waiting} changed page(s) wait for extraction next run (budget/batch cap)._"]
    return "\n".join(lines) + "\n"


def tracks_plan() -> list[tuple[Collector, SourceSpec]]:
    from future.collectors.hackathons import KaggleCollector, MLHCollector
    from future.collectors.pagewatch import PageWatchCollector
    return [
        (MLHCollector(), SourceSpec(kind="html_page", track="hackathon", method="mlh_season_page_embedded_json",
                                    url="https://www.mlh.com/seasons", terms_verdict="allowed")),
        (KaggleCollector(), SourceSpec(kind="api", track="hackathon", method="kaggle_competitions_api",
                                       url="https://www.kaggle.com/api/v1/competitions/list",
                                       terms_verdict="allowed")),
        (PageWatchCollector(), SourceSpec(kind="html_page", track="mixed", method="page_change_watch",
                                          url="seeds/pagewatch.json", terms_verdict="allowed")),
    ]


def run_labs(store: Store, *, today: dt.date, collector: Collector | None = None, top_n: int = 30,
             write_file: bool = True) -> dict:
    """Weekly: active labs on Pranav's topics from OpenAlex → lab_outreach targets. No model calls."""
    from future.collectors.openalex import OpenAlexLabCollector
    c = collector or OpenAlexLabCollector()
    spec = SourceSpec(kind="api", track="research", method="openalex_works_and_authors_api",
                      url="https://api.openalex.org", terms_verdict="allowed")
    with run_stage(store, "labs") as ctx:
        records = _collect(store, ctx, [(c, spec)])
        labs = [tn.from_lab({"url": r.url, "content_hash": r.content_hash, "payload": r.payload,
                             "source": r.source}) for r in records]
        store.upsert_opportunities([opportunity_row(o) for o in labs])
        keep = sorted((o for o in labs if o.eligibility.result != "fail"),
                      key=lambda o: (-(o.details.get("works") or 0), -(o.details.get("h_index") or 0)))
        ctx.items_in, ctx.items_out = len(records), len(keep)
    lines = [f"# FUTURE lab targets — {today.isoformat()}", "",
             f"{len(keep)} researchers with 2+ recent papers on your topics (h-index ≥ {tn.MIN_LAB_H_INDEX}); "
             f"{len(labs) - len(keep)} likely students left out. Check each profile before any outreach.", ""]
    lines += [f"- **{o.details.get('author_name')}**, {o.org} ({o.location}) — {o.details.get('works')} matching "
              f"works, h-index {o.details.get('h_index')}  \n  [{o.url}]({o.url})" for o in keep[:top_n]]
    path = None
    if write_file:
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        path = DIGEST_DIR / f"{today.isoformat()}-labs.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"records": len(records), "kept": len(keep), "requests": getattr(c, "requests", None),
            "cost_usd": getattr(c, "cost_usd", None), "digest_path": str(path) if path else None}

