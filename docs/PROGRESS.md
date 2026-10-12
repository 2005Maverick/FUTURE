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
| ST01.04.04 | trijya probe + queue policy | done | orchestrator/trijya.py; 6 tests; live probe: awake, services not yet installed → WAIT (evals/results/G01/ST01.04.04-trijya-live-probe.txt) |
| ST01.04.05 | Task Scheduler registration | done | scripts/task_scheduler.ps1 (jobs created DISABLED); live: register→fire→exit 0x0→removed; run.py healthcheck stage |
| ST01.05.* | trijya-3 Docker/Ollama/SearXNG/Crawl4AI | blocked:H1 | |
| G01 | Gate | done (PASS WITH RISK) | evals/results/G01/GATE-G01.md; risks: H11 (live DB writes), H1 (trijya base) |
| S02.01 | Greenhouse collector (30-company seed) | done | 25 live boards (others use Ashby/Lever → S03.01); live run 25/25 ok, 6,029 postings, 32s, 0 tokens (evals/results/G02/S02.01-live-collect.txt); 7 unit tests |
| S02.02 | Normaliser + dedup + eligibility v1 (E-02 subset) | done | E-02 15/15 + 0 ineligible pass; live audit caught over-broad title rule (91 passes incl. recruiters) → role-relevance rewrite, 41 real-title regression tests; now 6,029→5,348 deduped → 37 pass / 351 unclear / 4,960 fail, manual audit 0 ineligible passes (evals/results/G02/S02.02-live-audit.txt) |
| S02.03 | Evaluator v1 (jobs rubric) | done | agent .claude/agents/evaluator.md + rubrics/jobs.md + private profile; deterministic guards (verbatim quotes, jsonschema, rubric-consistent recs, budget); live 12 roles: 65/66 quotes verified, 1 invented quote dropped; tokens cut 13.4k→6.0k/eval via single-turn JSON (ADR-001 #6); pre-filter gap 'Exp: 3-15yrs' fixed. Quality vs Pranav = E-03 (needs H5) |
| S02.04 | Ranking + digest v1 | done | pipeline/ranking.py (deterministic, per-component breakdown, weights PROVISIONAL until E-03) + digest/build.py; 9 tests; real digest rendered from 12 live evals (private/digests/2026-10-12.md). Found: evals must be keyed by dedup_key, not org+title (Stripe same title in 4 cities) → requirement for S02.05b |
| S02.05b | Daily stage: collect→normalize→evaluate (keyed by dedup_key, eval cache, budget-ordered)→rank→digest; local persistence until H11 | done | orchestrator/daily.py + LocalFileStore + migrations 0003/0004; 7 integration tests incl. keying regression; live: run1 6 evals/43k tokens, run2 0 tokens all cached (evals/results/G02/S02.05b-live-daily.txt). Finding: judge variance on close calls (3 vs 4) → E-03 |
| S02.05 | Sheet mirror (Apps Script) | blocked:H11 | reads Supabase; no rows there until the secret key is set |
| S02.06 | Dashboard v0 (local first; deploy needs H2) | doing | Next 16.4 (proxy.ts, Cache Components + Suspense per bundled docs) + Supabase SSR auth; Live (runs + realtime events), Opportunities, Digest; owner-only magic link; lint+build OK; auth test: all private routes 307→/login incl. forged cookie (evals/results/G02/S02.06-dashboard-auth.txt); realtime migration 0005. Remaining: deploy (H2), first sign-in + app_owner row (after H11 data), Supabase auth redirect URLs |
| G02 | Gate | blocked:H11 | pipeline E2E proven locally (S02.05b); 'visible on dashboard + Sheet' needs DB writes. DECISION 2026-10-12: data-side P03 work (more sources) proceeds meanwhile; display-dependent steps wait |
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
| 7 | 2026-10-12 | ST01.04.04 trijya-3 probe + run/wait/fallback policy | 6 tests pass; live probe correct | ST01.04.05 Task Scheduler registration script |
| 8 | 2026-10-12 | ST01.04.05 scheduler script + healthcheck stage; G01 gate | G01 PASS WITH RISK | P02: S02.01 Greenhouse collector |
| 9 | 2026-10-12 | S02.01 Greenhouse collector + collect stage + source health | live 6,029 postings; 136 rough India/remote ML matches | S02.02 normaliser + dedup + eligibility (US-only remote = ineligible) |
| 10 | 2026-10-12 | S02.02 normaliser, dedup, eligibility + role relevance | live audit found & fixed false passes; 0 ineligible in final 37 | S02.03 Evaluator v1 (jobs rubric) via skill |
| 11 | 2026-10-12 | S02.03 Evaluator agent v1 + live slice + token optimisation | 12 live evals sane & evidence-backed; -55% tokens/eval | S02.04 ranking + digest v1 |
| 12 | 2026-10-12 | S02.04 ranking + digest (interrupted by Pranav's server question, resumed) | 9 tests; real digest; keying requirement found | S02.05b daily stage wiring |
| 13 | 2026-10-12 | S02.05b daily pipeline end-to-end + local persistence | live E2E works; cache = 0 tokens on rerun; city bug fixed | S02.06 dashboard v0 (code + auth; deploy needs H2, data needs H11) |
| 13b | 2026-10-12 | State size fix (descriptions only for candidates: 41 MB → 8.4 MB) | MISTAKE: deleted state.json to rebuild → lost 6 cached evals (~43k tokens) + overwrote today's digest; fixed with automatic .bak snapshot on every save + test | S02.06 dashboard v0 |
| 14 | 2026-10-12 | S02.06 dashboard v0 code + auth tests | build OK; private routes locked; deploy/data wait on H2/H11 | S03.01 Lever/Ashby/Workable/SmartRecruiters collectors (G02 display pending) |
