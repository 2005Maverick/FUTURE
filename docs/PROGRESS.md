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
| H-tok | Run `claude setup-token` once if unattended auth needs it (ST01.02.02) | only if needed |

## Task ledger
| ID | Task | Status | Evidence / notes |
|---|---|---|---|
| G00 | Design v1 | done | docs/DESIGN.md; build invoked 2026-10-12 |
| ST01.01.01 | git init + remote | done | origin=2005Maverick/FUTURE; .env/private ignored (git check-ignore) |
| ST01.01.02 | Project CLAUDE.md | done | CLAUDE.md (infra ids moved to private/infra.md) |
| ST01.01.03 | Python package skeleton + pytest | done | pyproject.toml, core/future, .venv; pytest 17 passed |
| ST01.01.04 | Pre-commit secret/PII scanner + E-10 | done | E-10 PASS: real hook blocks key/phone/private path, allows clean (evals/results/G01/E-10-and-scanner-tests.txt) |
| ST01.01.05 | First commit + push | done | pushed to branch `dev` (rig_guard blocks pushes to main; Pranav merges dev→main via PR) |
| ST01.02.01 | R1 headless Claude auth check | todo | |
| ST01.02.02 | R1 unattended auth (Task Scheduler) | todo | may need H-tok |
| ST01.02.03 | R1 models + agent JSON output | todo | |
| ST01.02.04 | R1 usage capture → ledger | todo | |
| ST01.02.05 | ADR-001 | todo | |
| ST01.03.01 | Supabase project `future` | todo | check cost/limit first |
| ST01.03.02 | Migration 0001 | todo | |
| ST01.03.03 | RLS + sheet_view + anon-deny test | todo | HARD BLOCK |
| ST01.03.04 | db.py + round-trip test | todo | |
| ST01.04.01 | runs/events writer | todo | |
| ST01.04.02 | Idempotent stage runner + lock (E-08) | todo | |
| ST01.04.03 | Budget guard (E-09) | todo | |
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
