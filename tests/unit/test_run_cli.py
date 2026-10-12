import json

from future.orchestrator import run
from future.store import MemoryStore


def test_healthcheck_records_run_and_reports(monkeypatch, tmp_path, capsys):
    store = MemoryStore()
    monkeypatch.setattr(run, "make_store", lambda: (store, "memory"))
    monkeypatch.setattr(run, "LOCK_DIR", tmp_path / "locks")
    monkeypatch.setattr(run, "LOCAL_LOG", tmp_path / "runs.jsonl")
    monkeypatch.setenv("TRIJYA_HOST", "")
    assert run.main(["--stage", "healthcheck"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["stage"] == "healthcheck" and out["result"]["trijya_awake"] is False
    assert next(iter(store.runs.values()))["status"] == "ok"
    assert (tmp_path / "runs.jsonl").exists()


def test_concurrent_run_is_skipped_cleanly(monkeypatch, tmp_path, capsys):
    from future.orchestrator.stages import InstanceLock
    monkeypatch.setattr(run, "make_store", lambda: (MemoryStore(), "memory"))
    monkeypatch.setattr(run, "LOCK_DIR", tmp_path / "locks")
    monkeypatch.setattr(run, "LOCAL_LOG", tmp_path / "runs.jsonl")
    with InstanceLock(tmp_path / "locks" / "healthcheck.lock"):
        assert run.main(["--stage", "healthcheck"]) == 0
    assert "skip:" in capsys.readouterr().out
