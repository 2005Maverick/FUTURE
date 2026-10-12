# High-Signal Prompt Engineering
## Contents
- 1. Prompt objective
- 2. Prompt specification
- 3. Core design pattern
- 4. Instructions and freedom
- 5. Context and evidence
- 6. Examples and schemas
- 7. Research and tool behavior
- 8. Reasoning and self-critique
- 9. Model-specific adaptation
- 10. Anti-patterns
- 11. Prompt QA
- 12. Sources

## 1. Prompt objective

A prompt is an interface between intent and model behavior. Optimize for task completion, decision quality, and reliability—not a dramatic persona description.

Before writing, state:
- what must the model produce or accomplish?
- who will use the result?
- what context does it need?
- what constraints are real?
- what evidence must support it?
- what does success look like?
- what errors are especially costly?
- what freedom should the model retain?

## 2. Prompt specification

Write a compact specification before the prompt itself:

```text
GOAL:
USER / AUDIENCE:
CONTEXT:
INPUTS:
OUTPUT / DELIVERABLE:
CONSTRAINTS:
AVAILABLE TOOLS:
QUALITY BAR:
FAILURE CONDITIONS:
UNCERTAINTIES:
ACCEPTANCE TEST:
```

Do not silently fill major unknowns. Ask, inspect, or clearly mark a default.

## 3. Core design pattern

A strong general-purpose prompt often contains:

1. **Objective:** the result to achieve.
2. **Context:** relevant facts, system state, audience, or source material.
3. **Constraints:** non-negotiable boundaries.
4. **Procedure:** only where a sequence materially improves reliability.
5. **Decision rules:** how to resolve trade-offs and uncertainty.
6. **Tools/evidence:** what to inspect and how to verify claims.
7. **Output contract:** structure, format, and required content.
8. **Acceptance criteria:** observable definition of done.
9. **Failure handling:** what to do when blocked, ambiguous, or wrong.

Use the shortest structure that covers the task's actual complexity. Do not force every prompt into a long template when a clear paragraph is more effective.

## 4. Outcome first, process only when useful

Prefer:
> Deliver an evidence-backed diagnosis of why the API intermittently returns stale data. Inspect the relevant code and logs, distinguish root causes from hypotheses, propose a test that separates the leading explanations, and do not claim a test ran unless you execute it.

Avoid:
> You are the world's best senior engineer with 50 years of experience. Think deeply and carefully. Be thorough, excellent, powerful, professional, elite, and perfect in every possible way.

The former changes behavior. The latter mainly describes a desired identity.

Specify steps when:
- order matters
- omissions are costly
- the task is multi-stage
- evidence needs traceability
- a known failure pattern needs prevention.

Leave room for model judgment when multiple methods are valid and constraints are clear.

## 5. Set the right degree of freedom

Use **high freedom** for open-ended creative work with clear goals and few hazards. Give the model outcome criteria and let it explore.

Use **medium freedom** when a default workflow exists but context changes the execution. Supply stages, options, and decision criteria.

Use **low freedom** when mistakes are expensive or operations are fragile. Specify exact sequence, validations, allowed actions, and approvals.

Don't apply rigid microsteps to every creative decision. Conversely, don't rely on broad aspirations for destructive, safety-critical, or exact-format tasks.

## 6. Context and evidence

Provide context that changes decisions. Remove information that does not.

For source-based work, tell the model to:
- inspect the supplied sources
- preserve their key terminology and framing when required
- distinguish source claims from external research and inference
- name missing evidence
- avoid filling gaps as if known.

For research:
- define the decision/question the research must support
- prefer primary sources for product/tool/policy facts
- cross-check consequential claims
- note source date and applicability
- seek contrary evidence
- stop when more research is unlikely to change the conclusion.

Do not say "research deeply" without clarifying what decision the research is supposed to resolve.

## 7. Instruction priority and conflict handling

For meaningful conflicts, define precedence. Example:
1. user’s explicit goal and constraints
2. applicable safety, legal, and platform constraints
3. authoritative source or repository contract
4. skill procedure
5. defaults and preferences.

