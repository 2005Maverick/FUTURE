"""Company board registry (S03.02): discover ATS board slugs from the Common Crawl
URL index, validate each against its public API, and keep the boards that have
relevant roles Pranav can take (India-located or India-compatible remote).

Weekly stage. The daily collectors read manual seeds ∪ registry-selected boards,
so the daily run stays fast while discovery keeps widening.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

from future.collectors.base import SEEDS_DIR, polite_client
from future.pipeline.location import parse_location
from future.pipeline.relevance import role_relevance

CDX = "https://index.commoncrawl.org/{crawl}-index"
REGISTRY_FILE = SEEDS_DIR / "registry.json"
URL_PATTERNS = {
    "ashby": ["jobs.ashbyhq.com/*"],
    "lever": ["jobs.lever.co/*"],
    "greenhouse": ["job-boards.greenhouse.io/*", "boards.greenhouse.io/*"],
    "workable": ["apply.workable.com/*"],
}
RESERVED = {"api", "j", "embed", "v1", "v0", "jobs", "careers", "static", "assets", "favicon.ico", "robots.txt", ""}
SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
LIST_API = {
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}",
}


def slug_from_url(ats: str, url: str) -> str | None:
    parts = urlsplit(url if "://" in url else f"https://{url}")
    if ats == "greenhouse" and parts.path.startswith("/embed/"):
        slug = (parse_qs(parts.query).get("for") or [""])[0]
    else:
        segs = [s for s in parts.path.split("/") if s]
        slug = segs[0] if segs else ""
    slug = slug.lower()
    return slug if slug not in RESERVED and SLUG_OK.match(slug) else None


def _get_text(client: httpx.Client, url: str, params: dict, retries: int = 4, sleep=time.sleep) -> str:
    for attempt in range(retries + 1):
        try:
            r = client.get(url, params=params)
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r.text
        except httpx.TransportError:
            pass
        sleep(2 * (2 ** attempt))
    raise RuntimeError(f"CDX unavailable: {url} {params}")


def harvest_slugs(ats: str, crawls: list[str], client: httpx.Client, sleep=time.sleep) -> set[str]:
    slugs: set[str] = set()
    for crawl in crawls:
        for pat in URL_PATTERNS[ats]:
            base = CDX.format(crawl=crawl)
            try:
                pages = json.loads(_get_text(client, base, {"url": pat, "output": "json", "showNumPages": "true"},
                                             sleep=sleep)).get("pages", 0)
                for page in range(pages):
                    text = _get_text(client, base, {"url": pat, "output": "json", "fl": "url", "page": page},
                                     sleep=sleep)
                    for line in text.splitlines():
                        try:
                            s = slug_from_url(ats, json.loads(line)["url"])
                        except (json.JSONDecodeError, KeyError):
                            continue
                        if s:
                            slugs.add(s)
                    sleep(1.0)
            except RuntimeError:
                continue   # one crawl/pattern unavailable: keep what we have
    return slugs


@dataclass
class BoardStats:
    ats: str
    slug: str
    jobs: int
    relevant: int
    relevant_india_ok: int
    checked_at: str
    error: str | None = None


def _jobs_of(ats: str, data) -> list[tuple[str, str]]:
    """(title, location) pairs from each ATS list API."""
    if ats == "ashby":
        return [(j.get("title") or "", (j.get("location") or "") + (" Remote" if j.get("isRemote") else ""))
                for j in data.get("jobs", [])]
    if ats == "lever":
        return [(p.get("text") or "", " ".join((p.get("categories") or {}).get("allLocations") or [])
                 + (" Remote" if (p.get("workplaceType") or "") == "remote" else "")) for p in data]
    if ats == "greenhouse":
        return [(j.get("title") or "", (j.get("location") or {}).get("name") or "") for j in data.get("jobs", [])]
    return [(j.get("title") or "", f"{j.get('city') or ''} {j.get('country') or ''}"
             + (" Remote" if str(j.get("telecommuting")).lower() == "true" else "")) for j in data.get("jobs", [])]


def validate(ats: str, slug: str, client: httpx.Client) -> BoardStats:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    try:
        r = client.get(LIST_API[ats].format(slug=slug))
        if r.status_code != 200:
            return BoardStats(ats, slug, 0, 0, 0, now, f"http {r.status_code}")
        jobs = _jobs_of(ats, r.json())
    except Exception as exc:
        return BoardStats(ats, slug, 0, 0, 0, now, type(exc).__name__)
    relevant = [(t, loc) for t, loc in jobs if role_relevance(t) == "relevant"]
    india_ok = 0
    for _, loc in relevant:
        p = parse_location(loc)
        if p.in_india or p.remote_scope in ("india_ok", "unspecified"):
            india_ok += 1
    return BoardStats(ats, slug, len(jobs), len(relevant), india_ok, now)


def validate_all(pairs: list[tuple[str, str]], client: httpx.Client, workers: int = 4) -> list[BoardStats]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda p: validate(p[0], p[1], client), pairs))


# First live harvest (2026-10-12): the top boards by raw count were data-labelling gig
# platforms and staffing aggregators (Prolific 3,931 jobs, Innodata, "agency") that would
# flood the queue. Huge boards are therefore excluded from AUTO-selection (add by hand if
# wanted), and auto-picks are capped so the daily run stays fast.
MAX_BOARD_JOBS = 1500
MAX_SELECTED = 300


def selected(stats: list[BoardStats], min_relevant_india_ok: int = 1, max_jobs: int = MAX_BOARD_JOBS,
             cap: int = MAX_SELECTED) -> dict[str, list[str]]:
    eligible = [s for s in stats if s.error is None and s.relevant_india_ok >= min_relevant_india_ok
                and s.jobs <= max_jobs]
    eligible.sort(key=lambda s: (-s.relevant_india_ok, s.ats, s.slug))
    out: dict[str, list[str]] = {}
    for s in eligible[:cap]:
        out.setdefault(s.ats, []).append(s.slug)
    return {k: sorted(v) for k, v in out.items()}


def manual_seeds(ats: str) -> set[str]:
    seed_file = SEEDS_DIR / f"{ats}.txt"
    if not seed_file.exists():
        return set()
    return {ln.strip() for ln in seed_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")}


def reselect_from_saved(path: Path = REGISTRY_FILE) -> dict[str, int]:
    """Re-apply the selection rules to the last harvest without re-harvesting."""
    data = json.loads(path.read_text(encoding="utf-8"))
    stats = [BoardStats(**b) for b in data["boards"]]
    save_registry(stats, path)
    return {k: len(v) for k, v in selected(stats).items()}


def save_registry(stats: list[BoardStats], path: Path = REGISTRY_FILE) -> None:
    payload = {"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "selected": selected(stats), "boards": [asdict(s) for s in stats]}
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")


def seeds_for(ats: str, path: Path = REGISTRY_FILE) -> list[str]:
    """Manual seeds ∪ registry-selected boards, order-preserving, no duplicates."""
    seed_file = SEEDS_DIR / f"{ats}.txt"
    manual = [ln.strip() for ln in seed_file.read_text(encoding="utf-8").splitlines()
              if ln.strip() and not ln.lstrip().startswith("#")] if seed_file.exists() else []
    auto = json.loads(path.read_text(encoding="utf-8")).get("selected", {}).get(ats, []) if path.exists() else []
    return list(dict.fromkeys(manual + auto))
