# FUTURE: Opportunity System Design (v1)

> **Status:** DRAFT v1, 2026-10-12. Nothing in this document has been built or tested yet.
> **Owner:** Pranav Singh Puri. **Written with:** `.claude/skills/agent-skill-architect`.
> **Evidence base:** nine verified research runs from 2026-10-10, saved in
> `D:\dev\_output\future\2026-10-10\research-A…I.md`. Claims taken from them cite the run letter, e.g. [A].

---

## 1. Problem specification

### Desired outcome
More **offers, admits, funding and wins** per hour of Pranav's time, in four tracks at once:

1. Jobs: full-time, 6-month internships, contract work.
2. Research: internships, pre-docs, professor outreach.
3. Higher studies: funded MS in Robotics or AI.
4. Hackathons, plus funding for Conquera.

### The real bottleneck
Finding opportunities is not the scarce part. These are:
- **Response rate.** Referrals reach interview at 40%, against about 3% for cold applications [F].
- **Pranav's time.**
- **Deadlines.**

The system therefore optimises **targeting, referrals and proof**, not the volume of polished letters. AI-written letters barely move callbacks [B].

### Facts, assumptions, unknowns
| Kind | Item |
|---|---|
| Fact | Claude runs only on Pranav's **Max 20x** subscription, shared with his other work. **No API key.** |
| Fact | The laptop is almost always on, with Edge and the Claude extension. **trijya-3** (RTX 3080 Ti 12 GB, WSL with 47 GB RAM, 507 GB free) **sleeps unpredictably**. It has no Docker or Ollama yet (checked 2026-10-11). |
| Fact | Repo `github.com/2005Maverick/FUTURE` is **public** by owner choice, so personal data never goes into git. |
| Fact | The Supabase organisation has 2 paused projects. The free-tier project limit could matter. |
| Fact | WhatsApp: channels only, read-only, at human pace. LinkedIn, Naukri and Wellfound forbid scraping [C][G]. |
| Assumption | Remote foreign pay floor = the equivalent of ₹10 LPA, until Pranav sets one. |
| Assumption | PhD programmes are out of scope. Remote research collaborations are in scope only if paid. |
| Unknown | The absolute size of the Max 20x weekly limit. Anthropic does not publish it [E], so the budget is **calibrated** (§8). |
| Unknown | Which address sends outreach email: pranavpuri03 (recommended) or a new one. See §11. |

### Scope

**In scope:** everything in the target list agreed on 2026-10-11 (jobs, research, MS, hackathons, Conquera funding).

**Out of scope:**
- unpaid work
- government hackathons (SIH, DISC)
- defence funding routes (iDEX)
- PhD programmes
- auto-submitting anything
- scraping sites whose terms forbid it

### Acceptance criteria for the whole system (v1)
1. Runs **daily without Pranav**, except for approvals, and survives trijya-3 sleeping and laptop restarts.
2. Every opportunity shown is **live, eligible and de-duplicated**, with its source link and deadline.
3. The shortlist matches Pranav's own judgement. Target: **at least 70% of top-10 items rated "worth applying" by him**, measured on a labelled set (§9). The figure is a starting target to revise after the first labels, not a researched threshold.
4. **Zero** drafts contain a claim missing from the fact file. **Zero** submissions or sends without explicit approval.
5. Daily Claude usage stays **under the calibrated cap** (§8), visible on the dashboard.
6. **No personal data is ever committed** to the public repo. A pre-commit check enforces this.

---

## 2. Architecture overview

The core rule, from the skill: **code does deterministic work, the model does judgement.** Agents exist only where judgement is needed, and every agent has a contract (§5).

```
            ┌──────────────── ORCHESTRATOR (Python, no LLM) ─────────────────┐
            │ schedule · stage order · budget guard · retries · run log      │
            └───┬───────────────┬───────────────┬───────────────┬────────────┘
                │               │               │               │
   COLLECT (code)        UNDERSTAND (LLM)   DECIDE (LLM)     PREPARE (LLM)       ACT (attended)
   collectors per   →    Extractor     →   Evaluator    →   Writer       →    Applier (browser)
   source + filters      (local model         (4 rubrics)      + Critic          stops at approval
   + dedup + liveness     or Haiku)                            (independent)
                │                                   ↑
                └──── Source Cartographer (weekly, finds new sources) ──┘

  STATE: Supabase Postgres (single source of truth) → Dashboard (Vercel) + Google Sheet mirror
  EVENTS: every stage writes run/event rows → live agent view
```

