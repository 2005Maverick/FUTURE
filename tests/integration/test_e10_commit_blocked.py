"""E-10 (HARD BLOCK): a commit containing a secret or phone number must be rejected
by the real git hook; a clean commit must succeed. Runs in a throwaway repo that
uses this project's hook and scanner."""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "precommit_scan.py", repo / "scripts")
    hooks = repo / ".githooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" scripts/precommit_scan.py\n')
    hook.chmod(0o755)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    git(repo, "config", "core.hooksPath", ".githooks")
    return repo


def test_commit_with_secret_is_blocked(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "leak.py").write_text("TOKEN = '" + "gh" + "p_" + "X" * 36 + "'\n")
    git(repo, "add", "leak.py")
    result = git(repo, "commit", "-m", "leak")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_commit_with_phone_is_blocked(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "notes.md").write_text("reach me at " + "98765" + "43210" + "\n")
    git(repo, "add", "notes.md")
    assert git(repo, "commit", "-m", "phone").returncode != 0


def test_commit_of_private_path_is_blocked(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "private").mkdir()
    (repo / "private" / "x.txt").write_text("hello\n")
    git(repo, "add", "-f", "private/x.txt")
    assert git(repo, "commit", "-m", "private").returncode != 0


def test_clean_commit_succeeds(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "ok.py").write_text("print('hello')\n")
    git(repo, "add", "ok.py")
    result = git(repo, "commit", "-m", "ok")
    assert result.returncode == 0, result.stdout + result.stderr
