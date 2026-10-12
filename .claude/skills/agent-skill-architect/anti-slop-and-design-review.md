# Anti-Slop, Specificity & Design Review
## Contents
- 1. What AI slop means in agent design
- 2. Replace adjectives with behavior
- 3. Specificity ladder
- 4. Remove redundancy
- 5. Opportunity-first critique
- 6. Expert behavior patterns
- 7. Originality and taste
- 8. Hostile design review
- 9. Rewrite examples
- 10. Acceptance checklist

## 1. What AI slop means in agent design

AI slop is not merely awkward phrasing. In prompts, personas, and skills it is **instructional material that sounds ambitious but does not reliably change behavior**.

Common forms:
- persona titles and fictional experience used as a substitute for method
- grand claims ("perfect", "genius", "best in the world")
- the same command repeated in many sections
- generic frameworks applied to every task
- lists of risks without repairs
- automatic rejection of ambitious ideas
- artificial question counts
- multi-agent theatre
- excessive output templates
- pretend research and pretend verification
- ungrounded numerical thresholds
- prompts that micromanage every choice while claiming to encourage creativity
- a huge skill that hides the important decision rules
- self-evaluation without evidence
- generic phrases like "think deeply" without defining the needed analysis.

## 2. Replace adjectives with behavior

For every aspirational phrase ask: **What would I observe if this instruction were followed?**

| Weak instruction | Behavioral replacement |
|---|---|
| Be an expert | Use the domain's diagnostic procedure; distinguish fact, inference, and uncertainty; test competing explanations |
| Be extremely detailed | Decompose only requirements and failure classes that can change the design or acceptance result; track coverage |
| Be creative | Generate meaningfully different options; explain each one's mechanism; avoid obvious default templates |
| Be critical | Identify a concrete failure, evidence, impact, and a repair or discriminating test |
| Do research | Identify the decision to resolve, search primary/current sources, map claims to evidence, seek contradictions, and report gaps |
| Make it production-grade | Define operational acceptance checks, recovery, permissions, observability, versioning, and release criteria appropriate to the scope |
| Remove AI slop | Replace abstractions with specific actions, trade-offs, examples, and observable criteria; remove repetition and stock phrasing |
| Use multiple agents | Delegate only independent specialist work with a contract; integrate disagreements against evidence |
| Test everything | Build a risk-weighted matrix of requirements, cases, oracles, results, and residual gaps |
| Ask me questions | Ask only unanswered questions whose answers materially alter the result; group them and explain the decisions they affect |

## 3. Specificity ladder

When a rule feels vague, descend these levels until it becomes usable:

1. **Aspiration:** "be excellent"
2. **Quality dimension:** "make diagnosis accurate"
3. **Observable behavior:** "separate symptoms from causes"
4. **Decision procedure:** "rank hypotheses by evidence and discriminating power"
5. **Test:** "design an experiment with predicted outcomes for the two leading hypotheses"
6. **Evidence:** "record results and update confidence; never claim execution without results."

Not every line needs level 6. But important requirements should descend far enough to change behavior.

## 4. Recursion without bloat

Depth means discovering the meaningful structure of a problem—not listing every conceivable subtype.

For a requirement, ask:
- What subtypes can produce different behavior?
- Which boundaries change the implementation?
- What interactions may invalidate the assumptions?
- What failure modes are plausible and consequential?
- What evidence would verify them?
- Can different branches be handled by one reusable rule?
- Does more detail change a decision, test, or output?

Stop decomposing when another level would not change action, acceptance, or risk handling. Record low-confidence areas instead of generating speculative taxonomies.

## 5. Remove redundancy

For each section, identify its unique job.

Use a **single source of truth** for cross-cutting principles, then reference it rather than repeating it. Keep task-specific examples near the behavior they teach.

To audit duplication:
1. extract repeated rules
2. compare whether they convey meaningfully different conditions
3. merge equivalent rules
4. preserve the strongest operational version
5. add cross-links where necessary
6. check that removing the duplicate did not erase a task-specific exception.

Repetition can be justified when a critical instruction must appear at a decision point, but it should add context rather than merely restate a slogan.

## 6. Opportunity-first critique

The agent designer's job is to help an ambitious idea become viable—not to begin by finding reasons to discourage it.

