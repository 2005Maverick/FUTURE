"""Headless Claude runner: the ONLY way the pipeline calls Claude.

Runs `claude -p` on Pranav's subscription login (never an API key), with a lean
context (own system prompt, no tools, no MCP, no user/project settings) so each
call doesn't pay ~17k tokens of default overhead. Returns parsed output plus a
usage record for the budget ledger.

Facts verified in ST01.02 (CLI 2.1.282):
- clean-env `claude -p --output-format json` authenticates via the stored CLI login
- JSON result carries `usage`, `modelUsage`, `total_cost_usd` (list-price equivalent)
- the `haiku` alias resolves to claude-haiku-4-5, so always pass full model ids
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

MODELS = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}

# Env vars injected by the Claude desktop app / SDK. Stripped so a pipeline run
# behaves identically whether launched from Task Scheduler or from a session.
_STRIP_PREFIXES = ("ANTHROPIC_", "CLAUDE_", "CLAUDECODE")


class ClaudeRunnerError(RuntimeError):
    pass


class ApiKeyPresentError(ClaudeRunnerError):
    """ANTHROPIC_API_KEY would silently switch billing to per-token API usage."""


@dataclass
class ClaudeResult:
    text: str
    data: Any | None
    model: str
    usage: dict[str, Any]
    cost_usd: float
    duration_s: float
    session_id: str | None
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def total_tokens(self) -> int:
        u = self.usage
        return int(
            u.get("input_tokens", 0) + u.get("output_tokens", 0)
            + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        )


def clean_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    if env.get("ANTHROPIC_API_KEY"):
        raise ApiKeyPresentError("ANTHROPIC_API_KEY is set; refusing to run (would bill the API).")
    return {k: v for k, v in env.items() if not k.startswith(_STRIP_PREFIXES)}


def claude_executable() -> str:
    exe = shutil.which("claude.exe") or shutil.which("claude")
    if not exe:
        raise ClaudeRunnerError("claude CLI not found on PATH")
    # On Windows the npm shim is a .ps1/.cmd; prefer the real binary next to it.
    if exe.lower().endswith((".ps1", ".cmd")):
        real = os.path.join(os.path.dirname(exe), "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
        if os.path.exists(real):
            return real
    return exe


def build_command(prompt: str, model: str, system_prompt: str, json_schema: dict | None,
                  effort: str | None = None) -> list[str]:
    cmd = [
        claude_executable(), "-p", prompt,
        "--output-format", "json",
        "--model", MODELS.get(model, model),
        "--system-prompt", system_prompt,
        "--tools", "",
        "--strict-mcp-config",
        "--setting-sources", "",
        "--disable-slash-commands",
        "--no-session-persistence",
    ]
    if json_schema is not None:
        cmd += ["--json-schema", json.dumps(json_schema)]
    if effort is not None:
        cmd += ["--effort", effort]
    return cmd


def run(prompt: str, *, model: str = "haiku", system_prompt: str, json_schema: dict | None = None,
        timeout_s: int = 300, cwd: str | None = None, effort: str | None = None) -> ClaudeResult:
    cmd = build_command(prompt, model, system_prompt, json_schema, effort)
    started = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          env=clean_env(), timeout=timeout_s, cwd=cwd)
    elapsed = time.monotonic() - started
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeRunnerError(f"non-JSON output (rc={proc.returncode}): {proc.stderr[-500:] or proc.stdout[:500]}") from exc
    if raw.get("is_error") or raw.get("subtype") != "success":
        raise ClaudeRunnerError(f"claude error: {raw.get('subtype')} {raw.get('result')!r} {raw.get('api_error_status')}")
    text = raw.get("result", "")
    data = raw.get("structured_output")
    if data is None and json_schema is not None:
        data = _parse_json_text(text)
    models_used = list((raw.get("modelUsage") or {}).keys())
    return ClaudeResult(
        text=text, data=data, model=models_used[0] if models_used else MODELS.get(model, model),
        usage=raw.get("usage", {}), cost_usd=float(raw.get("total_cost_usd") or 0.0),
        duration_s=round(elapsed, 2), session_id=raw.get("session_id"), raw=raw,
    )


def _parse_json_text(text: str) -> Any | None:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
