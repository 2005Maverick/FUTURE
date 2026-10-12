"""Persistence boundary for orchestration state (runs, events, budget, settings).

`Store` is the interface the orchestrator depends on. `MemoryStore` backs unit
tests; `SupabaseStore` writes to the live database through PostgREST with the
secret key (bypasses RLS; laptop-only, never shipped to the browser).
"""
from __future__ import annotations

import datetime as dt
import itertools
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


@dataclass
class BudgetEntry:
    purpose: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_create_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    run_id: str | None = None
    at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_create_tokens + self.cache_read_tokens


class Store(Protocol):
    def start_run(self, stage: str, agent: str | None, meta: dict[str, Any]) -> str: ...
    def finish_run(self, run_id: str, *, status: str, items_in: int, items_out: int,
                   tokens: int, cost_usd: float, error: str | None) -> None: ...
    def add_event(self, run_id: str | None, kind: str, message: str, level: str, data: dict[str, Any]) -> None: ...
    def add_budget(self, entry: BudgetEntry) -> None: ...
    def tokens_used_since(self, since: dt.datetime) -> int: ...
    def get_setting(self, key: str, default: Any = None) -> Any: ...
    def set_setting(self, key: str, value: Any) -> None: ...
    def ensure_source(self, name: str, *, kind: str, track: str, method: str, url: str | None,
                      terms_verdict: str) -> str: ...
    def add_raw_items(self, source_id: str, records: list[Any]) -> int: ...
    def update_source_health(self, source_id: str, health: str, yield_stats: dict[str, Any]) -> None: ...
    # opportunities / evaluations / digests (S02.05b). Opportunities are keyed by dedup_key;
    # an existing opportunity's status is never overwritten by re-ingestion.
    def upsert_opportunities(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]: ...
    def update_opportunity(self, opp_id: str, fields: dict[str, Any]) -> None: ...
    def get_evaluation(self, opp_id: str, rubric_version: str, input_hash: str) -> dict[str, Any] | None: ...
    def add_evaluation(self, opp_id: str, row: dict[str, Any]) -> None: ...
    def add_digest(self, for_date: dt.date, content_md: str) -> None: ...
    def list_open_opportunities(self) -> list[dict[str, Any]]: ...


OPEN_STATUSES = ("found", "verified", "scored", "shortlisted")
OPP_INSERT_FIELDS = ("type", "track", "title", "org", "url", "canonical_url", "dedup_key", "location", "remote",
                     "countries", "deadline", "eligibility", "details", "status", "skip_reason")
OPP_REFRESH_FIELDS = ("location", "details", "eligibility")   # safe to refresh on re-ingestion


def raw_row(source_id: str, record: Any) -> dict[str, Any]:
    return {"source_id": source_id, "external_id": record.external_id, "url": record.url,
            "content_hash": record.content_hash, "payload": record.payload}


