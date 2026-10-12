import datetime as dt

from future.digest.build import DigestItem, DigestStats, build
from future.pipeline.ranking import RankInput, rank, urgency

TODAY = dt.date(2026, 10, 12)


def test_better_fit_ranks_higher_all_else_equal():
    a = rank(RankInput(fit=5, value=3, recommendation="apply"), TODAY)
    b = rank(RankInput(fit=3, value=3, recommendation="apply"), TODAY)
    assert a.priority > b.priority


def test_close_deadline_beats_far_deadline():
    near = rank(RankInput(4, 4, "apply", deadline=TODAY + dt.timedelta(days=3)), TODAY)
    far = rank(RankInput(4, 4, "apply", deadline=TODAY + dt.timedelta(days=60)), TODAY)
    assert near.priority > far.priority and far.components["urgency"] == 0.0


def test_expired_and_skip_score_zero():
    assert rank(RankInput(5, 5, "apply", deadline=TODAY - dt.timedelta(days=1)), TODAY).priority == 0.0
    assert rank(RankInput(5, 5, "skip"), TODAY).priority == 0.0


def test_maybe_ranks_below_equal_apply():
    assert rank(RankInput(4, 4, "maybe"), TODAY).priority < rank(RankInput(4, 4, "apply"), TODAY).priority


def test_referral_lifts_priority():
    assert rank(RankInput(4, 4, "apply", referral_strength=5), TODAY).priority > \
        rank(RankInput(4, 4, "apply"), TODAY).priority


def test_unknown_deadline_is_modest_not_zero():
    assert urgency(None, TODAY) == (0.3, False)


def test_priority_bounds():
    top = rank(RankInput(5, 5, "apply", deadline=TODAY, referral_strength=5, first_seen=TODAY), TODAY)
    low = rank(RankInput(1, 1, "apply", deadline=TODAY + dt.timedelta(days=90), first_seen=TODAY - dt.timedelta(days=60)), TODAY)
    assert top.priority == 100.0 and 0.0 <= low.priority < 10


def item(org, rec, prio, deadline=None):
    return DigestItem(org=org, title="ML Engineer", location="Bengaluru", url=f"https://x/{org}", fit=4, value=4,
                      recommendation=rec, priority=prio, one_line="Strong LLM eval overlap.", deadline=deadline)


def test_digest_sections_order_and_skips_excluded():
    md = build(TODAY, [item("B", "apply", 50), item("A", "apply", 80), item("C", "maybe", 60), item("Z", "skip", 99)],
               DigestStats(collected=10, budget_used=150, budget_cap=300))
    assert md.index("**A —") < md.index("**B —")           # higher priority first
    assert "Z —" not in md                                   # skips never shown
    assert md.index("## Apply") < md.index("**C —")          # maybe appears after Apply section
    assert "(50%)" in md


def test_digest_deadline_window_and_empty_states():
    md = build(TODAY, [item("D", "apply", 70, deadline=TODAY + dt.timedelta(days=5)),
                       item("E", "apply", 60, deadline=TODAY + dt.timedelta(days=40))], DigestStats())
    deadlines = md.split("## Deadlines")[1].split("## Pipeline")[0]
    assert "D:" in deadlines and "E:" not in deadlines
    assert "_None today._" in build(TODAY, [], DigestStats())
