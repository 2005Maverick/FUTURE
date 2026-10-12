"""Deterministic priority (DESIGN §3): deadline × fit × value × referral, with a
visible per-component breakdown so the dashboard can say WHY an item ranks.

Weights are PROVISIONAL (no labels yet). They are recalibrated from Pranav's
labels after E-03 (S03.07) — do not tune them by intuition beyond that.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

WEIGHTS = {"fit": 0.40, "value": 0.25, "urgency": 0.20, "referral": 0.10, "freshness": 0.05}
URGENCY_HORIZON_DAYS = 30   # deadlines further out than this add no urgency


@dataclass(frozen=True)
class RankInput:
    fit: int                       # 1–5 from the Evaluator
    value: int                     # 1–5 from the Evaluator
    recommendation: str            # apply | maybe | skip
    deadline: dt.date | None = None
    referral_strength: int = 0     # 0 = none, 1–5 from referral_matches
    first_seen: dt.date | None = None


@dataclass(frozen=True)
class Rank:
    priority: float                # 0–100
    components: dict[str, float]   # each 0–1 before weighting
    expired: bool


def urgency(deadline: dt.date | None, today: dt.date) -> tuple[float, bool]:
    if deadline is None:
        return 0.3, False          # unknown deadline: modest, never zero (rolling roles still matter)
    days = (deadline - today).days
    if days < 0:
        return 0.0, True
    return max(0.0, 1.0 - days / URGENCY_HORIZON_DAYS), False


def freshness(first_seen: dt.date | None, today: dt.date) -> float:
    if first_seen is None:
        return 0.5
    return max(0.0, 1.0 - (today - first_seen).days / 14)


def rank(item: RankInput, today: dt.date) -> Rank:
    urg, expired = urgency(item.deadline, today)
    comps = {
        "fit": (item.fit - 1) / 4,
        "value": (item.value - 1) / 4,
        "urgency": urg,
        "referral": item.referral_strength / 5,
        "freshness": freshness(item.first_seen, today),
    }
    score = 100 * sum(WEIGHTS[k] * v for k, v in comps.items())
    if item.recommendation == "skip" or expired:
        score = 0.0
    elif item.recommendation == "maybe":
        score *= 0.75              # keep 'maybe' below an equal 'apply'
    return Rank(priority=round(score, 1), components={k: round(v, 3) for k, v in comps.items()}, expired=expired)
