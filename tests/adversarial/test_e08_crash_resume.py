"""E-08: kill a stage mid-run, re-run it, and prove no item is lost and none is
processed more than twice (at most the single in-flight item repeats)."""
import collections
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from future.orchestrator.stages import (InstanceLock, JsonlProgress, LockHeld, MemoryProgress,
                                         pid_alive, process_items)

WORKER = Path(__file__).with_name("crash_worker.py")


def test_real_kill_then_resume_loses_nothing(tmp_path):
    child = subprocess.Popen([sys.executable, str(WORKER), str(tmp_path)])
    time.sleep(0.9)                       # let it get partway (~8 of 20 items)
    child.kill()
    child.wait()
    first_pass = JsonlProgress(tmp_path / "progress.jsonl").done_keys("crashtest")
    assert 0 < len(first_pass) < 20, f"kill landed outside the run window: {len(first_pass)} done"

    subprocess.run([sys.executable, str(WORKER), str(tmp_path)], check=True, timeout=60)

    done = JsonlProgress(tmp_path / "progress.jsonl").done_keys("crashtest")
    assert done == {f"item-{i}" for i in range(20)}
    counts = collections.Counter(json.loads(l)["key"] for l in (tmp_path / "out.jsonl").read_text().splitlines() if l)
    assert set(counts) == done                                   # nothing lost
    assert max(counts.values()) <= 2                             # at most the in-flight item repeats
    assert sum(1 for c in counts.values() if c == 2) <= 1


def test_failed_items_are_retried_next_run_and_others_complete():
    progress, seen = MemoryProgress(), []
    flaky = {"b"}

    def handler(x):
        if x in flaky:
            raise ValueError("transient")
        seen.append(x)

    r1 = process_items("s", ["a", "b", "c"], key=str, handler=handler, progress=progress)
    assert r1.processed == 2 and r1.failed[0][0] == "b"
    flaky.clear()
    r2 = process_items("s", ["a", "b", "c"], key=str, handler=handler, progress=progress)
    assert r2.processed == 1 and r2.skipped_done == 2 and seen == ["a", "c", "b"]


def test_torn_last_line_is_ignored(tmp_path):
    p = tmp_path / "progress.jsonl"
    p.write_text('{"stage": "s", "key": "a"}\n{"stage": "s", "ke')
    assert JsonlProgress(p).done_keys("s") == {"a"}


def test_lock_is_exclusive_and_released(tmp_path):
    path = tmp_path / "run.lock"
    with InstanceLock(path):
        with pytest.raises(LockHeld):
            InstanceLock(path).acquire()
    with InstanceLock(path):              # re-acquirable after release
        pass


def test_stale_lock_from_dead_process_is_broken(tmp_path):
    path = tmp_path / "run.lock"
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    assert not pid_alive(dead.pid)
    path.write_text(json.dumps({"pid": dead.pid, "at": time.time()}))
    with InstanceLock(path):
        pass


def test_pid_alive_for_self():
    import os
    assert pid_alive(os.getpid())
