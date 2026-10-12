"""Child process for the E-08 crash test: processes 20 items slowly, writing an
idempotent side effect per item (append key to out.jsonl) before marking done."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from future.orchestrator.stages import JsonlProgress, process_items  # noqa: E402

work = Path(sys.argv[1])
out = work / "out.jsonl"


def handler(i: int) -> None:
    time.sleep(0.05)
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"key": f"item-{i}"}) + "\n")
        fh.flush()
    time.sleep(0.05)  # widen the window between side effect and mark_done


process_items("crashtest", range(20), key=lambda i: f"item-{i}", handler=handler,
              progress=JsonlProgress(work / "progress.jsonl"))
