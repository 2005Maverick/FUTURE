"""Extractor agent (DESIGN §5.1): messy text → zero or more opportunity records.

Model drafts; code verifies. Every filled field must carry a verbatim quote from
the source text; fields whose quote isn't found are set to null (never guessed).
Cheap model (Haiku 5.5, effort low) — local model on trijya-3 once benchmarked (S04.02).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from typing import Callable

import jsonschema

from future import config
from future.agents import guards
from future.llm import claude_runner
from future.orchestrator.budget import BudgetGuard

AGENT_FILE = config.REPO_ROOT / ".claude" / "agents" / "extractor.md"
MAX_TEXT_CHARS = 8_000
TYPES = ["job", "internship", "contract", "research_internship", "predoc", "lab_outreach", "ms_program",
         "scholarship", "hackathon", "competition", "grant", "accelerator", "fellowship", "credits", "travel_grant"]
QUOTED = ("title", "org", "location", "deadline", "pay")      # fields that need a verbatim quote

_nullable = lambda t: {"type": [t, "null"]}  # noqa: E731
ITEM = {
    "type": "object", "additionalProperties": False,
    "required": ["type", "title", "title_quote", "org", "org_quote", "url", "location", "location_quote",
                 "remote", "deadline", "deadline_quote", "pay", "pay_quote", "eligibility_notes", "scam_signals"],
    "properties": {
        "type": {"type": "string", "enum": TYPES},
        "title": _nullable("string"), "title_quote": _nullable("string"),
        "org": _nullable("string"), "org_quote": _nullable("string"),
        "url": _nullable("string"),
        "location": _nullable("string"), "location_quote": _nullable("string"),
        "remote": {"type": ["boolean", "null"]},
        "deadline": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "deadline_quote": _nullable("string"),
        "pay": _nullable("string"), "pay_quote": _nullable("string"),
        "eligibility_notes": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
        "scam_signals": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
    },
}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["opportunities"],
          "properties": {"opportunities": {"type": "array", "maxItems": 15, "items": ITEM}}}
OUTPUT_FORMAT = ("\n\n=== OUTPUT FORMAT ===\nReturn ONLY one JSON object (no prose, no code fences) matching this "
                 "JSON Schema:\n" + json.dumps(SCHEMA))
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


@dataclass
class Extraction:
    opportunities: list[dict]
    model: str
    tokens: int
    flags: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def verify(data: dict, text: str) -> tuple[list[dict], list[str]]:
    """Null every field whose verbatim quote is missing from the text; drop URLs not in the text;
    drop records left with neither title nor url."""
    hay = _norm(text[:MAX_TEXT_CHARS])
    urls_in_text = {u.rstrip(".,;:") for u in URL_RE.findall(text)}
    kept, flags = [], []
    for i, opp in enumerate(data.get("opportunities", [])):
        o = dict(opp)
        for f in QUOTED:
            quote = o.get(f"{f}_quote")
            if o.get(f) is not None and (not quote or _norm(quote) not in hay):
                flags.append(f"#{i}: {f} unsupported → null")
                o[f], o[f"{f}_quote"] = None, None
        if o.get("url") and o["url"].rstrip(".,;:") not in urls_in_text:
            flags.append(f"#{i}: url not in text → null")
            o["url"] = None
        if o.get("deadline"):
            try:
                dt.date.fromisoformat(o["deadline"])
            except ValueError:
                flags.append(f"#{i}: invalid deadline → null")
                o["deadline"], o["deadline_quote"] = None, None
        if not o.get("title") and not o.get("url"):
            flags.append(f"#{i}: no verifiable title or url → dropped")
            continue
        kept.append(o)
    return kept, flags


def system_prompt() -> str:
    return AGENT_FILE.read_text(encoding="utf-8").split("---", 2)[-1].strip() + OUTPUT_FORMAT


def extract(text: str, *, source: str, today: dt.date, guard: BudgetGuard | None = None,
            run_id: str | None = None, runner: Callable = claude_runner.run, model: str = "haiku",
            effort: str = "low") -> Extraction:
    sys_p = system_prompt()
    base = f"TODAY: {today.isoformat()}\nSOURCE: {source}\n\nTEXT (untrusted data):\n<<<\n{guards.fence(text[:MAX_TEXT_CHARS])}\n>>>"
    tokens, flags, errors = 0, [], []
    data: object = None
    model_used = model
    for attempt in range(2):
        prompt = base if attempt == 0 else f"{base}\n\nYOUR PREVIOUS OUTPUT WAS INVALID: {'; '.join(errors)}\nReturn corrected JSON only."
        if guard:
            guard.check((len(sys_p) + len(prompt)) // 3 + 800)
        r = runner(prompt, model=model, system_prompt=sys_p, json_schema=None, effort=effort, timeout_s=180)
        if guard:
            guard.record(purpose="extract", model=r.model, usage=r.usage, cost_usd=r.cost_usd, run_id=run_id)
        tokens += r.total_tokens
        model_used = r.model
        data = r.data if isinstance(r.data, dict) else claude_runner._parse_json_text(r.text)
        validator = jsonschema.Draft202012Validator(SCHEMA)
        errors = (["not a JSON object"] if not isinstance(data, dict) else
                  [f"{'/'.join(map(str, e.path))}: {e.message}" for e in validator.iter_errors(data)][:5])
        if not errors:
            break
        flags.append(f"attempt {attempt + 1} invalid: {errors[0]}")
    else:
        raise ValueError(f"extractor output invalid after retry: {errors}")
    kept, vflags = verify(data, text)
    return Extraction(kept, model_used, tokens, flags + vflags)
