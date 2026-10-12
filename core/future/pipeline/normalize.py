"""Raw collector payloads → canonical opportunity records (DESIGN §3), with
dedup keys that merge the same role posted several times."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from future.pipeline.eligibility import Eligibility, check_job
from future.pipeline.location import ParsedLocation, parse_location

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t\r\f\v]+")
BLANKS = re.compile(r"\n\s*\n+")
MAX_DESC = 12_000

ORG_NAMES = {"scaleai": "Scale AI", "togetherai": "Together AI", "stabilityai": "Stability AI",
             "mongodb": "MongoDB", "gitlab": "GitLab", "openai": "OpenAI", "elevenlabs": "ElevenLabs",
             "huggingface": "Hugging Face", "langchain": "LangChain", "physicalintelligence": "Physical Intelligence",
             "sarvam": "Sarvam AI", "cred": "CRED", "cursor": "Cursor (Anysphere)", "lightning": "Lightning AI",
             "deepgram": "Deepgram", "baseten": "Baseten"}


def html_to_text(raw: str) -> str:
    text = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", raw or "")
    text = html.unescape(TAG.sub(" ", text))
    text = WS.sub(" ", text)
    return BLANKS.sub("\n\n", "\n".join(line.strip() for line in text.splitlines())).strip()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def norm_title(title: str) -> str:
    t = re.sub(r"\(.*?\)|[-–—,|/]+", " ", title.lower())
    return re.sub(r"\s+", " ", t).strip()


def job_type(title: str) -> str:
    t = title.lower()
    if re.search(r"\bintern(ship)?\b", t):
        return "internship"
    if re.search(r"\bfellow(ship)?s?\b", t):
        return "fellowship"
    if re.search(r"\bcontract(or)?\b|\bfreelance\b", t):
        return "contract"
    return "job"


def location_bucket(loc: ParsedLocation) -> str:
    if loc.in_india:
        return "IN"
    if loc.remote and loc.remote_scope in ("india_ok", "unspecified"):
        return "REMOTE"
    return ",".join(sorted(loc.countries)) or "UNKNOWN"


@dataclass
class Opportunity:
    type: str
    track: str
    title: str
    org: str
    url: str
    canonical_url: str
    dedup_key: str
    location: str
    remote: str
    countries: list[str]
    description: str
    eligibility: Eligibility
    raw_hashes: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "skipped" if self.eligibility.result == "fail" else "verified"


def from_ats(raw: dict[str, Any]) -> Opportunity:
    """Any ATS collector's common payload (Greenhouse, Ashby, Lever, Workable) → Opportunity."""
    return from_greenhouse(raw)


def from_greenhouse(raw: dict[str, Any]) -> Opportunity:
    p = raw["payload"]
    org = p.get("org") or ORG_NAMES.get(p["board"], p["board"].replace("-", " ").title())
    loc = parse_location(p.get("location", ""), *p.get("offices", []))
    text = html_to_text(p.get("content_html", ""))[:MAX_DESC]
    elig = check_job(p["title"], loc, text)
    key_src = f"{org.lower()}|{norm_title(p['title'])}|{location_bucket(loc)}"
    return Opportunity(
        type=job_type(p["title"]), track="job", title=p["title"], org=org, url=raw["url"],
        canonical_url=canonical_url(raw["url"]),
        dedup_key=hashlib.sha1(key_src.encode("utf-8")).hexdigest(),
        location=loc.raw, remote="remote" if loc.remote else ("onsite" if loc.countries else "unknown"),
        countries=sorted(loc.countries), description=text, eligibility=elig,
        raw_hashes=[raw["content_hash"]],
        details={"departments": p.get("departments", []), "remote_scope": loc.remote_scope,
                 "first_published": p.get("first_published")},
    )


def dedupe(opps: list[Opportunity]) -> list[Opportunity]:
    """Merge records sharing a dedup key: keep the first, union locations and raw hashes."""
    merged: dict[str, Opportunity] = {}
    for o in opps:
        if o.dedup_key not in merged:
            merged[o.dedup_key] = o
            continue
        keep = merged[o.dedup_key]
        keep.raw_hashes.extend(h for h in o.raw_hashes if h not in keep.raw_hashes)
        if o.location and o.location not in keep.location:
            keep.location = f"{keep.location} | {o.location}"
        keep.details.setdefault("alt_urls", []).append(o.url)
    return list(merged.values())
