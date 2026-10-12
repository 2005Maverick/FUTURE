"""Budget guard: keeps the pipeline's Claude usage under a daily token cap so it
never eats Pranav's shared Max 20x limit (DESIGN §8).

Budget unit is TOKENS (ADR-001: cost_usd is not reliable per model yet).
The default cap is PROVISIONAL and gets replaced by the calibration week (S08.04).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from future.store import BudgetEntry, Store

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Provisional until S08.04 calibration: deliberately small.
DEFAULT_DAILY_CAP_TOKENS = 300_000
DEFAULT_URGENT_RESERVE_TOKENS = 60_000
CAP_KEY = "budget.daily_cap_tokens"
RESERVE_KEY = "budget.urgent_reserve_tokens"


class BudgetExhausted(Exception):
    pass


@dataclass
class BudgetStatus:
    used: int
    cap: int
    reserve: int

    @property
    def normal_remaining(self) -> int:
        return max(0, self.cap - self.reserve - self.used)

    @property
    def urgent_remaining(self) -> int:
        return max(0, self.cap - self.used)


class BudgetGuard:
    def __init__(self, store: Store, now=lambda: dt.datetime.now(dt.timezone.utc)) -> None:
        self._store = store
        self._now = now

    def day_start(self) -> dt.datetime:
        local = self._now().astimezone(IST)
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(dt.timezone.utc)

    def status(self) -> BudgetStatus:
        cap = int(self._store.get_setting(CAP_KEY, DEFAULT_DAILY_CAP_TOKENS))
        reserve = int(self._store.get_setting(RESERVE_KEY, DEFAULT_URGENT_RESERVE_TOKENS))
        return BudgetStatus(used=self._store.tokens_used_since(self.day_start()), cap=cap, reserve=reserve)

    def check(self, estimated_tokens: int, *, urgent: bool = False) -> None:
        """Raise BudgetExhausted if this call would exceed today's allowance."""
        st = self.status()
        remaining = st.urgent_remaining if urgent else st.normal_remaining
        if estimated_tokens > remaining:
            raise BudgetExhausted(
                f"need ~{estimated_tokens} tokens, {remaining} left today "
                f"(used {st.used}/{st.cap}, reserve {st.reserve}, urgent={urgent})")

    def record(self, *, purpose: str, model: str, usage: dict, cost_usd: float = 0.0,
               run_id: str | None = None) -> BudgetEntry:
        entry = BudgetEntry(
            purpose=purpose, model=model, run_id=run_id, cost_usd=cost_usd,
            input_tokens=int(usage.get("input_tokens", 0)), output_tokens=int(usage.get("output_tokens", 0)),
            cache_create_tokens=int(usage.get("cache_creation_input_tokens", 0)),
            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)), at=self._now())
        self._store.add_budget(entry)
        return entry
