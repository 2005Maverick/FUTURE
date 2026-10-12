"""Remote-job boards (S03.03): Himalayas and Remotive. Both aggregate many
companies, so payloads carry an explicit `org`. Same common payload shape as the
ATS collectors; location is "Remote - <allowed countries>" or "Remote - Worldwide".

Terms (research [G], verified 2026-10-12):
- Himalayas: free JSON API, no key; ≤20 jobs/request; credit Himalayas (link kept).
- Remotive: public API, 24h delayed, ≤ ~4 calls/day, must link back to the Remotive
  URL and name Remotive as the source; never resubmit jobs to other boards.
"""
from __future__ import annotations

import time
from typing import Iterator

import httpx

from future.collectors.base import CollectorReport, RawRecord, content_hash, get_json, polite_client

HIMALAYAS = "https://himalayas.app/jobs/api/search"
REMOTIVE = "https://remotive.com/api/remote-jobs"
HIMALAYAS_QUERIES = ["machine learning", "AI engineer", "LLM", "research engineer", "data scientist",
                     "computer vision", "NLP"]
REMOTIVE_QUERIES = ["machine learning", "AI"]          # 2 calls/run, under the ~4/day limit


def _rec(source: str, ext: str, url: str, fields: dict) -> RawRecord:
    return RawRecord(source, ext, url, fields, content_hash(source, ext, {k: v for k, v in fields.items() if k != "updated_at"}))


class HimalayasCollector:
    name = "himalayas"

    def __init__(self, queries: list[str] | None = None, client: httpx.Client | None = None,
                 max_pages: int = 3, delay_s: float = 1.0, sleep=time.sleep) -> None:
        self.queries = queries or HIMALAYAS_QUERIES
        self._client, self._max_pages, self._delay_s, self._sleep = client or polite_client(), max_pages, delay_s, sleep
        self.report = CollectorReport(source=self.name)

    def collect(self) -> Iterator[RawRecord]:
        seen: set[str] = set()
        for q in self.queries:
            for page in range(self._max_pages):
                try:
                    data = get_json(self._client, f"{HIMALAYAS}?q={q}&country=IN&limit=20&offset={page * 20}",
                                    sleep=self._sleep)
                except Exception as exc:
                    self.report.units_failed += 1
                    self.report.errors.append(f"{q}#{page}: {type(exc).__name__}")
                    break
                self.report.units_ok += 1
                jobs = data.get("jobs", [])
                for j in jobs:
                    guid = j.get("guid") or j.get("applicationLink")
                    if not guid or guid in seen:
                        continue
                    seen.add(guid)
                    self.report.records += 1
                    yield self._to_record(j, guid)
                self._sleep(self._delay_s)
                if len(jobs) < 20:
                    break

    @staticmethod
    def _to_record(j: dict, guid: str) -> RawRecord:
        restr = [str(r) for r in j.get("locationRestrictions") or []]
        pay = ""
        if j.get("minSalary") or j.get("maxSalary"):
            pay = f"<p>Salary: {j.get('minSalary') or '?'}–{j.get('maxSalary') or '?'} {j.get('currency') or ''} per {j.get('salaryPeriod') or 'year'}</p>"
        seniority = ", ".join(j.get("seniority") or [])
        return _rec("himalayas", guid, guid, {
            "board": j.get("companySlug") or "himalayas", "org": j.get("companyName"),
            "title": (j.get("title") or "").strip(),
            "location": "Remote - " + (", ".join(restr) if restr else "Worldwide"), "offices": [],
            "content_html": (j.get("description") or j.get("excerpt") or "") + pay
                            + (f"<p>Seniority: {seniority}</p>" if seniority else ""),
            "departments": list(j.get("categories") or [])[:3], "employment_type": j.get("employmentType"),
            "updated_at": None, "first_published": j.get("pubDate"), "via": "Himalayas"})


class RemotiveCollector:
    name = "remotive"

    def __init__(self, queries: list[str] | None = None, client: httpx.Client | None = None,
                 delay_s: float = 31.0, sleep=time.sleep) -> None:
        self.queries = queries or REMOTIVE_QUERIES
        self._client, self._delay_s, self._sleep = client or polite_client(), delay_s, sleep
        self.report = CollectorReport(source=self.name)

    def collect(self) -> Iterator[RawRecord]:
        seen: set[int] = set()
        for i, q in enumerate(self.queries):
            if i:
                self._sleep(self._delay_s)   # Remotive blocks >2 requests/minute
            try:
                data = get_json(self._client, f"{REMOTIVE}?search={q}", retries=0, sleep=self._sleep)
            except Exception as exc:
                self.report.units_failed += 1
                self.report.errors.append(f"{q}: {type(exc).__name__}")
                continue
            self.report.units_ok += 1
            for j in data.get("jobs", []):
                if not j.get("id") or not j.get("url") or j["id"] in seen:
                    continue
                seen.add(j["id"])
                self.report.records += 1
                yield _rec("remotive", str(j["id"]), j["url"], {
                    "board": "remotive", "org": j.get("company_name"), "title": (j.get("title") or "").strip(),
                    "location": f"Remote - {j.get('candidate_required_location') or 'unspecified'}", "offices": [],
                    "content_html": (j.get("description") or "")
                                    + (f"<p>Salary: {j['salary']}</p>" if j.get("salary") else ""),
                    "departments": [j.get("category")] if j.get("category") else [],
                    "employment_type": j.get("job_type"), "updated_at": None,
                    "first_published": j.get("publication_date"), "via": "Remotive"})
