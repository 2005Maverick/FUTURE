"""Offline tests for the headless Claude runner's safety and command shape."""
import pytest

from future.llm import claude_runner as cr


def test_api_key_present_refuses_to_run():
    with pytest.raises(cr.ApiKeyPresentError):
        cr.clean_env({"ANTHROPIC_API_KEY": "x" * 10, "PATH": "p"})


def test_app_injected_vars_are_stripped_and_others_kept():
    env = cr.clean_env({
        "ANTHROPIC_BASE_URL": "http://proxy", "CLAUDE_CODE_SESSION_ID": "s",
        "CLAUDECODE": "1", "PATH": "p", "USERPROFILE": "u",
    })
    assert env == {"PATH": "p", "USERPROFILE": "u"}


def test_empty_api_key_is_not_treated_as_present():
    assert cr.clean_env({"ANTHROPIC_API_KEY": "", "PATH": "p"}) == {"PATH": "p"}


def test_command_is_lean_and_uses_full_model_ids(monkeypatch):
    monkeypatch.setattr(cr, "claude_executable", lambda: "claude")
    cmd = cr.build_command("hi", "haiku", "sys", {"type": "object"})
    assert cmd[cmd.index("--model") + 1] == "claude-haiku-5-5"
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    for flag in ["--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence", "--json-schema"]:
        assert flag in cmd


def test_json_text_fallback_parsing():
    assert cr._parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert cr._parse_json_text("not json") is None
