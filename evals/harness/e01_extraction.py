"""E-01: Extractor field accuracy on real messy texts. Dataset is PRIVATE (third-party
phone numbers): private/evals/e01_extraction.json. Writes a summary (no raw text) to
evals/results/<gate>/E-01-<model>.txt. Usage: python evals/harness/e01_extraction.py [model]"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))
from future.agents import extractor as ex  # noqa: E402

FIELDS = ("title", "org", "url", "deadline")


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def match(field, got, want):
    if want is None:
        return got is None
    if got is None:
        return False
    if field == "url":
        return got.rstrip("/.,;") == want.rstrip("/.,;")
    if field == "deadline":
        return got == want
    return norm(want) in norm(got) or norm(got) in norm(want)


def main(model="haiku"):
    data = json.loads((ROOT / "private" / "evals" / "e01_extraction.json").read_text(encoding="utf-8"))
    today = dt.date(2026, 10, 12)
    count_ok = field_ok = field_total = invented = tokens = 0
    lines = []
    for case in data:
        out = ex.extract(case["text"], source=case["source"], today=today, model=model)
        tokens += out.tokens
        got = out.opportunities
        count_ok += len(got) == len(case["expect"])
        for exp in case["expect"]:                       # best-matching record by url, else title
            cand = next((g for g in got if match("url", g.get("url"), exp["url"])), None) or \
                   next((g for g in got if match("title", g.get("title"), exp["title"])), None) or {}
            for f in FIELDS:
                field_total += 1
                ok = match(f, cand.get(f), exp[f])
                field_ok += ok
                invented += (exp[f] is None and cand.get(f) is not None)
        if not case["expect"]:
            invented += len(got)                         # any record from a non-opportunity is invented
        lines.append(f"{case['id']}: expected {len(case['expect'])} got {len(got)} flags={len(out.flags)}")
    acc = field_ok / field_total if field_total else 1.0
    summary = (f"E-01 extraction | model={model} | cases={len(data)} | record-count correct {count_ok}/{len(data)} | "
               f"field accuracy {field_ok}/{field_total} = {acc:.0%} | invented fields/records = {invented} | "
               f"tokens={tokens} (avg {tokens // len(data)})")
    out_dir = ROOT / "evals" / "results" / "G04"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"E-01-{model}.txt").write_text(summary + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(summary)
    print("\n".join(lines))


if __name__ == "__main__":
    main(*(sys.argv[1:] or ["haiku"]))
