"""Feed-presence liveness (S03.04).

Full-feed sources (Greenhouse, Ashby, Lever, Workable) return a board's COMPLETE
list of open jobs on every fetch. So an open opportunity that is missing from
today's feed of a board that was fetched successfully today has been closed.
Safety rule: never expire anything from a board (or source) that failed today —
a network error must not look like a closed posting.

Search-style sources (Himalayas, Remotive) return query-dependent subsets, so
absence proves nothing; those age out instead (`stale_after_days`).
"""
from __future__ import annotations

import datetime as dt

FULL_FEED_SOURCES = {"greenhouse", "ashby", "lever", "workable"}
OPEN_STATUSES = ("found", "verified", "scored", "shortlisted")


def expired_keys(open_rows: list[dict], seen_keys: set[str], ok_boards: dict[str, set[str]],
                 today: dt.date, stale_after_days: int = 21) -> list[tuple[str, str]]:
    """Return (opp_id, reason) for open opportunities that should be marked expired."""
    out = []
    for row in open_rows:
        if row["dedup_key"] in seen_keys:
            continue
        details = row.get("details") or {}
        source, board = details.get("source"), details.get("board")
        if source in FULL_FEED_SOURCES:
            if board in ok_boards.get(source, set()):
                out.append((row["id"], f"no longer listed on {source}/{board}"))
        else:
            last = (row.get("last_seen_at") or "")[:10]
            if last and (today - dt.date.fromisoformat(last)).days > stale_after_days:
                out.append((row["id"], f"not seen for >{stale_after_days} days on {source}"))
    return out
