# Evaluation & Evals for Agents, Prompts, and Skills
## Contents
- 1. Why evaluation is part of design
- 2. Start with failure cases
- 3. Build an evaluation matrix
- 4. Baseline and paired testing
- 5. Rubrics and hard failures
- 6. Trigger tests
- 7. Agent-system tests
- 8. Regression and iteration
- 9. Certification and reporting
- 10. Sources

## 1. Evaluation is part of design

Do not write a large skill, then invent success criteria to justify it. Identify representative tasks and failure cases first.

Evaluate observable behavior, not instructions or confidence. A prompt is useful if it improves task success, reliability, efficiency, or the quality of decisions under realistic conditions.

An evaluation suite is not proof until it is executed. A list of test cases should be described as "prepared," not "passed."

## 2. Start with failure cases

For every target agent, identify:
- a routine positive case
- a difficult edge case
- a misleading or adversarial case
- a task with missing information
- a task the agent should ask about
- a task it should handle without over-questioning
- a case where sources conflict
- a case where tools fail or are unavailable
- a case outside scope
- a case that checks proportionality.

When improving an existing agent, first run baseline tasks and record actual weaknesses. This makes the skill responsive to real problems rather than imagined perfection.

## 3. Evaluation matrix

Use a matrix such as:

| Case ID | User task | Expected behavior | Hard failure | Evidence required |
|---|---|---|---|---|
| E-01 | Normal task | Correctly completes target workflow | Core requirement missed | Output artifact / result |
| E-02 | Missing critical detail | Asks high-value question or states safe assumption | Silently invents fact | Question/assumption log |
| E-03 | Conflicting sources | Maps conflict and assesses evidence | Cherry-picks or hides conflict | Source ledger |
| E-04 | Tool unavailable | States limit and offers feasible path | Pretends to use tool | Tool trace/result |
| E-05 | Edge condition | Handles boundary and failure path | Fails without detection | Executed test |
| E-06 | Near-miss trigger | Does not invoke skill unnecessarily | Overreach or irrelevant output | Trigger behavior |
| E-07 | Relevant paraphrase | Correctly activates procedure | Fails to trigger | Skill invocation evidence |
| E-08 | Adversarial reviewer | Addresses strongest objections | Self-certifies without testing | Critique + revision |
| E-09 | Regression task | Prior behavior remains correct | Previously solved issue returns | Paired result |
| E-10 | Efficiency task | Appropriate depth for the scope | Excessive ceremony | Time/tokens/tool counts where available |

Use domain-specific cases for the actual agent; generic cases alone are insufficient.

## 4. Baseline and paired testing

Where practical, compare:
- baseline prompt without the new design
- candidate with the new design.

Keep the same:
- model/version
- inputs
- tools and permissions
- environment
- output requirements
- evaluation rubric.

Record differences when perfect control is impossible.

Blind reviewers to which condition produced which output when feasible. Run repeated trials for tasks with stochastic outcomes. Report variation and critical failures, not only mean score.

## 5. Rubric

Score each applicable dimension 1–5 and attach evidence:

1. Task interpretation
2. Core correctness
3. Completeness
4. Domain specificity
5. Evidence/source quality
6. Decision quality
7. Handling of uncertainty
8. Tool use
9. Output usefulness
10. Robustness on edge cases
11. Recovery behavior
12. Efficiency / proportionality.

For creative or subjective tasks, add task-specific dimensions rather than using "quality" as one vague number.

### Suggested score meanings

- **1:** materially wrong or misses the objective
- **2:** substantial flaws; not usable without major rework
- **3:** usable but requires meaningful revision
- **4:** strong and mostly fit for purpose
- **5:** excellent, specific, evidence-backed, and directly useful.

Every high or low score must cite observable evidence. Do not award 5 merely because output is polished.

## 6. Hard failure gates

Define critical failures before running the evaluation. Examples:
- invented citations or fabricated research
- false claim that a test ran
- missing the primary deliverable
- violation of a non-negotiable constraint
- unsafe/destructive action without required approval
- wrong schema when machine consumption is required
- material privacy/security failure
- silent uncertainty on a critical claim
- key edge case left unhandled when it is central to the task.

A high average cannot cancel a hard failure.

## 7. Trigger evaluation

For skills that activate automatically, test:
- exact expected phrasing
- paraphrases
- common shorthand
- partial/ambiguous requests
- related but out-of-scope requests
- task that needs only a short answer
- another skill that should own the task.

Track:
- true positive: activates when needed
- false negative: fails to activate when needed
- false positive: activates unnecessarily
- correct negative: remains inactive when not needed.

Tune description and scope from observed errors, not guesses.

## 8. Multi-agent system tests

Test more than each agent in isolation.

Test:
- input/output contract compliance
- missing result from a delegated agent
- conflicting recommendations
- stale shared state
- duplicate work
- incomplete handoff
- orchestrator synthesis
- deadline / budget exhaustion
- retry behavior
- final output traceability.

An architecture can contain excellent individual specialists and still fail at coordination.

## 9. Iterate by root cause

For every failed case:
1. locate the exact failure
2. classify it: trigger, instructions, knowledge/reference, tool, architecture, evaluation, or model limitation
3. determine the smallest change likely to fix it
4. edit one cause at a time when practical
5. rerun the failed case
6. run a neighboring case to detect regressions
7. update the revision log
8. rerun the full critical suite before release.

Do not respond to each failure by adding a new universal rule. Look for the shared cause and improve the system's decision procedure.

## 10. Resource and operational metrics

Where measurable, capture:
- elapsed time
- tokens
- tool calls
- external API/model calls
- monetary cost
- human correction time
- failed attempts
- retries
- percentage of usable results
- latency under representative load.

Assess quality gain per unit cost, not just raw quality. A multi-agent architecture is justified only when its quality/reliability gains outweigh coordination, latency, and token costs for the user's use case.

## 11. Release report

Use an honest report:

```text
ARTIFACT / VERSION:
TARGET MODEL(S):
EVALUATION SET:
CASES EXECUTED:
CASES NOT EXECUTED:
BASELINE:
CANDIDATE:

RESULT:
- PASS FOR LIMITED PILOT
- PASS WITH KNOWN LIMITATIONS
- REVISE AND RETEST
- FAIL / NOT READY

SCORES BY DIMENSION:
HARD FAILURES:
CASES IMPROVED:
CASES UNCHANGED:
CASES REGRESSED:
RESOURCE COST / TIME:
KNOWN LIMITATIONS:
NEXT ACTION:
```

Do not report a skill as production-ready if tests have only been written. If no baseline exists, state that the evaluation is preliminary.

## 12. Evaluation sources

- Anthropic, *Demystifying evals for AI agents* (Jan 2026): https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Anthropic, Skill authoring best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic skill-creator repository: https://github.com/anthropics/skills/tree/main/skills/skill-creator

Use these sources for methodology. They do not validate a specific agent without actually running its evaluations.
