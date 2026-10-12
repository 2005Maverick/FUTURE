"""Near-duplicate merging across sources (S03.05).

Exact dedup (normalize.dedupe) already merges identical org/title/region. This
catches the SAME role listed slightly differently — e.g. an OpenAI posting on
Ashby and again on Himalayas ("OpenAI" vs "OpenAI, Inc.", "Applied AI Engineer"
vs "Applied AI Engineer - India").

v1 uses fuzzy string similarity (rapidfuzz) within the same location bucket.
Embedding similarity is the planned upgrade once trijya-3 runs local models (H1).
Threshold 90 on org and 88 on title is PROVISIONAL; tune on the S03.05 audit.
"""
from __future__ import annotations

import re
from collections import defaultdict

from rapidfuzz import fuzz

from future.pipeline.normalize import Opportunity, location_bucket, norm_title
from future.pipeline.location import parse_location

ORG_SUFFIX = re.compile(r"\b(inc|inc\.|llc|ltd|limited|pvt|private|corp|corporation|gmbh|co)\b\.?", re.I)
ORG_MIN, TITLE_MIN = 90, 90


LOCATION_WORDS = re.compile(r"\b(remote|hybrid|on-?site|onsite|india|indian|apac|emea|global|worldwide|"
                            r"bengaluru|bangalore|delhi|new delhi|mumbai|hyderabad|pune|chennai|gurugram|gurgaon|noida|"
                            r"us|usa|uk|london|san francisco|new york|nyc|seattle|toronto|singapore|dublin)\b", re.I)


def core_title(title: str) -> str:
    """Title without location/work-mode words: 'Applied AI Engineer - India (Remote)' → 'applied ai engineer'."""
    return re.sub(r"\s+", " ", LOCATION_WORDS.sub(" ", norm_title(title))).strip()


def norm_org(org: str) -> str:
    return re.sub(r"\s+", " ", ORG_SUFFIX.sub("", (org or "").lower().replace(",", " "))).strip()


def _bucket(o: Opportunity) -> str:
    return location_bucket(parse_location(o.location))


def merge_near_duplicates(opps: list[Opportunity]) -> tuple[list[Opportunity], list[tuple[str, str]]]:
    """Return (kept, merged_pairs[(kept_title, dropped_title)]). Prefers keeping the
    record from a full-feed ATS source (richer text) over a search aggregator."""
    def rank(o: Opportunity) -> int:
        return 0 if (o.details.get("source") in {"greenhouse", "ashby", "lever", "workable"}) else 1

    groups: dict[str, list[Opportunity]] = defaultdict(list)
    for o in sorted(opps, key=rank):
        groups[_bucket(o)].append(o)
    kept: list[Opportunity] = []
    merged: list[tuple[str, str]] = []
    for bucket_opps in groups.values():
        reps: list[Opportunity] = []
        for o in bucket_opps:
            org, title = norm_org(o.org), core_title(o.title)
            # Only ACROSS sources: two postings on one board are distinct jobs (exact dups were
            # merged already). token_sort_ratio compares whole titles; token_set_ratio scored
            # subsets as 100 and falsely merged 1,145 real roles in the S03.05 audit.
            match = next((r for r in reps if r.details.get("source") != o.details.get("source")
                          and fuzz.token_sort_ratio(org, norm_org(r.org)) >= ORG_MIN
                          and fuzz.token_sort_ratio(title, core_title(r.title)) >= TITLE_MIN), None)
            if match is None:
                reps.append(o)
                continue
            match.raw_hashes.extend(h for h in o.raw_hashes if h not in match.raw_hashes)
            match.details.setdefault("alt_urls", []).append(o.url)
            merged.append((f"{match.org}: {match.title}", f"{o.org}: {o.title}"))
        kept.extend(reps)
    return kept, merged
