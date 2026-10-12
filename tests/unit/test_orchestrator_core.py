"""ST01.04.01 (run/event log) and ST01.04.03 / E-09 (budget guard)."""
import datetime as dt

import pytest

from future.orchestrator import budget as b
from future.orchestrator.runlog import run_stage
from future.store import MemoryStore

UTC = dt.timezone.utc


def fixed(ts):
    return lambda: ts


# ---------- run log ----------
def test_successful_run_records_status_counts_and_events():
    store = MemoryStore()
    with run_stage(store, "collect", source="greenhouse") as ctx:
        ctx.items_in, ctx.items_out = 10, 7
        ctx.event("fetched", "10 items")
    run = next(iter(store.runs.values()))
    assert run["status"] == "ok" and run["items_in"] == 10 and run["items_out"] == 7
    assert run["meta"] == {"source": "greenhouse"}
    assert [e["kind"] for e in store.events] == ["run_started", "fetched", "run_finished"]


def test_error_run_is_marked_and_reraised():
    store = MemoryStore()
    with pytest.raises(ValueError):
        with run_stage(store, "evaluate"):
            raise ValueError("bad json")
    run = next(iter(store.runs.values()))
    assert run["status"] == "error" and "bad json" in run["error"]
    assert store.events[-1]["kind"] == "run_error" and store.events[-1]["level"] == "error"


def test_budget_exhaustion_is_a_clean_stop_not_a_crash():
    store = MemoryStore()
    with run_stage(store, "evaluate"):
        raise b.BudgetExhausted("cap reached")
    run = next(iter(store.runs.values()))
    assert run["status"] == "budget_exhausted"


# ---------- budget guard (E-09) ----------
NOON_IST = dt.datetime(2026, 10, 12, 6, 30, tzinfo=UTC)  # 12:00 IST


def guard_with(store, now=NOON_IST, cap=1000, reserve=200):
    store.set_setting(b.CAP_KEY, cap)
    store.set_setting(b.RESERVE_KEY, reserve)
    return b.BudgetGuard(store, now=fixed(now))


def usage(n):
    return {"input_tokens": n, "output_tokens": 0}


def test_normal_work_stops_before_reserve():
    store = MemoryStore()
    g = guard_with(store)
    g.record(purpose="eval", model="m", usage=usage(700))
    g.check(100)                      # 700+100 <= 800 normal allowance
    with pytest.raises(b.BudgetExhausted):
        g.check(101)                  # would dip into the urgent reserve


def test_urgent_work_may_use_reserve_but_not_exceed_cap():
    store = MemoryStore()
    g = guard_with(store)
    g.record(purpose="eval", model="m", usage=usage(900))
    g.check(100, urgent=True)
    with pytest.raises(b.BudgetExhausted):
        g.check(101, urgent=True)


def test_usage_counts_all_token_kinds():
    store = MemoryStore()
    g = guard_with(store)
    entry = g.record(purpose="x", model="m", usage={"input_tokens": 1, "output_tokens": 2,
                                                     "cache_creation_input_tokens": 3, "cache_read_input_tokens": 4})
    assert entry.total_tokens == 10 and g.status().used == 10


def test_day_resets_at_ist_midnight():
    store = MemoryStore()
    yesterday_late = dt.datetime(2026, 10, 11, 18, 0, tzinfo=UTC)   # 23:30 IST on the 11th
    b.BudgetGuard(store, now=fixed(yesterday_late)).record(purpose="x", model="m", usage=usage(999))
    today = b.BudgetGuard(store, now=fixed(dt.datetime(2026, 10, 11, 19, 0, tzinfo=UTC)))  # 00:30 IST on the 12th
    assert today.status().used == 0


def test_defaults_are_provisional_and_safe_when_unset():
    st = b.BudgetGuard(MemoryStore(), now=fixed(NOON_IST)).status()
    assert st.cap == b.DEFAULT_DAILY_CAP_TOKENS and st.reserve == b.DEFAULT_URGENT_RESERVE_TOKENS
    assert st.normal_remaining == st.cap - st.reserve
