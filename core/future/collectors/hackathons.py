"""Hackathon and competition collectors (S05.04): MLH season events and Kaggle
competitions. Same common payload shape as the job collectors ({board, org, title,
location, offices, content_html, departments, updated_at, first_published}) plus
track="hackathon", opp_type ("hackathon" | "competition"), deadline (ISO date or
None), prize (text or None) and mode ("online" | "in-person" | "hybrid" | None).

Sources and terms (verified live 2026-10-13):
- MLH: the public season page (www.mlh.com/seasons/<YYYY>/events, no login) embeds
  its event list as Inertia JSON. robots.txt allows it (only /account, /v4, /auth...
  are disallowed); the Terms of Use (rev. 2021-06-16) carry no scraping clause.
  One request per run. Upcoming events are not paginated; past events are skipped.
- Kaggle: the official REST API (/api/v1/competitions/list) with Pranav's own
  KAGGLE_API_TOKEN as a Bearer token. Defaults to active competitions, 20 per page.
- Devpost: NOT collected. Its public /api/hackathons JSON needs no login and
  robots.txt allows it, but the Devpost Terms of Service (updated 2025-12-05) forbid
  using "automated software ... to access, scrape, crawl or spider the Site ... or any
  related data". Devpost items arrive via its alert emails instead (S04.03).

Shared filter: government hackathons (Smart India Hackathon / SIH, iDEX, Defence
India Startup Challenge / DISC) and items whose deadline has passed are dropped.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import time
from typing import Any, Iterator

import httpx

from future import config
from future.collectors.base import (CollectorReport, RawRecord, content_hash, fetch, get_json,
                                    polite_client)

MLH_SEASON_URL = "https://www.mlh.com/seasons/{season}/events"
MLH_BASE = "https://www.mlh.com"
KAGGLE_LIST = "https://www.kaggle.com/api/v1/competitions/list"
KAGGLE_PAGE_SIZE = 20
KAGGLE_SKIP_CATEGORIES = frozenset({"Getting Started"})   # perpetual tutorials: no prize, 2030 deadlines
NO_PRIZE = frozenset({"", "knowledge", "kudos", "none"})

MLH_MODES = {"physical": "in-person", "hybrid_physical": "hybrid", "hybrid": "hybrid",
             "digital": "online", "online": "online", "virtual": "online"}

# Government hackathons are out of scope (DESIGN §1 exclusions).
GOV_PATTERNS = (
    re.compile(r"smart\s*india\s*hackathon", re.I),
    re.compile(r"\bSIH\s*(?:20\d\d)?\b"),
    re.compile(r"\biDEX\b", re.I),
    re.compile(r"innovations?\s+for\s+defen[cs]e\s+excellence", re.I),
    re.compile(r"defen[cs]e\s+india\s+startup\s+challenge", re.I),
    re.compile(r"\bDISC\s*\d+\b"),
)
_PAGE_JSON = re.compile(r'<script[^>]*data-page="app"[^>]*>(.*?)</script>', re.S)


def current_mlh_season(today: dt.date) -> int:
    """MLH seasons run Aug-Jul and are named by the year they end (Oct 2026 -> 2027)."""
    return today.year + 1 if today.month >= 8 else today.year


def gov_exclusion(fields: dict[str, Any]) -> str | None:
    """Return the matched pattern if this is a government hackathon, else None."""
    text = " ".join(str(fields.get(k) or "") for k in ("title", "org", "board"))
    for pat in GOV_PATTERNS:
        if pat.search(text):
            return pat.pattern
    return None


def is_expired(deadline: str | None, today: dt.date) -> bool:
    if not deadline:
        return False
    try:
        return dt.date.fromisoformat(deadline) < today
    except ValueError:
        return False


def drop_reason(fields: dict[str, Any], today: dt.date) -> str | None:
    """Shared exclusion filter: 'government' or 'expired', or None to keep."""
    if gov_exclusion(fields):
        return "government"
    if is_expired(fields.get("deadline"), today):
        return "expired"
    return None


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _rec(source: str, ext: str, url: str, fields: dict) -> RawRecord:
    return RawRecord(source, ext, url, fields,
                     content_hash(source, ext, {k: v for k, v in fields.items() if k != "updated_at"}))


def _html(rows: list[tuple[str, Any]], lead: str = "") -> str:
    body = "".join(f"<p>{html.escape(k)}: {html.escape(str(v))}</p>" for k, v in rows if v not in (None, "", []))
    return (f"<p>{html.escape(lead)}</p>" if lead else "") + body


class _FilteringCollector:
    name = "hackathons"

    def __init__(self, today: dt.date | None) -> None:
        self._today = today or dt.datetime.now(dt.timezone.utc).date()
        self.report = CollectorReport(source=self.name)
        self.dropped: dict[str, int] = {}

    def _keep(self, fields: dict[str, Any]) -> bool:
        reason = drop_reason(fields, self._today)
        if reason:
            self.dropped = {**self.dropped, reason: self.dropped.get(reason, 0) + 1}
            return False
        return True

    def _fail(self, unit: str, exc: Exception) -> None:
        self.report.units_failed += 1
        self.report.errors.append(f"{unit}: {type(exc).__name__}: {str(exc)[:120]}")


class MLHCollector(_FilteringCollector):
    name = "mlh"

    def __init__(self, season: int | None = None, client: httpx.Client | None = None,
                 today: dt.date | None = None) -> None:
        super().__init__(today)
        self.season = season or current_mlh_season(self._today)
        self._client = client or polite_client()

    def collect(self) -> Iterator[RawRecord]:
        unit = f"season-{self.season}"
        try:
            events = self._fetch_events()
        except Exception as exc:
            self._fail(unit, exc)
            return
        self.report.units_ok += 1
        self.report.ok_units.append(unit)
        seen: set[str] = set()
        for ev in events:
            if not isinstance(ev, dict) or ev.get("status") == "ended":
                continue
            ext = str(ev.get("slug") or ev.get("id") or "")
            if not ext or not ev.get("name") or ext in seen:
                continue
            seen.add(ext)
            rec = self._to_record(ev, ext)
            if self._keep(rec.payload):
                self.report.records += 1
                yield rec

    def _fetch_events(self) -> list:
        url = MLH_SEASON_URL.format(season=self.season)
        status, body = fetch(self._client, url)
        if status >= 400:
            raise httpx.HTTPError(f"HTTP {status}: {url}")
        m = _PAGE_JSON.search(body.decode("utf-8", errors="replace"))
        if not m:
            raise ValueError("no Inertia data-page JSON on the season page (layout changed?)")
        props = json.loads(m.group(1)).get("props") or {}
        if "upcomingEvents" not in props:
            raise ValueError("season page JSON has no upcomingEvents (layout changed?)")
        return props.get("upcomingEvents") or []

    def _to_record(self, ev: dict, ext: str) -> RawRecord:
        mode = MLH_MODES.get(str(ev.get("formatType") or "").lower())
        location = re.sub(r"\s+,", ",", " ".join(str(ev.get("location") or "").split()))
        country = str((ev.get("venueAddress") or {}).get("country") or "").strip()
        if country and not location.endswith(country):
            location = f"{location}, {country}" if location else country   # eligibility needs the country
        location = location or ("Online" if mode == "online" else "")
        focus = list((ev.get("customFields") or {}).get("hackathon_focus") or [])
        diversity = list((ev.get("customFields") or {}).get("underserved_types") or [])
        mlh_url = MLH_BASE + ev["url"] if str(ev.get("url") or "").startswith("/") else ev.get("url")
        starts, ends = _iso_date(ev.get("startsAt")), _iso_date(ev.get("endsAt"))
        name = str(ev["name"]).strip()
        return _rec("mlh", ext, ev.get("websiteUrl") or mlh_url or f"{MLH_BASE}/events/{ext}", {
            "board": "mlh", "org": name, "title": name, "location": location, "offices": [],
            "content_html": _html([("Dates", f"{starts} to {ends}" if starts else None),("Format", mode or ev.get("formatType")),
                                   ("Location", location), ("Region", ev.get("region")),
                                   ("Focus", ", ".join(focus)), ("Diversity focus", ", ".join(diversity)),
                                   ("MLH page", mlh_url)], lead=f"MLH {self.season} season hackathon."),
            "departments": focus[:3], "updated_at": None, "first_published": None,
            "track": "hackathon", "opp_type": "hackathon", "deadline": starts, "prize": None, "mode": mode,
            "starts_at": starts, "ends_at": ends, "via": "MLH"})


class KaggleCollector(_FilteringCollector):
    name = "kaggle"

    def __init__(self, token: str | None = None, client: httpx.Client | None = None, max_pages: int = 10,
                 delay_s: float = 1.0, sleep=time.sleep, today: dt.date | None = None) -> None:
        super().__init__(today)
        self._token = token if token is not None else config.load().kaggle_api_token
        self._client = client or polite_client()
        if self._token:
            self._client.headers["Authorization"] = f"Bearer {self._token}"
        self._max_pages, self._delay_s, self._sleep = max_pages, delay_s, sleep

    def collect(self) -> Iterator[RawRecord]:
        if not self._token:
            self._fail("auth", RuntimeError("KAGGLE_API_TOKEN not set"))
            return
        seen: set[str] = set()
        for page in range(1, self._max_pages + 1):
            if page > 1:
                self._sleep(self._delay_s)
            try:
                data = get_json(self._client, f"{KAGGLE_LIST}?page={page}", sleep=self._sleep)
                if not isinstance(data, list):
                    raise ValueError(f"expected a list, got {type(data).__name__}")
            except Exception as exc:
                self._fail(f"page-{page}", exc)
                break
            self.report.units_ok += 1
            self.report.ok_units.append(f"page-{page}")
            for c in data:
                ext = str(c.get("id") or c.get("ref") or "")
                if not ext or ext in seen or c.get("category") in KAGGLE_SKIP_CATEGORIES:
                    continue
                seen.add(ext)
                rec = self._to_record(c, ext)
                if self._keep(rec.payload):
                    self.report.records += 1
                    yield rec
            if len(data) < KAGGLE_PAGE_SIZE:
                break

    @staticmethod
    def _to_record(c: dict, ext: str) -> RawRecord:
        final = _iso_date(c.get("deadline"))
        entry = _iso_date(c.get("newEntrantDeadline")) or final
        reward = " ".join(str(c.get("reward") or "").split())
        prize = None if reward.lower() in NO_PRIZE else re.sub(r"\bUsd\b", "USD", reward)
        tags = [t.get("name") for t in c.get("tags") or [] if isinstance(t, dict) and t.get("name")]
        url = c.get("url") or f"https://www.kaggle.com/competitions/{ext}"
        org = c.get("organizationName") or c.get("hostName") or "Kaggle"
        return _rec("kaggle", ext, url, {
            "board": "kaggle", "org": org, "title": (c.get("title") or "").strip(), "location": "Online",
            "offices": [],
            "content_html": _html([("Category", c.get("category")), ("Reward", reward),
                                   ("Entry deadline", entry), ("Final deadline", final),
                                   ("Max team size", c.get("maxTeamSize")),
                                   ("Metric", c.get("evaluationMetric")),
                                   ("Notebook-only submissions", c.get("isKernelsSubmissionsOnly")),
                                   ("Tags", ", ".join(tags[:6]))], lead=c.get("description") or ""),
            "departments": tags[:3], "updated_at": None, "first_published": c.get("enabledDate"),
            "track": "hackathon", "opp_type": "competition", "deadline": entry, "prize": prize,
            "mode": "online", "final_deadline": final, "category": c.get("category"), "via": "Kaggle"})
