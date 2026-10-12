# Agent Architecture Design
## Contents
- 1. Architecture objective
- 2. Artifact-selection matrix
- 3. Specialist role design
- 4. Single agent vs multi-agent
- 5. Delegation contracts
- 6. State, memory, and context
- 7. Autonomy and control
- 8. Failure and recovery
- 9. Common architecture traps
- 10. Reference sources

## 1. Architecture objective

Architecture is the allocation of responsibility, context, decisions, and control. Do not start by naming agents. Start from the work that must be done and the boundaries that make the work easier to perform correctly.

Model the task as:
`USER GOAL → CAPABILITIES → WORKFLOW → DECISIONS → TOOLS / EVIDENCE → DELIVERABLE → ACCEPTANCE TESTS`.

For every component ask:
- What exact job owns it?
- What input does it need?
- What may it decide?
- What can it change?
- What does it return?
- Who consumes that result?
- How is quality judged?
- What happens when it fails?
- Why can this responsibility not remain elsewhere?

If the last question has no convincing answer, the component may be unnecessary.

## 2. Artifact-selection matrix

| Need | Best starting form | Use when |
|---|---|---|
| One task, one session | Task prompt | The work is self-contained and won't be reused much |
| Stable behavior across conversations | Persona/system instructions | Role, tone, judgement and recurring behavior matter |
| Repeatable procedure | Skill | The task has reusable steps, tools, templates, and quality gates |
| Repository conventions | Project instructions / rules | Requirements should be applied across many code tasks |
| Narrow specialist task | Subagent | Independent context or bounded specialist judgment is useful |
| Objective enforcement | Script / hook / test | The condition can be checked deterministically |
| Parallel independent work | Multi-agent orchestration | Work can truly proceed separately and synthesis adds value |
| Rich multi-stage product | Combined architecture | Distinct layers provide clear benefit and each boundary is explicit |

Do not turn everything into a skill. A skill is a capability pack, not a universal place to store all instructions.

## 3. Build the responsibility map

Create a list of work units. For each, record:
- mission
- inputs
- transformation / decisions
- outputs
- quality tests
- dependencies
- tools
- failure modes
- authority / autonomy
- required context.

Group work units by cohesion. Responsibilities that constantly need the same information and decisions often belong together. Responsibilities that need different evidence, specialized methods, or independent critique may be separated.

Use a **responsibility coverage matrix**:

| Required capability | Owner | Required input | Output | Acceptance evidence |
|---|---|---|---|---|

Every critical capability has one clear owner. Multiple components may contribute, but avoid ambiguity about who produces the final decision.

## 4. Specialist role design

A useful agent specification includes:

1. **Mission:** what outcome it owns.
2. **Domain boundaries:** what it handles and what it hands off.
3. **Operating procedure:** how it carries out the work.
4. **Decision rules:** how it chooses among alternatives.
5. **Evidence standard:** what sources/tests are needed.
6. **Tool contract:** tools it can actually use.
7. **Input contract:** what it expects and how it handles gaps.
8. **Output contract:** exact result it returns.
9. **Failure policy:** how it diagnoses, recovers, and escalates.
10. **Evaluation:** how to demonstrate competence.

Avoid fictional biographies as a substitute for capabilities. “Twenty years of experience” does not create experience. Encode expert-like practices: diagnosis, calibration, domain frameworks, counterexamples, controlled experiments, and disciplined trade-offs.

## 5. Single agent vs multi-agent

### Prefer one agent when
- responsibilities are tightly coupled
- the task needs a single coherent mental model
- delegation adds handoff overhead
- independent results would be hard to reconcile
- the task is small or time-sensitive.

### Consider multiple agents when
- subproblems are genuinely distinct
- investigation can occur in parallel
- independent critique reduces confirmation bias
- specialists use different evidence or tools
- each can return a useful artifact without reading every intermediate detail.

### Do not split just because
- a task is complex
- “six experts” sounds impressive
- the prompt asks for a team
- different headings can be assigned to different personas.

A single strong orchestrator with focused references may outperform a noisy committee.

## 6. Useful role patterns

Choose only those that address an observed risk.

