"""Hard eligibility rules (DESIGN §3), applied before any model spend.

Result is pass / fail / unclear. `fail` must be certain from the posting text;
anything ambiguous is `unclear` and goes to the Evaluator. Reasons are always
recorded so a skipped item can be audited.

Candidate facts encoded here (from the agreed target list, 2026-10-11):
- Indian citizen, based in India; abroad only with visa sponsorship.
- Final-year B.Tech, graduating June 2027 → new-grad / intern level.
- No unpaid work. Excluded categories handled per track elsewhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from future.pipeline.location import ParsedLocation
from future.pipeline.relevance import role_relevance

SENIOR_TITLE = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head of|vp|vice president|"
                          r"chief|distinguished|level\s*[5-9]|l[5-9])\b", re.I)
MID_LEVEL = re.compile(r"\bengineer\s+(iii|iv|3|4)\b|\b(swe|sde)\s*(iii|3)\b", re.I)  # level-3+ ladders
# Only years tied to experience ("5+ years of industry experience", "3-5 yrs' experience");
# "founded 10 years ago" must not count.
YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:(?:-|to)\s*\d{1,2}\s*\+?\s*)?(?:years|yrs)['’]?\s*(?:of\s+)?"
                   r"(?:[\w/-]+\s+){0,4}?experience", re.I)
# Short form seen live on Cloudflare postings: "Exp: 3-15yrs", "Exp : 3- 12 yrs", "Exp: 5 - 10yrs".
EXP_SHORT = re.compile(r"\bexp(?:erience)?\s*:\s*(\d{1,2})\s*\+?\s*(?:(?:-|to)\s*\d{1,2}\s*)?\+?\s*(?:yrs|years)\b", re.I)
PHD_REQUIRED = re.compile(r"(phd|ph\.d\.?|doctorate)[^.\n]{0,40}\b(required|must)\b|"
                          r"\b(must|required to)\b[^.\n]{0,40}(phd|ph\.d\.?|doctorate)", re.I)
UNPAID = re.compile(r"\bunpaid\b|\bno stipend\b|\bvolunteer (position|role)\b", re.I)
NO_SPONSOR = re.compile(r"(not|unable to|cannot|can't|won't|will not|do not|don't)\s+(be able to\s+)?"
                        r"(provide\s+|offer\s+)?(visa\s+)?sponsor", re.I)
SPONSOR_OK = re.compile(r"\b(visa sponsorship (is )?(available|provided|offered)|we (do )?sponsor visas|"
                        r"sponsorship available|relocation (and|&) visa support)\b", re.I)
WORK_AUTH_REQUIRED = re.compile(r"(must|required to)\s+(be\s+)?(legally\s+)?(authorized|eligible) to work in "
                                r"(the\s+)?(us|united states|uk|canada|eu)", re.I)


@dataclass
class Eligibility:
    result: str = "pass"          # pass | fail | unclear
    reasons: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.result = "fail"
        self.reasons.append(f"fail: {reason}")

    def unclear(self, reason: str) -> None:
        if self.result != "fail":
            self.result = "unclear"
        self.reasons.append(f"unclear: {reason}")


def max_years_required(text: str) -> int | None:
    nums = [int(m.group(1)) for pat in (YEARS, EXP_SHORT) for m in pat.finditer(text) if int(m.group(1)) <= 30]
    return min(nums) if nums else None   # the *lowest* stated bar is the real minimum


def check_job(title: str, loc: ParsedLocation, text: str) -> Eligibility:
    e = Eligibility()
    relevance = role_relevance(title)
    if relevance == "irrelevant":
        e.fail("not a target ML/AI/software role by title")
    elif relevance == "borderline":
        e.unclear("technical but off-centre role (SRE/security/architect/analyst)")
    if SENIOR_TITLE.search(title) or MID_LEVEL.search(title):
        e.fail("senior/lead/manager title (candidate is new-grad)")
    years = max_years_required(text)
    if years is not None and years >= 4:
        e.fail(f"requires {years}+ years of experience")
    elif years is not None and years >= 2:
        e.unclear(f"asks for {years}+ years of experience")
    if PHD_REQUIRED.search(text):
        e.fail("PhD required")
    if UNPAID.search(text):
        e.fail("unpaid")

    abroad_only = not loc.in_india
    if loc.remote:
        scope = loc.remote_scope
        if scope == "restricted":
            e.fail(f"remote only within {', '.join(sorted(loc.countries | loc.regions))}")
        elif scope == "unspecified":
            e.unclear("remote, region not stated")
        abroad_only = abroad_only and scope != "india_ok"
    if abroad_only and not loc.remote:
        if not loc.countries and not loc.regions:
            e.unclear("location not stated")
        elif NO_SPONSOR.search(text) or WORK_AUTH_REQUIRED.search(text):
            e.fail("abroad and no visa sponsorship / local work authorisation required")
        elif SPONSOR_OK.search(text):
            e.reasons.append("ok: abroad with visa sponsorship stated")
        else:
            e.unclear("abroad; visa sponsorship not stated")
    return e
