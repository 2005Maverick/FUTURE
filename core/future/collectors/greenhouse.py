"""Greenhouse public job-board collector (verified: no auth for GET, [C]).

GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
One request per company board; a failing board is recorded and skipped.
"""
from __future__ import annotations

import html
import time
from typing import Iterator

import httpx

from future.collectors.base import CollectorReport, RawRecord, content_hash, get_json, polite_client, read_seeds

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
SOURCE = "greenhouse"


class GreenhouseCollector:
    name = SOURCE

    def __init__(self, boards: list[str] | None = None, client: httpx.Client | None = None,
                 delay_s: float = 0.5, sleep=time.sleep) -> None:
        if boards is None:
            from future.collectors.registry import seeds_for   # manual seeds ∪ registry-selected boards
            boards = seeds_for(SOURCE)
        self.boards = boards
        self._client = client or polite_client()
        self._delay_s = delay_s
        self._sleep = sleep
        self.report = CollectorReport(source=SOURCE)

    def collect(self) -> Iterator[RawRecord]:
        for i, board in enumerate(self.boards):
            if i:
                self._sleep(self._delay_s)
            try:
                data = get_json(self._client, API.format(token=board), sleep=self._sleep)
            except Exception as exc:  # one bad board must not stop the run
                self.report.units_failed += 1
                self.report.errors.append(f"{board}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            self.report.units_ok += 1
            self.report.ok_units.append(board)
            for job in data.get("jobs", []):
                record = self._to_record(board, job)
                if record:
                    self.report.records += 1
                    yield record

    @staticmethod
    def _to_record(board: str, job: dict) -> RawRecord | None:
        job_id, url = job.get("id"), job.get("absolute_url")
        if not job_id or not url:
            return None
        fields = {
            "board": board,
            "title": (job.get("title") or "").strip(),
            "location": ((job.get("location") or {}).get("name") or "").strip(),
            "content_html": html.unescape(job.get("content") or ""),
            "departments": [d.get("name") for d in job.get("departments") or [] if d.get("name")],
            "offices": [o.get("name") for o in job.get("offices") or [] if o.get("name")],
            "updated_at": job.get("updated_at"),
            "first_published": job.get("first_published"),
        }
        hashed = {k: v for k, v in fields.items() if k != "updated_at"}  # timestamp churn ≠ content change
        external_id = f"{board}:{job_id}"
        return RawRecord(source=SOURCE, external_id=external_id, url=url, payload=fields,
                         content_hash=content_hash(SOURCE, external_id, hashed))
