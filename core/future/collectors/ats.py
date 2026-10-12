"""Lever, Ashby and Workable public job-board collectors (S03.01).

Each emits RawRecords in the SAME payload shape as the Greenhouse collector
({board, title, location, offices, content_html, departments, updated_at,
first_published}) so a single normaliser + eligibility filter serves every ATS.
Remote postings get "Remote" appended to `location` so the location parser sees it.

Endpoints (public, no auth; verified live 2026-10-12):
  Lever    GET https://api.lever.co/v0/postings/{slug}?mode=json
  Ashby    GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
  Workable GET https://apply.workable.com/api/v1/widget/accounts/{slug}          (list)
           GET https://apply.workable.com/api/v2/accounts/{slug}/jobs/{shortcode} (description)
"""
from __future__ import annotations

import html
import time
from typing import Any, Iterator

import httpx

from future.collectors.base import CollectorReport, RawRecord, content_hash, get_json, polite_client, read_seeds


def _record(source: str, board: str, job_id: str, url: str, fields: dict[str, Any]) -> RawRecord:
    hashed = {k: v for k, v in fields.items() if k != "updated_at"}
    ext = f"{board}:{job_id}"
    return RawRecord(source=source, external_id=ext, url=url, payload=fields,
                     content_hash=content_hash(source, ext, hashed))


def _with_remote(location: str, remote: bool) -> str:
    return f"{location} | Remote" if remote and "remote" not in location.lower() else location


class _BoardCollector:
    name = ""
    seed_file = ""

    def __init__(self, boards: list[str] | None = None, client: httpx.Client | None = None,
                 delay_s: float = 0.5, sleep=time.sleep) -> None:
        self.boards = boards if boards is not None else read_seeds(self.seed_file)
        self._client = client or polite_client()
        self._delay_s, self._sleep = delay_s, sleep
        self.report = CollectorReport(source=self.name)

    def collect(self) -> Iterator[RawRecord]:
        for i, board in enumerate(self.boards):
            if i:
                self._sleep(self._delay_s)
            try:
                records = list(self._board(board))
            except Exception as exc:  # one bad board must not stop the run
                self.report.units_failed += 1
                self.report.errors.append(f"{board}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            self.report.units_ok += 1
            self.report.records += len(records)
            yield from records

    def _board(self, board: str) -> Iterator[RawRecord]:
        raise NotImplementedError


class AshbyCollector(_BoardCollector):
    name, seed_file = "ashby", "ashby.txt"
    API = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"

    def _board(self, board):
        data = get_json(self._client, self.API.format(slug=board), sleep=self._sleep)
        for j in data.get("jobs", []):
            if not j.get("id") or not j.get("jobUrl") or j.get("isListed") is False:
                continue
            remote = bool(j.get("isRemote")) or (j.get("workplaceType") or "").lower() == "remote"
            secondary = [s.get("location") for s in j.get("secondaryLocations") or [] if isinstance(s, dict) and s.get("location")]
            comp = ((j.get("compensation") or {}).get("scrapeableCompensationSalarySummary")
                    or (j.get("compensation") or {}).get("compensationTierSummary"))
            content = (j.get("descriptionHtml") or "") + (f"<p>Compensation: {comp}</p>" if comp else "")
            yield _record(self.name, board, j["id"], j["jobUrl"], {
                "board": board, "title": (j.get("title") or "").strip(),
                "location": _with_remote((j.get("location") or "").strip(), remote), "offices": secondary,
                "content_html": content, "departments": [d for d in (j.get("department"), j.get("team")) if d],
                "employment_type": j.get("employmentType"), "updated_at": None,
                "first_published": j.get("publishedAt")})


class LeverCollector(_BoardCollector):
    name, seed_file = "lever", "lever.txt"
    API = "https://api.lever.co/v0/postings/{slug}?mode=json"

    def _board(self, board):
        for p in get_json(self._client, self.API.format(slug=board), sleep=self._sleep):
            if not p.get("id") or not p.get("hostedUrl"):
                continue
            cats = p.get("categories") or {}
            locs = [l for l in (cats.get("allLocations") or []) if l] or ([cats["location"]] if cats.get("location") else [])
            remote = (p.get("workplaceType") or "").lower() == "remote"
            sections = "".join(f"<h3>{html.escape(l.get('text', ''))}</h3><ul>{l.get('content', '')}</ul>"
                               for l in p.get("lists") or [])
            content = (p.get("description") or "") + sections + (p.get("additional") or "")
            yield _record(self.name, board, p["id"], p["hostedUrl"], {
                "board": board, "title": (p.get("text") or "").strip(),
                "location": _with_remote(" | ".join(locs), remote), "offices": [],
                "content_html": content, "departments": [d for d in (cats.get("department"), cats.get("team")) if d],
                "employment_type": cats.get("commitment"), "updated_at": None,
                "first_published": p.get("createdAt")})


class WorkableCollector(_BoardCollector):
    name, seed_file = "workable", "workable.txt"
    LIST = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
    DETAIL = "https://apply.workable.com/api/v2/accounts/{slug}/jobs/{code}"

    def _board(self, board):
        data = get_json(self._client, self.LIST.format(slug=board), sleep=self._sleep)
        for j in data.get("jobs", []):
            code = j.get("shortcode")
            if not code or not j.get("url"):
                continue
            try:
                detail = get_json(self._client, self.DETAIL.format(slug=board, code=code), sleep=self._sleep)
            except Exception:
                detail = {}
            self._sleep(self._delay_s / 2)
            locs = [", ".join(x for x in (l.get("city"), l.get("country")) if x) for l in j.get("locations") or []]
            location = " | ".join(l for l in locs if l) or ", ".join(x for x in (j.get("city"), j.get("country")) if x)
            remote = str(j.get("telecommuting")).lower() == "true"
            content = "".join(detail.get(k) or "" for k in ("description", "requirements", "benefits"))
            yield _record(self.name, board, code, j["url"], {
                "board": board, "title": (j.get("title") or "").strip(),
                "location": _with_remote(location, remote), "offices": [],
                "content_html": content, "departments": [d for d in (j.get("department"), j.get("function")) if d],
                "employment_type": j.get("employment_type"), "updated_at": None,
                "first_published": j.get("published_on")})
