"""Non-job tracks → Opportunity (S05): hackathons/competitions, opportunities the
Extractor pulled from watched pages, and lab-outreach targets from OpenAlex.

Eligibility here is deterministic and conservative: only clear-cut cases fail
(in-person abroad, deadline passed, likely-student "lab"); everything uncertain
is `unclear` so a human or a later evaluator decides.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from future.pipeline.eligibility import Eligibility
from future.pipeline.location import parse_location
from future.pipeline.normalize import MAX_DESC, Opportunity, canonical_url, html_to_text, norm_title

TRACK_TYPES = {
    "hackathon": {"hackathon", "competition"},
    "research": {"research_internship", "predoc", "lab_outreach", "fellowship", "scholarship", "travel_grant"},
    "ms": {"ms_program", "scholarship", "fellowship"},
    "funding": {"grant", "accelerator", "fellowship", "credits"},
}
KIND_TYPES = {"scholarship": "scholarship", "fellowship": "fellowship", "accelerator": "accelerator",
              "grant": "grant"}
PROGRAMME_TYPE = {"research": "research_internship", "ms": "ms_program", "funding": "accelerator",
                  "hackathon": "hackathon"}
MIN_LAB_H_INDEX = 10   # below this an OpenAlex "lab" is usually a student co-author (S05.03 live run)


def _key(*parts: str) -> str:
    return hashlib.sha1("|".join(p.lower() for p in parts).encode("utf-8")).hexdigest()


def _deadline_check(elig: Eligibility, deadline: str | None, today: dt.date | None) -> None:
    if deadline and today:
        try:
            if dt.date.fromisoformat(deadline) < today:
                elig.fail(f"deadline passed ({deadline})")
        except ValueError:
            elig.unclear(f"unreadable deadline {deadline!r}")


def from_hackathon(raw: dict[str, Any], today: dt.date | None = None) -> Opportunity:
    p = raw["payload"]
    mode = p.get("mode") or "unknown"
    loc = parse_location(p.get("location", ""))
    elig = Eligibility()
    if mode == "online":
        elig.reasons.append("online")
    elif loc.in_india:
        elig.reasons.append(f"{mode} in India")
    elif mode == "in-person":
        elig.fail(f"in-person outside India ({p.get('location') or 'unknown'})")
    else:
        elig.unclear(f"{mode} event outside India; check whether online participation is allowed")
    _deadline_check(elig, p.get("deadline"), today)
    opp_type = p.get("opp_type") if p.get("opp_type") in TRACK_TYPES["hackathon"] else "hackathon"
    return Opportunity(
        type=opp_type, track="hackathon", title=p["title"], org=p.get("org") or p["title"], url=raw["url"],
        canonical_url=canonical_url(raw["url"]), dedup_key=_key("hackathon", raw["source"], norm_title(p["title"])),
        location=loc.raw, remote="remote" if mode == "online" else ("onsite" if loc.countries else "unknown"),
        countries=sorted(loc.countries), description=html_to_text(p.get("content_html", ""))[:MAX_DESC],
        eligibility=elig, raw_hashes=[raw["content_hash"]], deadline=p.get("deadline"),
        details={"source": raw["source"], "board": p.get("board"), "mode": mode, "prize": p.get("prize"),
                 "starts_at": p.get("starts_at"), "ends_at": p.get("ends_at"), "via": p.get("via")},
    )


def _type_for(item_type: str, page: dict[str, str]) -> str:
    track = page["track"]
    if item_type in TRACK_TYPES[track]:
        return item_type
    return KIND_TYPES.get(page.get("kind", ""), PROGRAMME_TYPE[track])


def from_extracted(item: dict[str, Any], page: dict[str, str], *, content_hash: str,
                   today: dt.date | None = None) -> Opportunity:
    """One Extractor record from a watched page. Every field was already verified verbatim
    by the Extractor; missing ones stay missing."""
    org = item.get("org") or page["org"]
    url = item.get("url") or page["url"]
    loc = parse_location(item.get("location") or "")
    elig = Eligibility()
    elig.unclear("found on a watched page; eligibility needs a read")
    for note in item.get("eligibility_notes") or []:
        elig.reasons.append(f"note: {note}")
    if item.get("scam_signals"):
        elig.unclear(f"scam signals: {'; '.join(item['scam_signals'])}")
    _deadline_check(elig, item.get("deadline"), today)
    facts = [("Pay", item.get("pay")), ("Location", item.get("location")), ("Deadline", item.get("deadline"))]
    description = "\n".join(f"{k}: {v}" for k, v in facts if v)
    return Opportunity(
        type=_type_for(item.get("type", ""), page), track=page["track"], title=item["title"] or page["org"],
        org=org, url=url, canonical_url=canonical_url(url),
        dedup_key=_key(page["track"], org, norm_title(item["title"] or page["id"])),
        location=loc.raw, remote="remote" if item.get("remote") else ("onsite" if loc.countries else "unknown"),
        countries=sorted(loc.countries), description=description, eligibility=elig,
        raw_hashes=[content_hash], deadline=item.get("deadline"),
        details={"source": "pagewatch", "board": page["id"], "page_url": page["url"], "pay": item.get("pay"),
                 "scam_signals": item.get("scam_signals") or []},
    )


def from_lab(raw: dict[str, Any]) -> Opportunity:
    p = raw["payload"]
    loc = parse_location(p.get("location", ""))
    elig = Eligibility()
    h = p.get("h_index")
    if h is None or h < MIN_LAB_H_INDEX:
        elig.fail(f"h-index {h} below {MIN_LAB_H_INDEX} (likely a student co-author, not a lab head)")
    return Opportunity(
        type="lab_outreach", track="research", title=p["title"], org=p.get("org") or "", url=raw["url"],
        canonical_url=canonical_url(raw["url"]), dedup_key=_key("lab", p.get("author_id") or raw["url"]),
        location=loc.raw, remote="unknown", countries=sorted(loc.countries),
        description=html_to_text(p.get("content_html", ""))[:MAX_DESC], eligibility=elig,
        raw_hashes=[raw["content_hash"]],
        details={"source": "openalex", "board": "openalex", "author_name": p.get("author_name"),
                 "orcid": p.get("orcid"), "h_index": h, "works": p.get("works"),
                 "topics": p.get("departments", []), "top_papers": p.get("top_papers", [])},
    )
