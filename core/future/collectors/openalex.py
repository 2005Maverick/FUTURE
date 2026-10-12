"""OpenAlex research-lab collector (S05.01): topic -> recent works -> authors ->
current institution -> one `lab_outreach` record per active researcher.

API facts (verified live 2026-10-13 against help.openalex.org and api.openalex.org):
- Works search: `search.title_abstract_keywords=<terms>` (title + abstract + keywords,
  stemmed; bare words AND together, "double quotes" make a phrase). Year window:
  `filter=publication_year:2025-2026`. Sort `relevance_score:desc` (needs a search).
- Auth: `Authorization: Bearer <key>` (documented as equivalent to `?api_key=`). The
  header keeps the key out of URLs, so it can never reach httpx's request log or an
  error string.
- Metered: each response reports `meta.cost_usd`. Search = $0.001/call, list/filter =
  $0.0001/call; free key budget is $1/day. per_page max 100 (cost is per call).
- Authors batch: `/authors?filter=ids.openalex:A1|A2|...` gives last_known_institutions
  and summary_stats.h_index for up to `author_batch` authors per (cheap) call.

Payload shape matches the other collectors ({board, org, title, location, offices,
content_html, departments, updated_at, first_published}) plus track/opp_type/works.
`content_html` holds PLAIN TEXT. Fetched metadata is data, never instructions.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

import httpx

from future.collectors.base import USER_AGENT, CollectorReport, RawRecord, content_hash, get_json

log = logging.getLogger(__name__)

SOURCE = "openalex"
WORKS_URL = "https://api.openalex.org/works"
AUTHORS_URL = "https://api.openalex.org/authors"
WORK_FIELDS = "id,title,publication_year,cited_by_count,authorships,primary_location"
AUTHOR_FIELDS = "id,display_name,orcid,last_known_institutions,summary_stats,works_count"
DEFAULT_TOPICS = [
    "vision-language models robotics",
    "embodied AI",
    "LLM evaluation",
    "multimodal medical imaging",
    "adversarial robustness deep learning",
    "robot learning foundation models",
    "trustworthy machine learning",
    "LLM alignment",
]
MAX_REQUESTS = 40            # hard cap per run (searches + author lookups)
MAX_COST_USD = 0.10          # stop early if the metered cost reaches this
ENRICH_RESERVE = 6           # requests kept back for author lookups (6 x 50 = 300 authors)
TOP_PAPERS = 3
VOLATILE = ("content_html", "h_index", "author_works_count", "updated_at")
COUNTRY_NAMES = {
    "IN": "India", "US": "United States", "GB": "United Kingdom", "CA": "Canada", "DE": "Germany",
    "FR": "France", "CH": "Switzerland", "NL": "Netherlands", "SG": "Singapore", "JP": "Japan",
    "KR": "South Korea", "CN": "China", "HK": "Hong Kong", "TW": "Taiwan", "AU": "Australia",
    "IT": "Italy", "ES": "Spain", "SE": "Sweden", "DK": "Denmark", "FI": "Finland", "NO": "Norway",
    "BE": "Belgium", "AT": "Austria", "IE": "Ireland", "IL": "Israel", "AE": "UAE", "SA": "Saudi Arabia",
    "QA": "Qatar", "PL": "Poland", "PT": "Portugal", "CZ": "Czech Republic", "BR": "Brazil",
    "NZ": "New Zealand", "MO": "Macao", "LU": "Luxembourg", "GR": "Greece", "TR": "Turkey",
    "IS": "Iceland", "RO": "Romania", "EE": "Estonia", "HU": "Hungary", "SI": "Slovenia", "HR": "Croatia",
    "SK": "Slovakia", "LT": "Lithuania", "LV": "Latvia", "UA": "Ukraine", "RU": "Russia", "CY": "Cyprus",
    "MT": "Malta", "MY": "Malaysia", "TH": "Thailand", "VN": "Vietnam", "ID": "Indonesia", "PH": "Philippines",
    "PK": "Pakistan", "BD": "Bangladesh", "LK": "Sri Lanka", "NP": "Nepal", "IR": "Iran", "EG": "Egypt",
    "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya", "MX": "Mexico", "CL": "Chile", "AR": "Argentina",
    "CO": "Colombia", "JO": "Jordan", "OM": "Oman", "KW": "Kuwait", "BH": "Bahrain", "MA": "Morocco",
    "TN": "Tunisia",
}


@dataclass(frozen=True)
class Paper:
    work_id: str
    title: str
    year: int | None
    venue: str | None
    cited_by: int


@dataclass(frozen=True)
class Institution:
    id: str
    name: str
    country_code: str | None
    lineage: frozenset[str]


@dataclass
class AuthorAgg:
    """Per-author accumulator (local to one aggregation pass)."""
    author_id: str
    name: str
    orcid: str | None
    papers: dict[str, Paper] = field(default_factory=dict)
    topics: Counter = field(default_factory=Counter)
    institutions: Counter = field(default_factory=Counter)      # Institution -> matching works there


def _short_id(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def _institution(raw: dict) -> Institution | None:
    if not raw.get("id") or not raw.get("display_name"):
        return None
    lineage = frozenset(raw.get("lineage") or []) | {raw["id"]}
    return Institution(raw["id"], raw["display_name"], raw.get("country_code"), lineage)


def _paper(work: dict) -> Paper:
    source = ((work.get("primary_location") or {}).get("source") or {})
    return Paper(work["id"], (work.get("title") or "").strip(), work.get("publication_year"),
                 source.get("display_name"), int(work.get("cited_by_count") or 0))


def _paper_key(paper: Paper) -> str:
    """Versions of one paper (arXiv preprint + journal copy, dash/case variants) are
    separate OpenAlex works; key on the normalised title so they count once."""
    norm = "".join(ch for ch in paper.title.casefold() if ch.isalnum())
    return norm or paper.work_id


def aggregate(hits: list[tuple[str, dict]], max_authors_per_work: int = 20) -> dict[str, AuthorAgg]:
    """Group (topic, work) hits by author. A paper found by several topics, or in
    several versions, counts once per author but adds every topic. Works with huge
    author lists are skipped: one of 40 names on a survey says nothing about a lab."""
    authors: dict[str, AuthorAgg] = {}
    for topic, work in hits:
        ships = work.get("authorships") or []
        if not work.get("id") or len(ships) > max_authors_per_work:
            continue
        paper = _paper(work)
        key = _paper_key(paper)
        for ship in ships:
            who = ship.get("author") or {}
            if not who.get("id"):
                continue
            agg = authors.setdefault(who["id"], AuthorAgg(who["id"], who.get("display_name") or "", who.get("orcid")))
            first_time = key not in agg.papers
            if first_time or paper.cited_by > agg.papers[key].cited_by:
                agg.papers[key] = paper                  # keep the most-cited version
            agg.topics[topic] += 1
            if first_time:
                for inst in filter(None, (_institution(i) for i in ship.get("institutions") or [])):
                    agg.institutions[inst] += 1
    return authors


def pick_institution(agg: AuthorAgg, last_known: list[dict] | None) -> Institution | None:
    """Institution to address: a last-known institution that matches the matching works'
    affiliations (by lineage). If none matches, the 2025-26 works' own most frequent
    affiliation wins: a mismatch there usually means a merged OpenAlex profile (live run
    2026-10-13: a VLM-robotics author shown at an oil company), not a move. Last-known
    is used alone only when the works carry no affiliation. An author looked up with NO
    last-known institution is dropped; without a lookup (skipped/failed) the works'
    affiliation is used."""
    current = [i for i in (_institution(r) for r in last_known or []) if i]
    from_works = agg.institutions.most_common(1)[0][0] if agg.institutions else None
    if current:
        seen = set().union(*(i.lineage for i in agg.institutions)) if agg.institutions else set()
        return next((i for i in current if i.lineage & seen), from_works or current[0])
    if last_known is not None:
        return None
    return from_works


def _top_papers(agg: AuthorAgg) -> list[Paper]:
    return sorted(agg.papers.values(), key=lambda p: (-p.cited_by, -(p.year or 0), p.title))[:TOP_PAPERS]


def _summary_text(agg: AuthorAgg, inst: Institution, country: str, topics: list[str],
                  stats: dict, top: list[Paper]) -> str:
    lines = [f"Researcher: {agg.name}" + (f" (ORCID {agg.orcid})" if agg.orcid else ""),
             f"Institution: {inst.name}, {country}",
             f"OpenAlex: {agg.author_id}"
             + (f"; h-index {stats['h_index']}" if stats.get("h_index") is not None else "")
             + (f"; {stats['works_count']} works total" if stats.get("works_count") is not None else ""),
             f"Matching recent works: {len(agg.papers)} on {', '.join(topics)}",
             "Top matching papers:"]
    lines += [f"- {p.title} ({p.year or 'n.d.'}" + (f", {p.venue}" if p.venue else "") + f", {p.cited_by} citations)"
              for p in top]
    lines.append("Source: OpenAlex (CC0).")
    return "\n".join(lines)


def to_record(agg: AuthorAgg, inst: Institution, stats: dict, topic_order: list[str]) -> RawRecord:
    topics = sorted(agg.topics, key=lambda t: (-agg.topics[t], topic_order.index(t) if t in topic_order else 99))
    country = COUNTRY_NAMES.get(inst.country_code or "", inst.country_code or "Unknown")
    top = _top_papers(agg)
    ext = _short_id(agg.author_id)
    fields: dict[str, Any] = {
        "board": SOURCE, "org": inst.name,
        "title": f"Research outreach: {agg.name} — {topics[0]}",
        "location": country, "offices": [],
        "content_html": _summary_text(agg, inst, country, topics, stats, top),
        "departments": topics, "updated_at": None, "first_published": None,
        "track": "research", "opp_type": "lab_outreach", "works": len(agg.papers),
        "author_name": agg.name, "author_id": ext, "orcid": agg.orcid,
        "institution_id": _short_id(inst.id), "country_code": inst.country_code,
        "h_index": stats.get("h_index"), "author_works_count": stats.get("works_count"),
        "top_papers": [{"id": _short_id(p.work_id), "title": p.title, "year": p.year, "venue": p.venue}
                       for p in top],
        "via": "OpenAlex",
    }
    stable = {k: v for k, v in fields.items() if k not in VOLATILE}
    return RawRecord(SOURCE, ext, agg.orcid or agg.author_id, fields, content_hash(SOURCE, ext, stable))


def _default_api_key() -> str | None:
    from future import config   # lazy: config loads .env on import
    return config.load().openalex_api_key


class OpenAlexLabCollector:
    name = SOURCE

    def __init__(self, topics: list[str] | None = None, api_key: str | None = None,
                 transport: httpx.BaseTransport | None = None, years: tuple[int, int] | None = None,
                 pages_per_topic: int = 2, per_page: int = 100, min_works: int = 2,
                 max_requests: int = MAX_REQUESTS, max_cost_usd: float = MAX_COST_USD,
                 enrich: bool = True, author_batch: int = 50, max_authors_per_work: int = 20,
                 sort: str = "relevance_score:desc", delay_s: float = 0.5,
                 sleep: Callable[[float], None] = time.sleep, today: Callable[[], dt.date] = dt.date.today) -> None:
        self.topics = list(topics or DEFAULT_TOPICS)
        key = api_key if api_key is not None else _default_api_key()
        headers = {"User-Agent": USER_AGENT} | ({"Authorization": f"Bearer {key}"} if key else {})
        self._client = httpx.Client(timeout=30, headers=headers, follow_redirects=True, transport=transport)
        year = today().year
        self.years = years or (year - 1, year)
        self.pages_per_topic, self.per_page, self.min_works = pages_per_topic, min(per_page, 100), min_works
        self.max_requests, self.max_cost_usd = max_requests, max_cost_usd
        self.enrich, self.author_batch, self.max_authors_per_work = enrich, author_batch, max_authors_per_work
        self.sort, self._delay_s, self._sleep = sort, delay_s, sleep
        self.report = CollectorReport(source=self.name)
        self.requests, self.cost_usd = 0, 0.0
        self.stats: dict[str, int] = {}
        self._author_stats: dict[str, dict] = {}
        if not key:
            self.report.errors.append("no OPENALEX_API_KEY: running keyless (small daily budget)")

    # ---- metered HTTP -------------------------------------------------------
    def _budget_left(self, reserve: int = 0) -> bool:
        return self.requests < self.max_requests - reserve and self.cost_usd < self.max_cost_usd

    def _get(self, url: str, params: dict[str, str], label: str) -> dict | None:
        if self.requests:
            self._sleep(self._delay_s)
        self.requests += 1
        try:
            data = get_json(self._client, str(httpx.URL(url, params=params)), retries=1, sleep=self._sleep)
        except Exception as exc:     # recorded, never raised: one bad call must not sink the run
            status = getattr(getattr(exc, "response", None), "status_code", None)
            self.report.units_failed += 1
            self.report.errors.append(f"{label}: {type(exc).__name__}" + (f" {status}" if status else ""))
            return None
        cost = float((data.get("meta") or {}).get("cost_usd") or 0)
        self.cost_usd += cost
        self.report.units_ok += 1
        log.info("openalex %s cost_usd=%.4f total=%.4f", label, cost, self.cost_usd)
        return data

    def works_params(self, topic: str, page: int) -> dict[str, str]:
        return {"search.title_abstract_keywords": topic,
                "filter": f"publication_year:{self.years[0]}-{self.years[1]}",
                "sort": self.sort, "per_page": str(self.per_page), "page": str(page), "select": WORK_FIELDS}

    # ---- stages -------------------------------------------------------------
    def _search(self) -> list[tuple[str, dict]]:
        reserve = ENRICH_RESERVE if self.enrich else 0
        hits: list[tuple[str, dict]] = []
        for topic in self.topics:
            for page in range(1, self.pages_per_topic + 1):
                if not self._budget_left(reserve):
                    self.report.errors.append(f"budget reached before {topic!r} p{page}")
                    return hits
                data = self._get(WORKS_URL, self.works_params(topic, page), f"{topic!r} p{page}")
                if data is None:
                    break
                results = data.get("results") or []
                hits.extend((topic, w) for w in results)
                if len(results) < self.per_page:
                    break
        return hits

    def _lookup_authors(self, author_ids: list[str]) -> dict[str, list[dict] | None]:
        """author id -> last_known_institutions (list, maybe empty). Missing key = not looked up."""
        found: dict[str, list[dict] | None] = {}
        for i in range(0, len(author_ids), self.author_batch):
            if not self._budget_left():
                self.report.errors.append("budget reached during author lookup")
                break
            batch = author_ids[i:i + self.author_batch]
            params = {"filter": "ids.openalex:" + "|".join(_short_id(a) for a in batch),
                      "per_page": str(len(batch)), "select": AUTHOR_FIELDS}
            data = self._get(AUTHORS_URL, params, f"authors {i // self.author_batch + 1}")
            if data is None:
                continue
            for a in data.get("results") or []:
                found[a["id"]] = a.get("last_known_institutions") or []
                self._author_stats[a["id"]] = {"h_index": (a.get("summary_stats") or {}).get("h_index"),
                                               "works_count": a.get("works_count")}
        return found

    def collect(self) -> Iterator[RawRecord]:
        hits = self._search()
        authors = aggregate(hits, self.max_authors_per_work)
        keep = sorted((a for a in authors.values() if len(a.papers) >= self.min_works),
                      key=lambda a: (-len(a.papers), a.name))
        current = self._lookup_authors([a.author_id for a in keep]) if self.enrich and keep else {}
        self.stats = {"works_seen": len({w.get("id") for _, w in hits}), "authors_seen": len(authors),
                      "candidates": len(keep), "no_institution": 0}
        for agg in keep:
            inst = pick_institution(agg, current.get(agg.author_id))
            if inst is None:
                self.stats["no_institution"] += 1
                continue
            self.report.records += 1
            yield to_record(agg, inst, self._author_stats.get(agg.author_id, {}), self.topics)
        log.info("openalex run: %d requests, cost_usd=%.4f, %d records", self.requests, self.cost_usd,
                 self.report.records)