- **Lead / architect:** owns scope, decisions, integration, and delivery.
- **Research specialist:** gathers current evidence and maps sources to claims.
- **Domain specialist:** handles a distinct technical or creative discipline.
- **Implementer:** creates the artifact or system.
- **Independent reviewer:** searches for failure and missing requirements.
- **Evaluator:** runs defined tests and scores evidence.
- **Operator:** deploys or performs state-changing work under explicit permissions.

A reviewer is not independent if it merely rewrites the implementer's reasoning in different words. Give it acceptance criteria and ask it to find counterevidence.

## 7. Delegation contracts

Every delegated task must specify:

```text
TASK ID:
MISSION:
CONTEXT TO READ:
EXACT QUESTIONS TO ANSWER:
TOOLS / PERMISSIONS:
CONSTRAINTS:
REQUIRED OUTPUT:
EVIDENCE REQUIRED:
WHAT NOT TO DO:
STOP / ESCALATION CONDITION:
```

Return structured results with:
- findings
- evidence
- uncertainties
- recommendations
- decisions needed from the lead
- artifact paths / IDs when relevant.

Avoid handoffs such as “research this deeply” with no decision to support. Ask what question the research must resolve and what evidence would change the recommendation.

## 8. Orchestration and integration

Define:
- sequence and parallelizable stages
- prerequisites
- shared artifacts and naming
- handoff format
- merge policy
- conflict resolution
- retry budget
- time/token/tool budget if relevant
- final authority
- termination condition.

The orchestrator should resolve contradictions rather than concatenate all opinions. When specialists disagree:
1. identify the actual disagreement
2. compare evidence quality
3. test assumptions
4. run a discriminating experiment if practical
5. record the decision and residual uncertainty.

Use parallelism only when outputs are sufficiently independent. Parallelizing dependent tasks can create rework.

## 9. State, memory, and context

Do not rely on conversation history as an invisible database for large workflows.

Identify what must persist:
- requirements and decisions
- source/evidence ledger
- task status
- versions
- shared facts
- unresolved questions
- test results
- known failures
- asset paths
- next actions.

Keep a compact source-of-truth artifact when the task lasts across sessions. Record facts separately from hypotheses and decisions. Avoid repeatedly loading irrelevant specialist knowledge; use selective references.

## 10. Tools and permissions

For each tool define:
- reason for use
- permitted inputs/actions
- expected output
- failure handling
- security implications
- whether it is read-only or state-changing
- whether results can be independently verified.

Never pretend unavailable tools exist. If a task depends on unavailable browsing, runtime, API, GPU, or repository access, distinguish the proposed plan from executed work.

Move deterministic checks into scripts/tests where appropriate. Use model judgment for ambiguous reasoning; use code for repeatable rules.

## 11. Autonomy and control

Classify actions:
- read-only investigation
- reversible local edit
- external side effect
- destructive or irreversible action
- production deployment or sensitive action.

Define approval boundaries. Specify when to stop and ask before overwriting, deleting, spending money, contacting others, publishing, deploying, or altering production state.

A powerful agent is not an agent with no constraints. It has clear authority and reliable escalation.

## 12. Failure and recovery

For every component consider:
- missing inputs
- contradictory sources
- tool error
- timeout
- partial output
- malformed output
- failed verification
- unavailable specialist
- disagreement
- stale state
- context loss
- budget exhaustion.

Define a fallback, retry condition, and user-facing status. Do not blindly retry a state-changing operation.

## 13. Common architecture traps

- Agent proliferation without distinct responsibility.
- Circular delegation.
- Reviewers that always agree.
- Agents returning essays instead of useful structured artifacts.
- A lead that merely concatenates reports.
- Repeated full-context sharing that wastes tokens.
- Memory without source-of-truth rules.
- Tools with ambiguous permissions.
- No stop condition.
- No tests for handoffs.
- “Consensus” used instead of evidence.
- Tool calls treated as proof without checking their results.

## 14. Reference sources

Consult and re-check platform details as they change:
- Anthropic, Skills and customization overview: https://www.anthropic.com/research/skills
- Claude Code guidance on skills, hooks, rules and subagents: https://claude.com/resources/articles/steering-claude-code-skills-hooks-rules-subagents-and-more
- Anthropic, *Building effective agents*: https://www.anthropic.com/research/building-effective-agents
- Anthropic agent evaluation guidance: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
