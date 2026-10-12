# Reusable Skill Engineering
## Contents
- 1. What a skill is
- 2. When to build one
- 3. Structure and frontmatter
- 4. Progressive disclosure
- 5. Workflow design
- 6. References, scripts, hooks and subagents
- 7. Packaging and validation
- 8. Common gotchas
- 9. Release checklist
- 10. Current sources

## 1. What a skill is

A reusable skill packages specialized instructions, workflows, reference material, scripts, templates, and tests so an agent can perform a recurring task more reliably. The core skill is the entrypoint; related detail is loaded only when relevant.

A skill should provide something more specific than general intelligence:
- a domain procedure
- important failure modes and their mitigations
- use of specialized tools
- structured decision rules
- templates or deterministic automation
- a testable quality standard.

If a document only says "be accurate, helpful, concise, and think carefully," it is not a strong specialized skill.

## 2. When to build one

Build a skill when:
- the task recurs
- domain-specific procedure matters
- there are repeated pitfalls
- output conventions must persist
- references/templates/scripts are useful
- there are identifiable evaluations.

Use a one-shot prompt when the task is unique. Use project instructions for stable repository conventions. Use a hook or test for deterministic enforcement. Use a subagent for a distinct bounded role. Combine them only where the combined structure improves behavior.

## 3. Frontmatter and discovery

Use standard YAML frontmatter:

```yaml
---
name: specialist-skill-name
description: Describes the skill's capabilities and when it should be used.
---
```

Follow the target platform's current specification. For Claude Skills, the documented rules include a concise lowercase hyphenated `name`, a nonempty `description`, and a practical description of both what the skill does and when to use it.

The description is a discovery interface. Avoid generic labels like "helper" or "expert". Use the verbs, task types, artifacts, and trigger conditions a user would naturally mention.

Never assume that a skill is active just because its file exists. Test whether relevant tasks trigger it and irrelevant tasks do not.

## 4. Progressive disclosure

A useful layout:

```text
specialist-skill/
├── SKILL.md
├── domain-reference.md
├── workflows.md
├── examples.md
├── evaluation-cases.md
└── scripts/                 # optional deterministic helpers
```

Keep the main entrypoint focused on:
- when to use the skill
- first steps
- operating workflow
- important decision rules
- navigation to each direct reference
- quality gates
- handoff/output.

Put deep specialized material in separate files. Link every reference directly from `SKILL.md`; avoid long chains of references that force the model to discover a file through several intermediate files. For long references, add a contents section.

A practical target is fewer than 500 lines in `SKILL.md`, in line with current Anthropic guidance. It is a design target, not a reason to remove essential instructions.

## 5. Information architecture

Split references by distinct user intent or expertise, not arbitrary line counts. Each reference should answer:
- when to read it
- what decisions it supports
- which procedure or taxonomy it contains
- how to validate its output.

Avoid:
- duplicate instructions in main and references
- generic information a capable model already knows
- time-sensitive facts buried as permanent truth
- giant catch-all reference files
- nested references deeper than necessary
- several files with overlapping authority.

Keep terminology consistent. Give each important rule one canonical home and link to it.

## 6. Build for actual workflow

A skill should tell the model what to do, in what order, and how to recognize failure. It need not enforce one rigid workflow for every situation.

Include:
- trigger / non-trigger examples
- intake rules
- standard path
- conditional branches
- tool-use procedures
- output contracts
- troubleshooting / gotchas
- acceptance criteria
- recovery and escalation.

Match specificity to risk. Creative problem-solving needs degrees of freedom; destructive or exact operations need stricter steps.

## 7. Scripts and deterministic checks

Add scripts when they reliably perform deterministic work, such as:
- validating YAML/JSON
- checking required files
- checking broken links
- validating schemas
- collecting metadata
- linting output
- comparing manifests
- running fixed tests.

Scripts should not merely pass the work back to Claude. Include comments, usage instructions, dependency requirements, error handling, and expected outputs. Verify that dependencies exist or state how to install them.

Use model judgment for qualitative questions that do not have reliable deterministic rules. Use automation to support, not fake, judgment.

## 8. Skills vs rules, subagents, hooks

- **Skill:** reusable task procedure and specialist knowledge.
- **Project instructions / rules:** persistent project or path-specific conventions.
- **Subagent:** bounded specialist, potentially isolated context or tools.
- **Hook:** deterministic automation triggered by a lifecycle event.
- **Command:** explicit user-invoked workflow where supported.
- **External MCP/API integration:** actual capability/connection, not merely a prompt instruction.

Choose the mechanism based on when it should activate, where its instructions should live, whether it can take action, and how reliably behavior must be enforced.

## 9. Packaging

For a Claude Code skill, the usual install location is:
`.claude/skills/<skill-name>/SKILL.md`

A portable skill folder should preserve relative links. Package the whole folder as a ZIP if the user needs to install it manually. Don't give a ZIP containing only `SKILL.md` when the linked reference files are required.

Before delivery, validate:
- file and folder names
- YAML frontmatter
- Markdown headings
- relative links
- scripts and permissions if any
- no missing assets
- no accidental personal data or secrets
- no claim that an evaluation passed when it has not run.

## 10. Test the trigger

Create positive and negative trigger examples.

Positive: specific requests the skill should handle.
Negative: related-sounding tasks where the skill would be overkill or irrelevant.

For every description revision, test:
- direct user phrasing
- paraphrases
- ambiguous edge cases
- unrelated near-matches.

A skill that is excellent after activation but rarely activates is not complete. A skill that triggers on everything is not complete either.

## 11. Common gotchas

- Skill body becomes a general handbook.
- References contain stale tool/model assumptions.
- The main workflow does not tell the model which reference to open.
- A linked file is misspelled or missing from the ZIP.
- “Use current sources” is written without a web tool or fallback policy.
- Every task is routed through every specialist.
- Checklists become ritual rather than gates.
- Many examples encode one narrow style and bias all output toward it.
- Skills contain a changelog claiming tests passed without evidence.
- All instructions are copied into both `CLAUDE.md` and the skill, creating duplication.

## 12. Release checklist

- [ ] Description says what it does and when to invoke it.
- [ ] `SKILL.md` is concise and operational.
- [ ] Every detailed reference is directly linked.
- [ ] Important procedures have a clear start and finish.
- [ ] Key gotchas are concrete and actionable.
- [ ] Examples are realistic and contrastive.
- [ ] Positive/negative trigger tests exist.
- [ ] At least three task evaluations are defined.
- [ ] Relevant evaluation cases have been run, or status says not yet run.
- [ ] All files in the bundle exist and open.
- [ ] ZIP directory structure matches installation instructions.
- [ ] No unverified claim of production readiness.

## 13. Current sources

- Anthropic, Skill authoring best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic, lessons from building Claude Code skills: https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills
- Anthropic, choosing among skills, hooks, rules, and subagents: https://claude.com/resources/articles/steering-claude-code-skills-hooks-rules-subagents-and-more
- Anthropic, Skills overview: https://www.anthropic.com/research/skills

Platform syntax can change; check the current official documentation before publishing or distributing a new skill format.
