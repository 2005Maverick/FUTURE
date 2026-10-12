"""File-backed Store used until Supabase write access exists (H11).

Persists between runs, as one JSON snapshot in private/data/state.json: settings,
budget ledger, sources, seen raw-content hashes (not payloads, to keep the file
small), opportunities, evaluations, digests. Written atomically on save().
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import asdict
from pathlib import Path

from future.store import BudgetEntry, MemoryStore

MAX_EVENTS_KEPT = 2000


class LocalFileStore(MemoryStore):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = Path(path)
        if self.path.exists():
            self._load(json.loads(self.path.read_text(encoding="utf-8")))

    def _load(self, s: dict) -> None:
        self.settings = s.get("settings", {})
        self.budget = [BudgetEntry(**{**b, "at": dt.datetime.fromisoformat(b["at"])}) for b in s.get("budget", [])]
        self.sources_by_name = s.get("sources", {})
        self.raw = {h: {"content_hash": h} for h in s.get("raw_hashes", [])}
        self.opps = s.get("opportunities", {})
        self.evals = s.get("evaluations", [])
        self.digests = s.get("digests", {})
        self.events = s.get("events", [])

    def add_raw_items(self, source_id, records):
        new = 0
        for rec in records:
            if rec.content_hash not in self.raw:
                self.raw[rec.content_hash] = {"content_hash": rec.content_hash}   # payload lives in the daily raw file
                new += 1
        return new

    def save(self) -> None:
        snapshot = {
            "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "settings": self.settings,
            "budget": [{**asdict(b), "at": b.at.isoformat()} for b in self.budget],
            "sources": self.sources_by_name,
            "raw_hashes": list(self.raw),
            "opportunities": self.opps,
            "evaluations": self.evals,
            "digests": self.digests,
            "events": self.events[-MAX_EVENTS_KEPT:],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False, default=str), encoding="utf-8")
        if self.path.exists():
            # keep the previous snapshot: losing state also loses cached evaluations (tokens already spent)
            os.replace(self.path, self.path.with_suffix(".bak.json"))
        os.replace(tmp, self.path)