### Where things run
| Component | Runs on | Why |
|---|---|---|
| Orchestrator, collectors, filters, dedup | **Laptop**: Python, Windows Task Scheduler | Always on. Uses no tokens. |
| Claude agents (Extractor fallback, Evaluator, Writer, Critic, Cartographer) | **Laptop**: `claude -p` headless, subscription token | The only Claude route allowed (no API key) |
| Local model: triage and extraction; embeddings | **trijya-3** (Ollama in WSL), **only when awake** | Saves subscription usage |
| Self-hosted search (SearXNG) and crawler (Crawl4AI) | trijya-3 when awake, laptop fallback | Volume without paid APIs |
| WhatsApp reading, form filling | **Laptop Edge** through the Claude extension, in an attended or desktop session | The browser extension only exists there |
| Database, auth, realtime | Supabase (new `future` project) | Hosted, live updates |
| Dashboard | Vercel (Next.js) | Phone access |
| Sheet mirror | Google Apps Script inside the "Future" sheet, pulling from a read-only view | No service account needed |

**trijya-3 sleep policy.** Before each heavy stage, the orchestrator probes trijya-3's Ollama port.
- **Awake:** jobs go there.
- **Asleep:** jobs wait in the queue for up to 6 hours.
- **Still asleep after that:** Extractor work falls back to Haiku within the budget, and search/crawl falls back to the laptop.
- Nothing fails because trijya-3 sleeps.

---

## 3. Opportunity types and lifecycle

**One canonical record, `opportunity`, with `type` ∈** `job | internship | contract | research_internship | predoc | lab_outreach | ms_program | scholarship | hackathon | competition | grant | accelerator | fellowship | credits | travel_grant`.

**Lifecycle (status):**
```
found → verified → scored → shortlisted → preparing → awaiting_approval → submitted
  → (reply | interview | offer | rejected | no_response) ; or → skipped (with reason) / expired
```

**Hard eligibility filters run before any LLM spend:**
- deadline not passed
- location or remote compatible
- pay at or above the floor where pay is stated
- degree level (B.Tech final-year or graduate)
- nationality and visa (needs sponsorship outside India)
- not on the exclusion list (§1)

Opportunities that fail are stored as `skipped` with the reason, never silently dropped.

**Ranking.** `priority = f(deadline proximity, fit score, value, referral available, effort)`.
- The formula is deterministic and visible on the dashboard.
- The first weights are guesses, labelled as such, and get tuned from Pranav's labels.

---

## 4. Sources (v1 set)

**Principle:** use official feeds and email alerts first, polite scraping of permitted pages second, never forbidden scraping.

| Track | Source | Method | Verified |
|---|---|---|---|
| Jobs | Greenhouse, Lever, Ashby, Workable, SmartRecruiters company boards | Public JSON per company. Reuse **career-ops** `scan.mjs` providers | Yes [C] |
| Jobs | Company list: YC directory, VC portfolios (a16z, Sequoia/Peak XV, Accel India…), Common Crawl index harvest (~95k IDs) | Cartographer and a slug-harvest script | Partly [G] |
| Jobs | Himalayas API (country filter), Remotive API (4 calls/day, 24h delay) | API | Yes [G] |
| Jobs | SimplifyJobs and similar GitHub trackers | Raw README parse | Yes [C] |
| Jobs | LinkedIn, Naukri, Wellfound, Instahyre, Cutshort, Hirist, Internshala, YC WaaS | **Email alerts** into the work inbox, parsed by the Extractor | Method only |
| Research | OpenAlex (key in `.env`), Semantic Scholar (key pending) | API: topic → recent papers → authors → labs | Yes [C] |
| Research / MS | Programme and scholarship pages (OIST, DAAD, Erasmus Mundus, MEXT, GKS, KAIST, TUM, EPFL, NUS, MSR India…) | Watched pages with change detection | Per page |
| Hackathons | MLH events, Kaggle CLI (token in `.env`), lablab.ai; Devpost, Devfolio and Unstop alert emails | API, CLI, page watch, email | Partly [C][G] |
| Funding | Accelerator and scheme pages (YC, EF, Antler, EV, Thiel, Z Fellows, UPES Runway…) | Watched pages | Per page |
| All | WhatsApp channels (Krishan Kumar, TheGrowthRepo, Opportunities Corners, Ambition Arena, StartupsMap) | Read-only browser pass, 1–2×/day. The public channel page shows the last ~5 posts as a fallback [F] | Yes [F] |
| All | **Source Cartographer** discoveries: GitHub lists, newsletters, Telegram/Discord directories, Exa "pages like this" | Weekly run → proposals → adapters | — |

