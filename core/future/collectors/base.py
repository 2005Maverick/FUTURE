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


REQUEST_DEADLINE_S = 60.0
MAX_DEADLINE_RETRIES = 1


class RequestDeadline(httpx.TransportError):
    """Whole-request wall-clock limit exceeded (body trickling or stalled)."""


def fetch(client: httpx.Client, url: str, deadline_s: float = REQUEST_DEADLINE_S,
          clock=time.monotonic) -> tuple[int, bytes]:
    """GET with a HARD wall-clock deadline on the whole response.

    httpx's timeout is per read operation, so a server that keeps a connection
    open and trickles (or stalls after a laptop sleep/resume) can hang a run for
    hours — the 2026-10-12 daily run hung ~5h on one Cloudflare-hosted board. The
    body is streamed and the deadline checked between chunks; a single stalled read
    is still bounded by the client's read timeout.
    """
    end = clock() + deadline_s
    with client.stream("GET", url) as resp:
        chunks = []
        for chunk in resp.iter_bytes():
            chunks.append(chunk)
            if clock() > end:
                raise RequestDeadline(f"exceeded {deadline_s:.0f}s: {url}")
        return resp.status_code, b"".join(chunks)


def get_json(client: httpx.Client, url: str, *, retries: int = 3, backoff_s: float = 2.0,
             sleep=time.sleep, deadline_s: float = REQUEST_DEADLINE_S) -> Any:
    """GET JSON with a hard per-request deadline; retry on 429/5xx/network errors.
    A deadline overrun is retried only once: a board that stalls for 60s usually stalls
    again, and 3 retries cost ~4 min per dead board (2026-10-13 daily run).
    4xx (except 429) is not retried."""
    last: Exception | None = None
    deadlines = 0
    for attempt in range(retries + 1):
        try:
            status, body = fetch(client, url, deadline_s)
        except RequestDeadline as exc:
            last, deadlines = exc, deadlines + 1
            if deadlines > MAX_DEADLINE_RETRIES:
                raise
        except httpx.TransportError as exc:
            last = exc
        else:
            if status == 429 or status >= 500:
                last = httpx.HTTPError(f"HTTP {status}: {url}")
            elif status >= 400:
                raise httpx.HTTPStatusError(f"HTTP {status}: {url}", request=httpx.Request("GET", url),
                                            response=httpx.Response(status))
            else:
                return json.loads(body)
        if attempt < retries:
            sleep(backoff_s * (2 ** attempt))
    raise last  # type: ignore[misc]
