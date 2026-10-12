# GATE G01: Foundation & risk spikes (2026-10-12)

## Decision: PASS WITH RISK

### HARD BLOCK items (†)
| Item | Result | Evidence |
|---|---|---|
| † E-10: scanner blocks secrets/PII | PASS | E-10-and-scanner-tests.txt |
| † R1: headless Claude unattended | PASS (interactive, clean env, Task Scheduler) | R1-lean-calls.txt, R1-scheduler.txt, docs/adr/001 |
| † Supabase live, RLS on, anon denied | PASS (17/17 RLS, advisor 0 lints, 11/11 anon tests) | ST01.03.03-rls-anon-denied.txt |

### Other items
| Item | Result | Evidence |
|---|---|---|
| E-08 crash/resume | PASS (real kill, 5/5 repeats) | E-08-crash-resume.txt |
| E-09 budget guard | PASS | ST01.04-runlog-budget-E09.txt |
| trijya-3 probe/policy | PASS (live: awake → WAIT, services absent) | ST01.04.04-trijya-live-probe.txt |
| Task Scheduler job | PASS (registered disabled → fired → exit 0x0 → removed) | private/logs/runs.jsonl (local) |

### Accepted risks
- **H11 pending:** live DB writes are not yet verified. SupabaseStore is tested offline (MockTransport); runs use MemoryStore plus a local JSONL log until the key is added. Re-verify the round trip (ST01.03.04) as soon as H11 lands.
- **H1 pending:** trijya-3 base (Docker, Ollama, SearXNG, Crawl4AI) is parked. The pipeline queues or falls back by design.

### Rollback
Nothing deployed and nothing scheduled. Scheduled jobs are created disabled; `scripts/task_scheduler.ps1 -Disable` stops everything.