Collectors record per-source health and yield (items, kept, shortlisted, applied, replies). Sources that produce nothing get demoted.

---

## 5. Agents and their contracts

Six model-driven agents. Each one has a distinct job, input and output. Considered and **rejected as separate agents**:
- **"Strategist":** deterministic ranking does this.
- **"Referral agent":** deterministic contact matching plus the Writer.
- **"Reporter":** a template.
- **One scout per track:** collectors are code, and judgement is one Evaluator with per-track rubrics.

Persona text in each prompt is limited to **tone and method**. Persona prompts do not improve accuracy [B]. Correctness comes from rubrics, facts and external checks.

### 5.1 Extractor
| | |
|---|---|
| Mission | Turn messy text (WhatsApp posts, alert emails, web pages) into structured `opportunity` records |
| Input | Raw item text plus source metadata |
| Output | JSON per item: type, org, title, url, location, remote, pay, deadline, eligibility hints, confidence. **`null` if unknown, never guessed.** |
| Model | Local model on trijya-3 (chosen by benchmark in Phase 1); Haiku 5.5 fallback |
| Decision authority | None beyond extraction. It does not judge fit. |
| Failure | Bad JSON → retry once → mark `needs_review`. Missing deadline → `deadline: null`, flagged. |
| Tests | 50 labelled raw items (WhatsApp, email, page): field accuracy, never-invented fields |

