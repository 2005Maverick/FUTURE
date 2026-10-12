"""ST01.02.02 probe: run one tiny Claude call from Windows Task Scheduler and record
whether it worked. Writes evals/results/G01/R1-scheduler.txt. Safe to delete later."""
import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
OUT = ROOT / "evals" / "results" / "G01" / "R1-scheduler.txt"


def main() -> int:
    lines = [f"run_at={dt.datetime.now().isoformat(timespec='seconds')}",
             f"launched_with_claude_session_vars={any(k.startswith('CLAUDE') for k in os.environ)}"]
    try:
        from future.llm import claude_runner as cr
        r = cr.run("Reply with exactly: OK", model="haiku", system_prompt="Reply tersely.", timeout_s=180)
        lines += [f"status=ok", f"result={r.text.strip()}", f"model={r.model}", f"total_tokens={r.total_tokens}"]
        code = 0
    except Exception as exc:  # record any failure for the ledger
        lines += [f"status=error", f"error={type(exc).__name__}: {exc}"]
        code = 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
