"""Daily digest (DESIGN §6, 09:00): what to act on, what's due, and how the
pipeline did. Plain markdown so it renders on the dashboard, in a Sheet note,
or in chat on the phone."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class DigestItem:
    org: str
    title: str
    location: str
    url: str
    fit: int
    value: int
    recommendation: str
    priority: float
    one_line: str
    deadline: dt.date | None = None
    referral: str | None = None


@dataclass
class DigestStats:
    collected: int = 0
    new: int = 0
    after_dedupe: int = 0
    eligible_pass: int = 0
    eligible_unclear: int = 0
    skipped: int = 0
    evaluated: int = 0
    budget_used: int = 0
    budget_cap: int = 0
    top_skip_reasons: list[tuple[str, int]] = field(default_factory=list)
    source_health: dict[str, str] = field(default_factory=dict)


def _line(i: DigestItem) -> str:
    due = f" · due **{i.deadline.isoformat()}**" if i.deadline else ""
    ref = f" · referral: {i.referral}" if i.referral else ""
    return (f"- **{i.org} — {i.title}** ({i.location[:60]}) · fit {i.fit}/5 · value {i.value}/5{due}{ref}\n"
            f"  {i.one_line}  \n  [{i.url}]({i.url})")


def build(today: dt.date, items: list[DigestItem], stats: DigestStats, top_n: int = 10) -> str:
    ranked = sorted((i for i in items if i.recommendation != "skip"), key=lambda i: -i.priority)
    apply = [i for i in ranked if i.recommendation == "apply"][:top_n]
    maybe = [i for i in ranked if i.recommendation == "maybe"][:top_n]
    soon = sorted((i for i in ranked if i.deadline and 0 <= (i.deadline - today).days <= 14),
                  key=lambda i: i.deadline)
    out = [f"# FUTURE digest — {today.isoformat()}", ""]
    out += ["## Apply (top picks)", *([_line(i) for i in apply] or ["_None today._"]), ""]
    out += ["## Worth a look", *([_line(i) for i in maybe] or ["_None today._"]), ""]
    out += ["## Deadlines in the next 14 days",
            *([f"- {i.deadline.isoformat()} — {i.org}: {i.title}" for i in soon] or ["_None known._"]), ""]
    s = stats
    pct = f"{100 * s.budget_used / s.budget_cap:.0f}%" if s.budget_cap else "n/a"
    out += ["## Pipeline",
            f"- Collected {s.collected} postings ({s.new} new) → {s.after_dedupe} after de-duplication",
            f"- Eligibility: {s.eligible_pass} pass · {s.eligible_unclear} unclear · {s.skipped} skipped",
            f"- Evaluated today: {s.evaluated} · Claude budget used: {s.budget_used:,} / {s.budget_cap:,} tokens ({pct})"]
    if s.top_skip_reasons:
        out.append("- Top skip reasons: " + "; ".join(f"{r} ({n})" for r, n in s.top_skip_reasons[:4]))
    if s.source_health:
        out.append("- Sources: " + ", ".join(f"{k}={v}" for k, v in sorted(s.source_health.items())))
    return "\n".join(out) + "\n"