For any proposed capability:
1. state the strongest plausible version of the user's objective
2. identify the potential value
3. determine what must be true for it to work
4. map the gaps and risks
5. propose ways to close the gaps
6. define a prototype or evaluation that can establish feasibility
7. recommend proceeding, testing, revising, or rejecting based on evidence.

A risk statement alone is incomplete. Pair it with one or more of:
- mitigation
- alternative architecture
- fallback
- experiment
- explicit trade-off
- decision required.

Do not pretend every idea is viable. Do not reject ideas simply because they are difficult, competitive, or uncertain. Investigate the feasible design space.

## 7. High-quality specialist behavior

A strong specialist agent demonstrates:
- precise scope
- relevant domain models and methods
- independent judgment
- calibrated uncertainty
- source discipline
- awareness of trade-offs
- recognition of limits
- efficient tool use
- coherent outputs
- repeatable quality checks
- ability to revise after counterevidence.

It should not merely sound like an expert. Its decisions should reveal expertise.

## 8. Originality and useful taste

Original output comes from:
- strong understanding of the user's goal
- relevant but non-obvious connections
- meaningful alternatives
- attention to context
- deliberate constraints
- concrete execution choices
- critique that improves rather than sterilizes the result.

Avoid defaults unless supported by the user or domain. For instance, do not make every UI dark blue and glowing, every article contrarian, every channel faceless, every story inspirational, every agent a seven-role council, or every prompt a rigid checklist.

Before selecting a solution, ask:
- What would the generic version look like?
- What assumptions create that generic result?
- What is distinctive about this user's context?
- What alternative would be meaningfully different?
- What evidence or criterion should decide between them?

## 9. Hostile design review

Try to break the prompt or skill:
- Could an agent follow every instruction and still fail the objective?
- Are any instructions impossible in the actual tool environment?
- Does the workflow assume a fact it never checks?
- Are questions asked too late or too often?
- Is research likely to become unbounded?
- Does the architecture duplicate roles?
- Can the model silently skip a quality gate?
- Are output fields defined but never validated?
- Can the agent confuse a proposal with an executed test?
- Is there a stop condition?
- Can a user tell what is and is not complete?
- Would a smaller prompt perform just as well?
- What task would trigger the skill incorrectly?
- What task should trigger it but may not?
- Which instruction is least likely to survive context pressure?
- Which failure has no recovery path?

For each significant issue, write: observed weakness → consequence → fix → test.

## 10. Rewrite examples

### Example A: Overblown persona

Bad:
> You are the ultimate genius researcher who has decades of unmatched experience and knows everything about every topic. Always produce the perfect answer.

Better:
> For claims that affect the recommendation, verify the current source, distinguish documented facts from inference, seek contrary evidence, and state what remains unresolved. If the evidence could change the decision, do not skip the research step.

### Example B: Fake exhaustive testing

Bad:
> Test every possible edge case and guarantee production readiness.

Better:
> Build a risk-weighted coverage matrix for each requirement. Prioritize boundary conditions, malformed inputs, dependency failures, state transitions, and high-blast-radius interactions. Execute available tests, record results, and label anything not run as unverified. Do not claim exhaustive coverage.

### Example C: Endless critique

Bad:
> List all reasons the idea might fail before making a recommendation.

Better:
> First establish the strongest viable version of the idea and its value proposition. Then test the assumptions most likely to make it fail. For each material risk, propose a mitigation, alternative, or experiment. Recommend a kill only when evidence justifies it.

### Example D: Multi-agent theatre

Bad:
> Use 10 elite agents to discuss everything from every angle and produce the best solution.

Better:
> Delegate only work that can proceed independently and requires distinct evidence or expertise. Define each task's output, merge conflicting findings against the evidence, and omit any role whose contribution is duplicative.

## 11. Final acceptance checklist

- [ ] Important adjectives have been translated into behaviors.
- [ ] Critical behaviors have decision rules or observable tests.
- [ ] No fictional biography substitutes for capability.
- [ ] No repeated instruction adds no new context.
- [ ] The system searches for the viable version before rejecting ideas.
- [ ] Research requirements are bounded and evidence-based.
- [ ] Questions are decision-relevant.
- [ ] Role boundaries are real, not ceremonial.
- [ ] It does not claim unavailable tools or completed tests.
- [ ] The design leaves freedom where appropriate.
- [ ] Failures lead to useful repairs or experiments.
- [ ] The output can be tested against realistic tasks.
