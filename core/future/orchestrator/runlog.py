"""Run/event logging: every stage execution is a `runs` row with an `events`
stream, which the dashboard's live view subscribes to."""
from __future__ import annotations

import contextlib
import traceback
from dataclasses import dataclass, field
from typing import Any, Iterator

from future.orchestrator.budget import BudgetExhausted
from future.store import Store


@dataclass
class RunContext:
    store: Store
    run_id: str
    stage: str
    items_in: int = 0
    items_out: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    notes: list[str] = field(default_factory=list)

    def event(self, kind: str, message: str = "", level: str = "info", **data: Any) -> None:
        self.store.add_event(self.run_id, kind, message, level, data)

    def add_usage(self, tokens: int, cost_usd: float = 0.0) -> None:
        self.tokens += tokens
        self.cost_usd += cost_usd


@contextlib.contextmanager
def run_stage(store: Store, stage: str, agent: str | None = None, **meta: Any) -> Iterator[RunContext]:
    """Record a stage run. Budget exhaustion is a normal stop (status
    budget_exhausted, not re-raised); any other exception marks the run as
    error and propagates."""
    run_id = store.start_run(stage, agent, meta)
    ctx = RunContext(store=store, run_id=run_id, stage=stage)
    ctx.event("run_started", f"{stage} started")
    status, error = "ok", None
    try:
        yield ctx
    except BudgetExhausted as exc:
        status, error = "budget_exhausted", str(exc)
        ctx.event("budget_exhausted", str(exc), level="warn")
    except Exception as exc:
        status, error = "error", f"{type(exc).__name__}: {exc}"
        ctx.event("run_error", error, level="error", traceback=traceback.format_exc(limit=5))
        raise
    finally:
        store.finish_run(run_id, status=status, items_in=ctx.items_in, items_out=ctx.items_out,
                         tokens=ctx.tokens, cost_usd=ctx.cost_usd, error=error)
        if status == "ok":
            ctx.event("run_finished", f"{stage} finished", items_in=ctx.items_in, items_out=ctx.items_out)
