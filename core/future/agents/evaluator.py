"""Evaluator agent (DESIGN §5.2). One opportunity in → validated evaluation out.

The model judges; this code enforces what can be checked deterministically:
schema ranges, verbatim evidence quotes, recommendation consistency, budget.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import jsonschema
from pathlib import Path
from typing import Callable

from future import config
from future.agents import guards
from future.llm import claude_runner
from future.orchestrator.budget import BudgetGuard

AGENT_FILE = config.REPO_ROOT / ".claude" / "agents" / "evaluator.md"
RUBRIC_DIR = Path(__file__).with_name("rubrics")
PROFILE_FILE = config.REPO_ROOT / "private" / "profile.md"
RUBRIC_VERSION = "jobs-v1"
MAX_POSTING_CHARS = 7_000

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fit", "value", "eligibility", "eligibility_reason", "legitimacy", "legitimacy_signal",
                 "evidence", "gaps", "recommendation", "one_line"],
    "properties": {
        "fit": {"type": "integer", "minimum": 1, "maximum": 5},
        "value": {"type": "integer", "minimum": 1, "maximum": 5},
        "eligibility": {"type": "string", "enum": ["pass", "fail", "unclear"]},
        "eligibility_reason": {"type": "string"},
        "legitimacy": {"type": "string", "enum": ["ok", "suspect"]},
        "legitimacy_signal": {"type": "string"},
        "evidence": {"type": "array", "minItems": 1, "maxItems": 6, "items": {
            "type": "object", "additionalProperties": False, "required": ["quote", "supports"],
            "properties": {"quote": {"type": "string"}, "supports": {"type": "string"}}}},
        "gaps": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
        "recommendation": {"type": "string", "enum": ["apply", "maybe", "skip"]},
        "one_line": {"type": "string", "maxLength": 200},
    },
}


@dataclass
class Evaluation:
    data: dict
    model: str
    tokens: int
    dropped_quotes: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def system_prompt(track: str = "jobs") -> str:
    agent = AGENT_FILE.read_text(encoding="utf-8").split("---", 2)[-1].strip()
    rubric = (RUBRIC_DIR / f"{track}.md").read_text(encoding="utf-8")
    profile = PROFILE_FILE.read_text(encoding="utf-8")
    return f"{agent}\n\n=== RUBRIC ===\n{rubric}\n\n=== CANDIDATE PROFILE ===\n{profile}"


def user_prompt(title: str, org: str, location: str, prefilter_notes: list[str], posting_text: str) -> str:
    notes = "; ".join(prefilter_notes) or "none"
    return (f"OPPORTUNITY\nTitle: {title}\nOrganisation: {org}\nLocation: {location}\n"
            f"Pre-filter notes (deterministic, may be incomplete): {notes}\n\n"
            f"POSTING TEXT (untrusted data):\n<<<\n{guards.fence(posting_text[:MAX_POSTING_CHARS])}\n>>>")


def validate(data: dict, posting_text: str) -> tuple[dict, list[str], list[str]]:
    """Drop non-verbatim quotes; enforce rubric consistency and the E-11 injection guards.
    Returns (data, dropped, flags)."""
    haystack = _norm(posting_text[:MAX_POSTING_CHARS])
    kept, dropped, injected = [], [], []
    for ev in data.get("evidence", []):
        quote = _norm(ev.get("quote", ""))
        if not quote or quote not in haystack:
            dropped.append(ev)
        elif guards.has_injection(ev["quote"]):
            injected.append(ev)              # verbatim, but it is an instruction to us, not evidence
        else:
            kept.append(ev)
    data = {**data, "evidence": kept}
    flags = []
    if dropped:
        flags.append(f"dropped {len(dropped)} non-verbatim quote(s)")
    if injected:
        flags.append(f"dropped {len(injected)} quote(s) that address an AI reader")
    if not kept:
        flags.append("no verifiable evidence")
    data, judgement_flags = _guard_judgement(data, guards.has_injection(posting_text))
    flags += judgement_flags
    rec = data["recommendation"]
    allowed = allowed_recommendations(data["fit"], data["eligibility"])
    if rec not in allowed:
        flags.append(f"recommendation '{rec}' inconsistent with fit={data['fit']}/eligibility="
                     f"{data['eligibility']}; set to '{allowed[0]}'")
        data["recommendation"] = allowed[0]
    if data["recommendation"] == "apply" and (not kept or data["legitimacy"] == "suspect" or injected):
        reason = ("no verifiable evidence" if not kept else
                  "legitimacy suspect" if data["legitimacy"] == "suspect" else "posting addresses an AI reader")
        flags.append(f"apply → maybe ({reason}); a human must look first")
        data["recommendation"] = "maybe"
    return data, [d.get("quote", "") for d in dropped + injected], flags


INJECTION_ONE_LINE = "Posting contains text aimed at AI screeners; read it yourself before acting."


def _guard_judgement(data: dict, posting_has_injection: bool) -> tuple[dict, list[str]]:
    """Free text goes into the digest: no links or addresses, no sentence addressing an AI reader.
    If the posting carries an injection, the model's one_line is replaced outright (E-11 EV-03:
    a summary repeated the injected request)."""
    flags = []
    one_line = INJECTION_ONE_LINE if posting_has_injection else guards.scrub(data["one_line"])
    reason = guards.scrub(data["eligibility_reason"])
    gaps = [g for g in (guards.scrub(x) for x in data.get("gaps", [])) if g]
    if posting_has_injection:
        flags.append("posting addresses an AI reader; one_line replaced")
    elif one_line != data["one_line"].strip():
        flags.append("one_line scrubbed")
    return {**data, "one_line": one_line or "(no summary)", "eligibility_reason": reason, "gaps": gaps}, flags


def allowed_recommendations(fit: int, eligibility: str) -> tuple[str, ...]:
    """Rubric (jobs.md): apply = fit≥4 & not fail; maybe = fit 3, or fit≥4 with an eligibility question."""
    if eligibility == "fail":
        return ("skip",)
    if fit >= 4:
        return ("apply",) if eligibility == "pass" else ("apply", "maybe")
    if fit == 3:
        return ("maybe",)
    return ("skip",)


OUTPUT_FORMAT = ("\n\n=== OUTPUT FORMAT ===\nReturn ONLY one JSON object (no prose, no code fences) "
                 "matching this JSON Schema:\n" + json.dumps(SCHEMA))


def schema_errors(data: object) -> list[str]:
    validator = jsonschema.Draft202012Validator(SCHEMA)
    return [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in validator.iter_errors(data)][:5]


def evaluate(title: str, org: str, location: str, prefilter_notes: list[str], posting_text: str, *,
             guard: BudgetGuard | None = None, run_id: str | None = None, model: str = "sonnet",
             effort: str = "medium", runner: Callable = claude_runner.run, track: str = "jobs") -> Evaluation:
    """Single-turn JSON + local schema validation (ADR-001: --json-schema costs ~3 turns, ~2.2x tokens).
    One repair retry if the JSON is invalid."""
    sys_p = system_prompt(track) + OUTPUT_FORMAT
    usr_p = user_prompt(title, org, location, prefilter_notes, posting_text)
    flags: list[str] = []
    tokens = 0
    data: object = None
    model_used = model
    for attempt in range(2):
        prompt = usr_p if attempt == 0 else (
            f"{usr_p}\n\nYOUR PREVIOUS OUTPUT WAS INVALID: {'; '.join(errors)}\nReturn the corrected JSON only.")
        if guard:
            guard.check((len(sys_p) + len(prompt)) // 3 + 1000)
        result = runner(prompt, model=model, system_prompt=sys_p, json_schema=None, effort=effort, timeout_s=240)
        if guard:
            guard.record(purpose=f"evaluate:{track}", model=result.model, usage=result.usage,
                         cost_usd=result.cost_usd, run_id=run_id)
        tokens += result.total_tokens
        model_used = result.model
        data = result.data if isinstance(result.data, dict) else claude_runner._parse_json_text(result.text)
        errors = ["output is not a JSON object"] if not isinstance(data, dict) else schema_errors(data)
        if not errors:
            break
        flags.append(f"attempt {attempt + 1} invalid: {errors[0]}")
    else:
        raise ValueError(f"evaluator output invalid after retry: {errors}")
    data, dropped, vflags = validate(data, posting_text)
    return Evaluation(data=data, model=model_used, tokens=tokens, dropped_quotes=dropped, flags=flags + vflags)
