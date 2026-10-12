# FUTURE: Progress Ledger

> Single source of truth for build status. The build loop (docs/LOOP.md) reads this at the start of every iteration and updates it at the end.
> **Status values:**
> - `todo` · `doing` · `done` (with evidence) · `blocked:H#` (waiting on Pranav) · `blocked:dep` · `parked` (descoped for now)
> - Only mark `done` when the step's test or threshold has actually been met. Put the evidence in the Evidence column.

## Human gates (Pranav)
| ID | Need | Status |
|---|---|---|
| H1 | sudo in trijya-3 WSL | waiting |
| H2 | Vercel account + `vercel login` | waiting |
| H3 | Work Gmail + connector + forwarding filter | waiting |
| H4 | LinkedIn Connections.csv → private/ | waiting |
| H5 | Label 40 opportunities | needs G02 first |
| H6 | Voice samples | waiting (optional) |
| H7 | Per-submission approval | per item |
| H8 | Semantic Scholar key | waiting (optional) |
| H9 | Job-alert sign-ups | waiting |
| H10 | DESIGN §11 overrides | defaults apply |
| H11 | Copy Supabase **secret key** (Dashboard → project `future` → Settings → API Keys → Secret) into `.env` as `SUPABASE_SECRET_KEY=` | waiting |
| H-tok | Run `claude setup-token` once if unattended auth needs it (ST01.02.02) | not needed (CLI login works unattended) |

## Task ledger
| ID | Task | Status | Evidence / notes |
|---|---|---|---|
| G00 | Design v1 | done | docs/DESIGN.md; build invoked 2026-10-12 |
| ST01.01.01 | git init + remote | done | origin=2005Maverick/FUTURE; .env/private ignored (git check-ignore) |
| ST01.01.02 | Project CLAUDE.md | done | CLAUDE.md (infra ids moved to private/infra.md) |
| ST01.01.03 | Python package skeleton + pytest | done | pyproject.toml, core/future, .venv; pytest 17 passed |
| ST01.01.04 | Pre-commit secret/PII scanner + E-10 | done | E-10 PASS: real hook blocks key/phone/private path, allows clean (evals/results/G01/E-10-and-scanner-tests.txt) |
| ST01.01.05 | First commit + push | done | pushed to branch `dev` (rig_guard blocks pushes to main; Pranav merges dev→main via PR) |
| ST01.02.01 | R1 headless Claude auth check | done | clean-env `claude -p` works via CLI login; ADR-001 |
| ST01.02.02 | R1 unattended auth (Task Scheduler) | done | Task Scheduler run OK via CLI login, no H-tok needed (evals/results/G01/R1-scheduler.txt); exit-code quirk noted in ADR-001 |
| ST01.02.03 | R1 models + agent JSON output | done | claude_runner.py: haiku/sonnet 5.5 + --json-schema OK; lean flags ~1k vs ~17k tokens (evals/results/G01/R1-lean-calls.txt) |
| ST01.02.04 | R1 usage capture → ledger | doing | usage parsed into ClaudeResult; DB ledger write pending ST01.03 |
| ST01.02.05 | ADR-001 | done | docs/adr/001-headless-claude.md |
| ST01.03.01 | Supabase project `future` | done | $0/mo confirmed; ACTIVE_HEALTHY, ap-south-1 (id in private/infra.md) |
| ST01.03.02 | Migration 0001 | done | db/migrations/0001_init.sql + 0002_private_is_owner.sql applied; 17 tables |
| ST01.03.03 | RLS + sheet_view + anon-deny test | done | RLS on 17/17; security advisor 0 lints; anon read/write/RPC denied 11/11 (evals/results/G01/ST01.03.03-rls-anon-denied.txt) |
| ST01.03.04 | db.py + round-trip test | blocked:H11 | needs SUPABASE_SECRET_KEY in .env |
| ST01.04.01 | runs/events writer | done | store.py (Store/MemoryStore/SupabaseStore) + orchestrator/runlog.py; tests pass; live writes activate with H11 |
| ST01.04.02 | Idempotent stage runner + lock (E-08) | done | E-08 PASS: real kill mid-run → resume, 0 lost, ≤1 item repeated; 5/5 repeat runs pass; stale-lock + exclusive-lock tests (evals/results/G01/E-08-crash-resume.txt) |
| ST01.04.03 | Budget guard (E-09) | done | E-09 PASS: cap, urgent reserve, IST day reset (evals/results/G01/ST01.04-runlog-budget-E09.txt); cap 300k/day PROVISIONAL until S08.04 |
| ST01.04.04 | trijya probe + queue policy | todo | |
| ST01.04.05 | Task Scheduler registration | todo | |
| ST01.05.* | trijya-3 Docker/Ollama/SearXNG/Crawl4AI | blocked:H1 | |
| G01 | Gate | todo | |
| S02.01 | Greenhouse collector (30-company seed) | todo | |
| S02.02 | Normaliser + dedup + eligibility v1 (E-02 subset) | todo | |
| S02.03 | Evaluator v1 (jobs rubric) | todo | |
| S02.04 | Ranking + digest v1 | todo | |
| S02.05 | Sheet mirror (Apps Script) | todo | |
| S02.06 | Dashboard v0 (local first; deploy needs H2) | todo | |
| G02 | Gate | todo | |
| S03.01–S03.07 | Jobs track complete | todo | S03.07 needs H5 |
| S04.01–S04.06 | Messy sources + Extractor | todo | S04.02 needs H1; S04.03 needs H3/H9 |
| S05.01–S05.07 | Other tracks + Cartographer | todo | |
| S06.01 | Master CV 2-page + 1-page | todo | can start any time |
| S06.02–S06.06 | Fact file, contacts, Writer, Critic, approvals | todo | S06.03 needs H4 |
| S07.* | Act & track | todo | needs G06, H3, H7 |
| S08.* | Hardening | todo | |
| S09.* | Operate & learn | todo | |

## Iteration log
| # | Date (IST) | Did | Result | Next |
|---|---|---|---|---|
| 0 | 2026-10-12 | Wrote DESIGN, ROADMAP, PROGRESS, LOOP | — | ST01.01.01 |
| 1 | 2026-10-12 | S01.01 scaffold: git, CLAUDE.md, package, scanner+hook, E-10 | 17/17 tests pass; scan clean; pushed to dev | ST01.02.01 (R1 headless Claude) |
| 2 | 2026-10-12 | R1 spike: headless Claude on subscription; lean runner; ADR-001 | works; overhead -94%; 22 tests pass | ST01.02.02 Task Scheduler, then ST01.03 Supabase |
| 3 | 2026-10-12 | ST01.02.02 Task Scheduler unattended Claude call | PASS (411 tokens, haiku-5-5); temp task deleted | ST01.03 Supabase project + schema |
| 4 | 2026-10-12 | S01.03 Supabase: project, schema, RLS, advisor fix, anon-deny tests | PASS (HARD BLOCK gate cleared); db.py waits on H11 | ST01.04 orchestrator core (local, no DB writes until H11) |
| 5 | 2026-10-12 | ST01.04.01 run log + ST01.04.03 budget guard behind a Store interface | 13 new tests pass (E-09 PASS) | ST01.04.02 idempotent stage runner + lock (E-08) |
| 6 | 2026-10-12 | ST01.04.02 resumable stages (durable progress ledger) + single-instance lock | E-08 PASS (real process kill, 5/5 stable) | ST01.04.04 trijya-3 probe + queue policy |