### 5.2 Evaluator
| | |
|---|---|
| Mission | Decide whether an opportunity is worth Pranav's time, with evidence |
| Input | Opportunity record, the posting page (fetched), fact file, preferences, the track rubric |
| Rubrics (reference files) | `jobs` (adapted from career-ops' A–H blocks), `research/lab`, `ms/scholarship`, `hackathon`, `funding` |
| Output | `{fit 1–5, value 1–5, eligibility: pass/fail/unclear + reason, legitimacy: ok/suspect + signal, evidence quotes, gaps, recommended action}` |
| Model | Sonnet 5.5 |
| Bias controls | Rubric anchored on quoted evidence; length-neutral; calibrated against Pranav's labels (§9) |
| Failure | Cannot fetch the page → score from the record, flagged `low_evidence`. It never upgrades a score without evidence. |

### 5.3 Writer
| | |
|---|---|
| Mission | Produce the application materials an opportunity needs |
| Document types (one reference each) | Tailored CV (from the master 2-page CV), cover letter, SOP / statement (word limits enforced), professor email, referral request, grant and accelerator answers, form answers |
| Input | Opportunity, Evaluator report, **fact file**, voice profile, company/lab research notes (posting, papers, product) |
| Rules | Every claim must map to a fact-file entry ID. Names something specific and real about the target. Respects word limits. Never writes where AI text is banned (e.g. Emergent Ventures): it produces notes for Pranav instead. |
| Model | Opus 5.5 for SOPs, research emails and grants; Sonnet 5.5 for the rest |
| Output | Draft plus a claim map (sentence → fact ID) plus open questions for Pranav |

### 5.4 Critic (independent reviewer)
| | |
|---|---|
| Mission | Block drafts that are false, generic or off-target. It is not there to polish them. |
| Checks | (1) **Deterministic:** every fact ID resolves; word count; banned-phrase linter (AI tells profiled on our own drafts [B]); required fields. (2) **Model:** claims not supported by the fact file; generic sentences that would fit any company; mismatch with the posting's actual asks. |
| Model | Sonnet 5.5 with a different prompt from the Writer. A local model acts as a second-family style check when trijya-3 is awake [F]. |
| Output | `pass / revise (with specific line fixes) / block (with reason)`. At most **2 revise cycles**, then escalate to Pranav. |
| Why separate | Self-critique without an external signal makes drafts worse [B]. The Critic's external signals are the fact file, the posting and the linter. |

### 5.5 Source Cartographer
| | |
|---|---|
| Mission | Find **new** sources, from well-known to obscure, and propose how to collect them |
| Cadence | Weekly, plus on demand |
| Tools | Exa (key in `.env`), self-hosted SearXNG, GitHub search, the existing source table |
| Output | Proposals `{source, type, access method, terms check, sample items, expected yield}` → Pranav approves → an adapter is written |
| Guardrail | Records the terms-of-service verdict per source. Rejects any source that needs scraping a site whose terms forbid it. |

### 5.6 Applier (browser operator)
| | |
|---|---|
| Mission | Fill application forms in Edge using approved materials |
| Runs | Only in an attended or desktop Claude session on the laptop, where the Edge extension exists |
| Rules | Never creates accounts or types passwords (Pranav signs in). Stops before **Submit**. Submission happens only after **Pranav's explicit "yes" in the Claude chat** (phone through Remote Control) **or Pranav clicking Submit himself**. Never uploads anything not approved. |
| Output | Screenshot of the filled form plus field log → approval request; after submission, confirmation evidence → `submitted` |

### 5.7 Deterministic workers (no LLM)
- Collectors (one per source)
- URL canonicaliser and fingerprint dedup, plus embedding near-duplicate check
- Liveness checker (career-ops' method)
- Eligibility filter, ranking
- **Contact matcher**: opportunity organisation ↔ LinkedIn `Connections.csv`, co-author affiliations, past employers. This drives referral-first.
- Sheet sync, daily digest, budget guard, pre-commit secret and PII scanner

---

## 6. Daily flow

| Time (IST, adjustable) | Stage |
|---|---|
| 06:00 | Collect from all sources (code) → normalise → dedup → hard filters |
| 06:30 | Extract messy items: trijya-3 if awake, else queue |
| 08:00 | Evaluate new verified items, in priority order, until today's evaluation budget is spent |
| 09:00 | **Digest** to the dashboard and Sheet: new shortlist, deadlines in the next 14 days, referral matches, items needing a decision |
| On Pranav's pick | Writer → Critic → **approval queue** |
| Attended session | Applier fills forms; Pranav approves each submit |
| 13:00 and 19:00 | WhatsApp channel pass (read-only), when Edge is open |
| 21:00 | Inbox pass: alerts → new items; replies → status updates |
| Weekly (Sun) | Cartographer; source yield review; "what got replies" report; recalibrate weights |

All stages are idempotent and resumable. A run interrupted by a restart continues from the last completed item.

---

## 7. Data model (Supabase)

| Table | Holds |
|---|---|
| `sources` | name, type, method, terms verdict, health, last run, yield counters |
| `raw_items` | source_id, fetched_at, raw text/JSON, content hash |
| `opportunities` | canonical record (§3), status, priority, deadline, links, dedup key |
| `evaluations` | opportunity_id, rubric version, scores, evidence, model, tokens |
| `contacts` | people (connections, co-authors, recruiters, professors) with organisations. **Private.** |
| `referral_matches` | opportunity ↔ contact, path, strength |
| `documents` | drafts by type and version, claim map, Critic verdict |
| `approvals` | what is being approved (document or submit), payload hash, decision, decided_at, channel |
| `applications` | submitted_at, channel, evidence, follow-up dates, outcome |
| `runs`, `events` | every agent and stage run: start/end, status, items, **tokens and cost estimate**, errors → live view |
| `labels` | Pranav's thumbs or 1–5 ratings on opportunities and drafts (the golden set) |
| `budget` | daily and weekly usage ledger and caps |

**Security:**
- Single-user Supabase Auth.
- Row Level Security on every table.
- The Sheet reads only a restricted view.
- Personal source files (CV, standard answers, Connections.csv) stay in `private/`, gitignored, and are loaded into the database only where needed.

---

## 8. Usage budget on a shared Max 20x plan

Anthropic does not publish the absolute weekly limit [E]. So:

1. **Measure.** Every `claude -p` call runs with `--output-format json`. Its reported usage (and cost estimate) is written to `budget`. *(Verify in Phase 1 that headless JSON output carries usage under subscription auth.)*
2. **Cap.** Start with a **daily pipeline cap = 15% of one day's share of the weekly limit**, estimated from `/usage` readings over the first week. The pipeline stops non-urgent stages at the cap. Urgent deadline items may use a separate small reserve.
3. **Calibrate.** For 7 days, compare the pipeline's own token count against `/usage` percentages. Adjust the cap so the pipeline never pushes Pranav's other work into a limit.
4. **Spend priority when the budget is tight:** imminent deadlines > referral-backed > high fit > everything else.
5. **Never set `ANTHROPIC_API_KEY`** on the laptop. In `-p` mode it silently switches billing [E]. The orchestrator refuses to start if it's present.

**Savings levers (evidence [A]):**
- free collection and filtering before any model call
- local triage
- short contexts: only the posting plus the relevant fact entries, never the whole CV history
- routing: Haiku for extraction, Sonnet for judgement, Opus only for high-stakes writing

---

## 9. Evaluation plan (prepared, not yet run)

| ID | What | How | Hard failure |
|---|---|---|---|
| E-01 | Extractor field accuracy | 50 labelled raw items | Any invented deadline or pay |
| E-02 | Eligibility filter | 30 crafted edge cases (visa, degree, dates, unpaid) | An ineligible item shortlisted |
| E-03 | Evaluator vs Pranav | **Pranav labels 40 real opportunities** across tracks (thumbs + 1–5). Precision@10 of the shortlist. Swapped-order pairwise checks [F]. | — |
| E-04 | Writer factuality | 10 drafts; every sentence traced to a fact ID | Any unsupported claim |
| E-05 | Writer quality | Pranav blind-rates drafts against a plain baseline prompt | — |
| E-06 | Critic catch rate | 10 drafts seeded with planted errors | Misses a planted false claim |
| E-07 | Approval gate | Try to submit without approval | Any submission happens |
| E-08 | trijya-3 asleep / restart mid-run | Kill and resume | Lost or duplicated items |
| E-09 | Budget guard | Simulate hitting the cap | Pipeline keeps spending |
| E-10 | Repo safety | Commit a file containing a key or phone number | Commit succeeds |

**Tooling:** **Inspect AI** (MIT, self-hostable) [F], plus plain pytest for the deterministic parts. **Release rule:** nothing is called "working" until its rows here have run, with results recorded.

---

## 10. Build phases

Each phase ends with its own acceptance check. No phase starts before the previous one passes.

| Phase | Deliverable | Done when |
|---|---|---|
| **0** | This design, reviewed by Pranav | Pranav approves or edits |
| **1. Skeleton** | Repo scaffold and pre-commit guard; trijya-3: Docker, Ollama, local-model benchmark (E-01 subset), SearXNG, Crawl4AI; Supabase schema; orchestrator, budget ledger and `runs/events`; dashboard v0 (live view and pipeline list) | E-07, E-08, E-09, E-10 pass; dashboard shows a live dummy run |
| **2. Jobs slice** | career-ops installed; ATS, Himalayas, Remotive and SimplifyJobs collectors; Extractor; Evaluator (jobs rubric); digest; Sheet mirror | Real daily run works; **Pranav labels 40 items** (E-03 baseline) |
| **3. All tracks** | Research (OpenAlex), MS, hackathons, funding collectors and rubrics; WhatsApp pass; inbox alerts; Cartographer v1 | E-01, E-02 pass; each track has at least 1 week of real items |
| **4. Prepare and act** | Master CV and fact file; Writer and Critic; contact matcher (needs Connections.csv); approval queue; Applier | E-04, E-05, E-06 pass; first real applications sent with approval |
| **5. Learn** | Reply tracking and follow-ups; weekly review; weight recalibration; voice model (LoRA on trijya-3, if samples are approved) | One month of outcome data shows reply rate per track and source |

Running alongside every phase: the **2-page CV** (needed for both the fact file and applications).

---

## 11. Open decisions for Pranav

1. **Outreach sending identity:** draft in pranavpuri03 (recommended: established reputation) vs a new address. This system does not send from pranavpuri03 unless that Gmail is connected.
2. **Work inbox for alerts:** create the new dedicated Gmail? (Recommended: yes.)
3. **Voice samples:** Sent-folder export, 10 written prompts, or both.
4. **Remote foreign pay floor** (default: the equivalent of ₹10 LPA).
5. **PhD:** keep out of scope? (Default: yes.)
6. **trijya-3:** permission to install Docker and Ollama in WSL, plus a way to grant sudo.
7. **Supabase:** permission to create the free project `future` (it may hit the free-project limit if the two paused RIG projects are restored).
8. **Daily schedule times** in §6.

---

## 12. Risks and responses

| Risk | Response |
|---|---|
| Pipeline eats the shared Max 20x limit | Measured ledger, hard cap, calibration week, priority ordering (§8) |
| Subscription use in headless mode is a terms grey zone [E] | Personal, low-volume, single-user use of the unmodified Claude Code binary. Cap kept modest. If Anthropic objects, the switch is an API key on the orchestrator only. |
| trijya-3 asleep for days | Queue plus fallbacks. Nothing depends on it for correctness. |
| WhatsApp number flagged | Read-only, channels only, 1–2 human-paced passes a day; the public channel page as a fallback |
| Scraped sites change or block | One collector per source with health tracking. Failures show on the dashboard and never crash the run. |
| Public repo leaks personal data | `private/` and `.env` gitignored, plus a pre-commit scanner (E-10) |
| Generic or false applications hurt reputation | Fact-ID claim map, an independent Critic, Pranav's approval for every send |
| Supabase free project pauses when idle | Daily writes keep it active; status shown on the dashboard |
| Scam or paid-training postings in channels | Evaluator legitimacy check; "pay to apply" triggers `suspect` |