class MemoryStore:
    """In-memory Store for tests and dry runs."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.budget: list[BudgetEntry] = []
        self.settings: dict[str, Any] = {}
        self.sources_by_name: dict[str, dict[str, Any]] = {}
        self.raw: dict[str, dict[str, Any]] = {}
        self.opps: dict[str, dict[str, Any]] = {}          # dedup_key -> row (id == dedup_key here)
        self.evals: list[dict[str, Any]] = []
        self.digests: dict[str, str] = {}
        self._ids = itertools.count(1)

    def upsert_opportunities(self, rows):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        out = {}
        for row in rows:
            key = row["dedup_key"]
            if key in self.opps:
                existing = self.opps[key]
                existing.update({k: row[k] for k in OPP_REFRESH_FIELDS if k in row}, last_seen_at=now)
            else:
                self.opps[key] = {**{k: row.get(k) for k in OPP_INSERT_FIELDS}, "id": key,
                                  "first_seen_at": now, "last_seen_at": now, "priority": None}
            out[key] = {"id": self.opps[key]["id"], "status": self.opps[key]["status"]}
        return out

    def update_opportunity(self, opp_id, fields):
        self.opps[opp_id].update(fields)

    def get_evaluation(self, opp_id, rubric_version, input_hash):
        for row in reversed(self.evals):
            if (row["opportunity_id"], row["rubric_version"], row["input_hash"]) == (opp_id, rubric_version, input_hash):
                return row
        return None

    def add_evaluation(self, opp_id, row):
        self.evals.append({**row, "opportunity_id": opp_id})

    def add_digest(self, for_date, content_md):
        self.digests[for_date.isoformat()] = content_md

    def list_open_opportunities(self):
        return [{"id": o["id"], "dedup_key": k, "details": o.get("details") or {}, "last_seen_at": o.get("last_seen_at"),
                 "deadline": o.get("deadline")}
                for k, o in self.opps.items() if o.get("status") in OPEN_STATUSES]

    def start_run(self, stage, agent, meta):
        run_id = str(uuid.uuid4())
        self.runs[run_id] = {"stage": stage, "agent": agent, "meta": dict(meta), "status": "running",
                             "started_at": dt.datetime.now(dt.timezone.utc)}
        return run_id

    def finish_run(self, run_id, *, status, items_in, items_out, tokens, cost_usd, error):
        self.runs[run_id].update(status=status, items_in=items_in, items_out=items_out, tokens=tokens,
                                 cost_usd=cost_usd, error=error, ended_at=dt.datetime.now(dt.timezone.utc))

    def add_event(self, run_id, kind, message, level, data):
        self.events.append({"id": next(self._ids), "run_id": run_id, "kind": kind, "message": message,
                            "level": level, "data": dict(data)})

    def add_budget(self, entry):
        self.budget.append(entry)

    def tokens_used_since(self, since):
        return sum(e.total_tokens for e in self.budget if e.at >= since)

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = value

    # sources & raw items
    def ensure_source(self, name, *, kind, track, method, url, terms_verdict):
        if name not in self.sources_by_name:
            self.sources_by_name[name] = {"id": str(uuid.uuid4()), "kind": kind, "track": track, "method": method,
                                          "url": url, "terms_verdict": terms_verdict, "health": "unknown", "yield": {}}
        return self.sources_by_name[name]["id"]

    def add_raw_items(self, source_id, records):
        new = 0
        for rec in records:
            if rec.content_hash not in self.raw:
                self.raw[rec.content_hash] = raw_row(source_id, rec)
                new += 1
        return new

    def update_source_health(self, source_id, health, yield_stats):
        for src in self.sources_by_name.values():
            if src["id"] == source_id:
                src.update(health=health, **{"yield": yield_stats})


class SupabaseStore:
    """Store backed by Supabase PostgREST using the secret (service) key."""

    def __init__(self, url: str, secret_key: str, client: httpx.Client | None = None) -> None:
        self._base = url.rstrip("/") + "/rest/v1"
        self._client = client or httpx.Client(timeout=20)
        self._headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}",
                         "Content-Type": "application/json"}

    def _req(self, method: str, path: str, **kw) -> httpx.Response:
        headers = {**self._headers, **kw.pop("headers", {})}
        resp = self._client.request(method, f"{self._base}/{path}", headers=headers, **kw)
        if resp.status_code >= 400:
            raise RuntimeError(f"Supabase {method} {path} failed: {resp.status_code} {resp.text[:300]}")
        return resp

    def start_run(self, stage, agent, meta):
        resp = self._req("POST", "runs", json={"stage": stage, "agent": agent, "meta": meta},
                         headers={"Prefer": "return=representation"})
        return resp.json()[0]["id"]

    def finish_run(self, run_id, *, status, items_in, items_out, tokens, cost_usd, error):
        self._req("PATCH", f"runs?id=eq.{run_id}", json={
            "status": status, "items_in": items_in, "items_out": items_out, "tokens": tokens,
            "cost_usd": cost_usd, "error": error, "ended_at": dt.datetime.now(dt.timezone.utc).isoformat()})

    def add_event(self, run_id, kind, message, level, data):
        self._req("POST", "events", json={"run_id": run_id, "kind": kind, "message": message,
                                           "level": level, "data": data})

    def add_budget(self, entry):
        self._req("POST", "budget_ledger", json={
            "purpose": entry.purpose, "model": entry.model, "run_id": entry.run_id,
            "input_tokens": entry.input_tokens, "output_tokens": entry.output_tokens,
            "cache_create_tokens": entry.cache_create_tokens, "cache_read_tokens": entry.cache_read_tokens,
            "total_tokens": entry.total_tokens, "cost_usd": entry.cost_usd, "at": entry.at.isoformat()})

    def tokens_used_since(self, since):
        resp = self._req("GET", f"budget_ledger?select=total_tokens&at=gte.{since.isoformat()}")
        return sum(int(row["total_tokens"]) for row in resp.json())

    def get_setting(self, key, default=None):
        rows = self._req("GET", f"settings?select=value&key=eq.{key}").json()
        return rows[0]["value"] if rows else default

    def set_setting(self, key, value):
        self._req("POST", "settings", json={"key": key, "value": value},
                  headers={"Prefer": "resolution=merge-duplicates"})

    def ensure_source(self, name, *, kind, track, method, url, terms_verdict):
        rows = self._req("POST", "sources?on_conflict=name", json={
            "name": name, "kind": kind, "track": track, "method": method, "url": url,
            "terms_verdict": terms_verdict},
            headers={"Prefer": "resolution=merge-duplicates,return=representation"}).json()
        return rows[0]["id"]

    def add_raw_items(self, source_id, records, batch: int = 500):
        new = 0
        for i in range(0, len(records), batch):
            chunk = [raw_row(source_id, r) for r in records[i:i + batch]]
            resp = self._req("POST", "raw_items?on_conflict=content_hash", json=chunk,
                             headers={"Prefer": "resolution=ignore-duplicates,return=representation"})
            new += len(resp.json())
        return new

    def upsert_opportunities(self, rows, batch: int = 300, key_batch: int = 100):
        # 1) insert only NEW rows (existing ones keep their status) 2) refresh safe fields 3) read back id/status
        for i in range(0, len(rows), batch):
            chunk = [{k: r.get(k) for k in OPP_INSERT_FIELDS} for r in rows[i:i + batch]]
            self._req("POST", "opportunities?on_conflict=dedup_key", json=chunk,
                      headers={"Prefer": "resolution=ignore-duplicates,return=minimal"})
        out: dict[str, dict[str, Any]] = {}
        keys = [r["dedup_key"] for r in rows]
        for i in range(0, len(keys), key_batch):
            in_list = ",".join(keys[i:i + key_batch])
            for rec in self._req("GET", f"opportunities?select=id,status,dedup_key&dedup_key=in.({in_list})").json():
                out[rec["dedup_key"]] = {"id": rec["id"], "status": rec["status"]}
        # Not yet: refreshing location/details/last_seen_at on existing rows needs a bulk RPC (S03.04 liveness).
        return out

    def update_opportunity(self, opp_id, fields):
        self._req("PATCH", f"opportunities?id=eq.{opp_id}", json=fields)

    def get_evaluation(self, opp_id, rubric_version, input_hash):
        rows = self._req("GET", f"evaluations?select=*&opportunity_id=eq.{opp_id}&rubric_version=eq.{rubric_version}"
                                f"&input_hash=eq.{input_hash}&order=created_at.desc&limit=1").json()
        return rows[0] if rows else None

    def add_evaluation(self, opp_id, row):
        self._req("POST", "evaluations", json={**row, "opportunity_id": opp_id})

    def add_digest(self, for_date, content_md):
        self._req("POST", "digests?on_conflict=for_date", json={"for_date": for_date.isoformat(), "content_md": content_md},
                  headers={"Prefer": "resolution=merge-duplicates"})

    def list_open_opportunities(self, page: int = 1000):
        out, offset = [], 0
        statuses = ",".join(OPEN_STATUSES)
        while True:
            rows = self._req("GET", f"opportunities?select=id,dedup_key,details,last_seen_at,deadline&status=in.({statuses})"
                                    f"&order=id&limit={page}&offset={offset}").json()
            out += rows
            if len(rows) < page:
                return out
            offset += page

    def update_source_health(self, source_id, health, yield_stats):
        self._req("PATCH", f"sources?id=eq.{source_id}", json={
            "health": health, "yield": yield_stats, "last_run_at": dt.datetime.now(dt.timezone.utc).isoformat()})
