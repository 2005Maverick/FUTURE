"""Collector building blocks: the raw record shape, polite HTTP with retries,
and stable content hashing (a changed posting re-ingests; an unchanged one dedupes)."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol

import httpx

USER_AGENT = "FUTURE-personal-opportunity-search/0.1 (+https://github.com/2005Maverick/FUTURE)"
SEEDS_DIR = Path(__file__).with_name("seeds")


def content_hash(source: str, external_id: str, fields: dict[str, Any]) -> str:
    blob = json.dumps({"s": source, "id": external_id, "f": fields}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RawRecord:
    source: str
    external_id: str
    url: str
    payload: dict[str, Any]
    content_hash: str


@dataclass
class CollectorReport:
    source: str
    units_ok: int = 0
    units_failed: int = 0
    records: int = 0
    errors: list[str] = field(default_factory=list)
    ok_units: list[str] = field(default_factory=list)   # boards fetched successfully this run (liveness)

    @property
    def success_rate(self) -> float:
        total = self.units_ok + self.units_failed
        return 1.0 if total == 0 else self.units_ok / total


class Collector(Protocol):
    name: str
    report: CollectorReport

    def collect(self) -> Iterator[RawRecord]: ...


def read_seeds(filename: str) -> list[str]:
    lines = (SEEDS_DIR / filename).read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def polite_client(timeout_s: float = 20) -> httpx.Client:
    return httpx.Client(timeout=timeout_s, headers={"User-Agent": USER_AGENT}, follow_redirects=True)


def get_json(client: httpx.Client, url: str, *, retries: int = 3, backoff_s: float = 2.0,
             sleep=time.sleep) -> Any:
    """GET with retry on 429/5xx/network errors. 4xx (except 429) is not retried."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.get(url)
        except httpx.TransportError as exc:
            last = exc
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last = httpx.HTTPStatusError(f"{resp.status_code}", request=resp.request, response=resp)
            elif resp.status_code >= 400:
                resp.raise_for_status()
            else:
                return resp.json()
        if attempt < retries:
            sleep(backoff_s * (2 ** attempt))
    raise last  # type: ignore[misc]
