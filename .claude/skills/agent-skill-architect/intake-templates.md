# Intake Templates, Specifications & Handoffs
## Contents
- 1. Question-first design
- 2. Universal specialist intake
- 3. Prompt-only intake
- 4. Skill-build intake
- 5. Existing-agent audit
- 6. Specification template
- 7. Agent contract
- 8. Evaluation plan
- 9. Decision/handoff report

## 1. Question-first design

The purpose of intake is to uncover decisions that would otherwise be made on hidden assumptions. It is not to interview the user for its own sake.

Ask a question if its answer may change:
- architecture
- behavior
- tool choice
- autonomy
- safety or permission boundary
- output
- success metrics
- research procedure
- deployment
- evaluation.

Do not ask if:
- the answer is already in the supplied material
- it has no meaningful effect on the design
- a safe reversible default is obvious
- the task is simple enough to proceed.

For a substantial design, ask grouped questions in one message and pause for answers if the user wants to co-design. Avoid asking for every technical detail before learning the main purpose.

## 2. Universal specialist intake

Use selectively:

### A. Outcome
1. What exact job should the agent perform?
2. Why does this matter; what will the result enable?
3. What would an excellent result look like in a real example?

### B. Audience and context
4. Who will use it and in what environment?
5. Is this a one-off task, recurring workflow, or long-lived system?
6. What inputs, files, data, code, and external systems exist?

### C. Scope
7. What is in scope?
8. What must it not do?
9. Which adjacent tasks should be handed to another tool/agent?

### D. Behavior and judgement
10. What choices must it make independently?
11. What should cause it to ask you first?
12. How should it handle conflicting evidence, missing information, or uncertain results?

### E. Tools and constraints
13. Which model/platform/runtime will run it?
14. Which tools, APIs, repository access, compute, or credentials are available?
15. What budget, latency, privacy, license, or environment constraints exist?

### F. Deliverables
16. What exact artifact(s) must it produce?
17. Required format, schema, style, or level of detail?
18. What are examples of excellent and unacceptable outputs?

### G. Quality and risk
19. What are the most costly failure modes?
20. How can success be tested?
21. What must be verified independently?
22. How should it recover or report a blocker?

### H. Maintenance
23. Will current research or policy changes matter?
24. How should versioning, evaluation, and future updates work?
25. Where/how will it be installed or invoked?

These are a bank of possible questions, not a mandatory 25-question questionnaire. Ask only those material to the project.

## 3. Prompt-only intake

For a one-off prompt, usually only determine:
- task/outcome
- target model or platform if consequential
- essential context
- constraints
- required output
- quality bar / example.

Then write the prompt. Do not force agent architecture, hooks, reference files, or an evaluation suite unless the request warrants them.

## 4. Skill-build intake

For a reusable skill, determine:
- trigger phrases and non-trigger cases
- recurring procedure
- special domain knowledge
- frequent errors
- tools/scripts/templates
- main workflow
- reference-file boundaries
- expected outputs
- acceptance tests
- install/package format
- current documentation needed.

Inspect existing instructions and representative real tasks before adding large documentation.

## 5. Existing-agent audit

Ask for or inspect:
- original prompt / SKILL.md / agent config
- intended use
- examples of failures
- outputs that are good and bad
- model/runtime
- tools and permissions
- current tests/evaluations
- constraints that must be preserved.

Audit:
1. goal mismatch
2. ambiguity
3. missing context
4. instruction conflicts
5. duplicated content
6. unsupported capability claims
7. poor tool strategy
8. failure handling
9. missing acceptance criteria
10. over-triggering / under-triggering
11. evaluation gap
12. unnecessary length.

Provide a prioritized diagnosis before rewriting the whole system if the user wants an audit first.

## 6. Agent / skill specification template

```yaml
artifact_type: "prompt | persona | skill | subagent | multi-agent system"
name: "..."
mission: "..."
primary_users: []
trigger_conditions: []
non_trigger_conditions: []
inputs: []
outputs: []
tools_available: []
permissions:
  read: []
  write: []
  external_side_effects: []
constraints: []
core_workflow: []
decision_rules: []
question_policy: "..."
evidence_policy: "..."
failure_modes: []
recovery_policy: []
acceptance_criteria: []
evaluation_cases: []
installation_target: "..."
unresolved_questions: []
```

Use only the fields that matter. Treat the template as a thinking aid, not a schema that every deliverable must contain.

## 7. Agent contract template

```text
ROLE / COMPONENT:
MISSION:
IN SCOPE:
OUT OF SCOPE:
INPUT CONTRACT:
TOOLS / PERMISSIONS:
PROCEDURE:
DECISION AUTHORITY:
OUTPUT CONTRACT:
EVIDENCE REQUIRED:
FAILURE / RECOVERY:
HANDOFF TO:
ACCEPTANCE TESTS:
```

## 8. Evaluation plan template

```text
EVAL ID:
TASK:
BASELINE:
EXPECTED BEHAVIOR:
HARD FAILURE:
EVIDENCE:
SCORING DIMENSIONS:
RUN CONFIGURATION:
REPETITIONS:
RESULTS:
REGRESSIONS:
DECISION:
```

## 9. Decision and handoff report

For a substantial project, finish with:
- what was created or changed
- key design decisions and why
- files and installation paths
- how to invoke
- which cases were run and actual result
- known limitations
- unresolved decisions
- next highest-value action.

Do not bury a missing test or blocked capability in a footnote. Make the status explicit.