The exact precedence depends on platform and applicable instructions. Do not pretend a custom prompt can override higher-priority system or platform rules.

When user constraints conflict:
- name the conflict
- explain why both cannot be satisfied as written
- offer options
- ask for a decision if it materially changes the output.

## 8. Examples are behavioral specifications

Use examples when they teach a distinction that prose alone may not establish.

Good examples show:
- acceptable input and output
- what is wrong with a tempting alternative
- how to label uncertainty
- correct tool usage
- common edge case
- valid and invalid structured output.

Do not overload examples with irrelevant detail or assume one example covers every task. Include contrastive examples for subtle behaviors.

## 9. Structured outputs

Use JSON, YAML, tables, or templates when downstream steps need predictable fields. Include:
- field names
- data types
- required/optional status
- enums where practical
- missing/unknown behavior
- validation criteria
- one realistic example.

Do not force structured output when it reduces usefulness or naturalness. A schema is a contract, not decoration.

## 10. Tool instructions

For each tool, specify the decision it supports. Avoid tool theater.

Define:
- when to use it
- what query/input to pass
- how to handle no results or failure
- how to validate results
- what not to infer from the output.

When the model can execute actions, distinguish read, write, external side effect, and destructive behavior. Require confirmation where needed.

## 11. Research, fact-checking, and freshness

For changing topics, specify:
- what must be current
- authoritative source types
- acceptable publication age when relevant
- how to cite
- how to label unknowns
- whether research is required before answering.

A prompt cannot guarantee freshness if the runtime has no web/research tool. It must then say that current claims remain unverified.

## 12. Self-critique that changes the output

“Critique your answer” is too vague alone. Define attack questions:
- Which requirement is least well supported?
- What input would break this?
- What alternative explanation could fit the evidence?
- What output would be technically correct but useless to the user?
- Which assumptions are doing the most work?
- Which section is generic or repetitive?
- What single test would most strongly falsify the conclusion?

Require the model to revise actual defects, not append a list of generic caveats.

Do not ask for hidden chain-of-thought. Ask for concise rationale, decisions, evidence, and testable explanations.

## 13. Model-specific adaptation

Prompts are not perfectly portable across model families, APIs, agent runtimes, and product surfaces. Before optimizing a prompt for a specific model:
- verify model identity and version
- inspect current official prompting guidance where available
- check tool schema and structured-output support
- determine context and latency constraints
- run representative evaluations
- compare with a shorter baseline
- preserve only improvements that survive testing.

For a strong model, excessive micro-instructions can narrow its search space or add noise. For a smaller model, more explicit decomposition or examples may be useful. Measure, don't assume.

## 14. Anti-patterns

Remove:
- “You are an expert in everything.”
- repeated “be thorough / be accurate / think deeply” with no observable method
- too many mandatory roles
- massive checklists unrelated to the task
- fixed question counts regardless of uncertainty
- invented numerical thresholds
- contradictory requests for brevity and exhaustive detail
- output structures that repeat the same information
- long negative-prompt lists that replace positive specification
- self-ratings with no evidence
- pretending to have performed research or tests
- rules that merely restate general common sense
- examples that are too specific and cause overfitting.

## 15. Prompt QA checklist

Before shipping a prompt, check:
- goal is unmistakable
- important context is present
- constraints are actionable
- tool availability is realistic
- procedure matches task complexity
- uncertainty path exists
- output contract is clear
- definition of done is testable
- no contradictory rules
- examples address real failure modes
- instructions are not repeated across sections
- there is a route to ask questions or state assumptions
- one or more evaluations can falsify the design.

## 16. Sources

- OpenAI, prompt engineering best practices: https://help.openai.com/en/articles/6654000-best-practices-for-prompt-engineering-with-chatgpt
- OpenAI, current prompting guide repository: https://github.com/openai/skills/blob/main/skills/.system/openai-docs/references/prompting-guide.md
- Anthropic, skill authoring best practices and context guidance: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices

Revisit sources when adapting the prompt to a newly released model, new API, or changed runtime.
