# ADR-001: Calling Claude headlessly on the Max subscription

**Status:** accepted (2026-10-12). Verified interactively, in a clean environment, **and from Windows Task Scheduler** (ST01.02.02).

## Context
- The pipeline must call Claude without an API key (owner decision), using Pranav's shared Max 20x plan.
- Each call's usage must be measurable for the budget guard.

## Verified (CLI 2.1.282, evidence in `evals/results/G01/R1-lean-calls.txt`)
1. `claude -p … --output-format json` in an environment **stripped of all `ANTHROPIC_*`/`CLAUDE*` variables**
   authenticates through the stored CLI login (`~/.claude/.credentials.json`). No key, no prompt.
2. The JSON result includes `usage` (input, output, cache-create, cache-read tokens), `modelUsage` (resolved model)
   and `total_cost_usd` (a list-price equivalent, useful as a budget unit even on a subscription).
3. The `haiku` alias resolves to **claude-haiku-4-5**, so the runner always passes full ids (`claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`).
4. A default call loads ~17k tokens of overhead (default system prompt, tools, global and project CLAUDE.md).
   Lean flags cut this to **~1k tokens (~94% less)**:
   `--system-prompt <own> --tools "" --strict-mcp-config --setting-sources "" --disable-slash-commands --no-session-persistence`
5. `--json-schema` gives schema-conforming structured output (tested with Haiku 5.5 and Sonnet 5.5).

## Decision
- All model calls go through `core/future/llm/claude_runner.py` using the lean flags.
- Agent instructions are passed as `--system-prompt`, built from `.claude/agents/*.md`, rather than relying on settings discovery.
- The runner refuses to start if `ANTHROPIC_API_KEY` is set.

## Open
- ST01.02.02 PASSED: a Task Scheduler task (user logged on; `scripts/run_probe.cmd` → `scheduler_probe.py`) ran with no
  Claude session vars and got `OK` from claude-haiku-5-5 (411 tokens). Evidence: `evals/results/G01/R1-scheduler.txt`.
  The 0x8007042B result came from the temporary cmd wrapper. The real job (python.exe called directly through
  scripts/task_scheduler.ps1) exits 0x0 (ST01.04.05). Untested: runs while **logged off** need a stored password,
  which is out of scope (the laptop stays logged in).
- `total_cost_usd` came out identical for Haiku and Sonnet on a tiny prompt. **Budget on tokens, not on cost_usd**,
  until per-model cost reporting is checked on realistic prompts.
