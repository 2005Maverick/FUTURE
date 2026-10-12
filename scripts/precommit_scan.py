"""Pre-commit guard: block secrets and personal data from entering this PUBLIC repo.

Scans the *staged* version of every added/changed file. Exits 1 (blocking the
commit) on any finding. Extra personal strings (emails, names of contacts, etc.)
are read from the gitignored `private/pii_denylist.txt`, one per line, so the
denylist itself never becomes public.

Usage:
    python scripts/precommit_scan.py            # scan staged files (hook mode)
    python scripts/precommit_scan.py FILE ...   # scan given files from disk
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DENYLIST_FILE = REPO_ROOT / "private" / "pii_denylist.txt"

# Paths that must never be committed, whatever their content.
BLOCKED_PATH_PATTERNS = [
    re.compile(r"(^|/)private/"),
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"\.(pem|key|p12|pfx)$"),
    re.compile(r"(^|/)Connections\.csv$", re.IGNORECASE),
]

# Content patterns. Each must be specific enough not to fire on normal code/docs.
CONTENT_PATTERNS = {
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "kaggle_token": re.compile(r"\bKGAT_[a-f0-9]{24,}\b"),
    "openai_or_anthropic_key": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{24,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_\-]{15,}\.eyJ[A-Za-z0-9_\-]{15,}\.[A-Za-z0-9_\-]{10,}"),
    "assigned_secret": re.compile(
        # no leading \b: names like EXA_API_KEY must match; the value must contain
        # a digit so plain identifiers (token = get_token_from_env()) don't fire
        r"(?i)(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*['\"]?(?=[A-Za-z_\-]*\d)[A-Za-z0-9_\-]{16,}"
    ),
    "indian_mobile": re.compile(r"(?<![\d\w])(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?![\d\w])"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

ALLOW_MARKER = "scan:allow"  # put on a line to suppress a reviewed false positive


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.excerpt}"


def load_denylist(path: Path = DENYLIST_FILE) -> list[str]:
    if not path.exists():
        return []
    items = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        item = raw.strip()
        if item and not item.startswith("#"):
            items.append(item.lower())
    return items


def check_path(path: str) -> list[Finding]:
    norm = path.replace("\\", "/")
    return [
        Finding(norm, 0, "blocked_path", pattern.pattern)
        for pattern in BLOCKED_PATH_PATTERNS
        if pattern.search(norm)
    ]


def _mask(text: str) -> str:
    text = text.strip()
    return text if len(text) <= 12 else f"{text[:6]}…{text[-3:]}"


def scan_text(path: str, text: str, denylist: list[str] | None = None) -> list[Finding]:
    denylist = denylist or []
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for kind, pattern in CONTENT_PATTERNS.items():
            match = pattern.search(line)
            if match:
                findings.append(Finding(path, lineno, kind, _mask(match.group(0))))
        lowered = line.lower()
        for item in denylist:
            if item in lowered:
                findings.append(Finding(path, lineno, "denylisted_pii", _mask(item)))
    return findings


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8", "replace")
    return [p for p in out.split("\0") if p]


def staged_content(path: str) -> str | None:
    proc = subprocess.run(["git", "show", f":{path}"], cwd=REPO_ROOT, capture_output=True)
    if proc.returncode != 0:
        return None
    data = proc.stdout
    if b"\0" in data[:8000]:  # binary file: path rules still apply, skip content
        return None
    return data.decode("utf-8", "replace")


def scan_files(paths: list[str], from_index: bool) -> list[Finding]:
    denylist = load_denylist()
    findings: list[Finding] = []
    for path in paths:
        findings.extend(check_path(path))
        if from_index:
            text = staged_content(path)
        else:
            p = Path(path)
            text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        if text is not None:
            findings.extend(scan_text(path, text, denylist))
    return findings


def main(argv: list[str]) -> int:
    from_index = not argv
    paths = staged_files() if from_index else argv
    findings = scan_files(paths, from_index=from_index)
    if findings:
        print("BLOCKED: possible secret or personal data in the commit:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(f"Fix it, move it to private/, or mark a reviewed false positive with '{ALLOW_MARKER}'.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
