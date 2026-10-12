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


class MemoryStore:
    """In-memory Store for tests and dry runs."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.budget: list[BudgetEntry] = []
        self.settings: dict[str, Any] = {}
        self._ids = itertools.count(1)

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
