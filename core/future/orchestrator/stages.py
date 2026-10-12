"""Idempotent, resumable item processing + single-instance locking (ST01.04.02).

Contract for handlers: they must be idempotent per item key (write by unique
key / upsert). The runner marks an item done only AFTER its handler returns, so
a crash re-processes at most the in-flight item and never loses one.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol, TypeVar

T = TypeVar("T")


class ProgressStore(Protocol):
    def done_keys(self, stage: str) -> set[str]: ...
    def mark_done(self, stage: str, key: str) -> None: ...


class MemoryProgress:
    def __init__(self) -> None:
        self._done: dict[str, set[str]] = {}

    def done_keys(self, stage):
        return set(self._done.get(stage, set()))

    def mark_done(self, stage, key):
        self._done.setdefault(stage, set()).add(key)


class JsonlProgress:
    """Durable local progress ledger (append-only JSONL, fsync per mark).
    Used for local runs and as the crash-test backend; Supabase-backed progress
    can implement the same protocol."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def done_keys(self, stage):
        if not self.path.exists():
            return set()
        keys = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:  # torn final line after a crash: ignore
                continue
            if rec.get("stage") == stage:
                keys.add(rec["key"])
        return keys

    def mark_done(self, stage, key):
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"stage": stage, "key": key}) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


@dataclass
class StageResult:
    processed: int
    skipped_done: int
    failed: list[tuple[str, str]]


def process_items(stage: str, items: Iterable[T], key: Callable[[T], str], handler: Callable[[T], None],
                  progress: ProgressStore, *, stop_on_error: bool = False) -> StageResult:
    done = progress.done_keys(stage)
    processed = skipped = 0
    failed: list[tuple[str, str]] = []
    for item in items:
        k = key(item)
        if k in done:
            skipped += 1
            continue
        try:
            handler(item)
        except Exception as exc:  # item-level failure: record, keep going (retried next run)
            failed.append((k, f"{type(exc).__name__}: {exc}"))
            if stop_on_error:
                break
            continue
        progress.mark_done(stage, k)
        done.add(k)
        processed += 1
    return StageResult(processed=processed, skipped_done=skipped, failed=failed)


# ---------------- single-instance lock ----------------
class LockHeld(RuntimeError):
    pass


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # NOTE: never use os.kill(pid, 0) on Windows: it TERMINATES the process.
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE = 0x1000, 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class InstanceLock:
    """Exclusive lock file holding {pid, at}. A lock whose PID is dead, or older
    than `stale_after_s`, is broken automatically."""

    def __init__(self, path: Path, stale_after_s: float = 6 * 3600) -> None:
        self.path = Path(path)
        self.stale_after_s = stale_after_s
        self._held = False

    def _try_create(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w") as fh:
            json.dump({"pid": os.getpid(), "at": time.time()}, fh)
        return True

    def acquire(self) -> "InstanceLock":
        if self._try_create():
            self._held = True
            return self
        try:
            info = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            info = {"pid": -1, "at": 0}
        stale = (not pid_alive(int(info.get("pid", -1)))) or (time.time() - float(info.get("at", 0)) > self.stale_after_s)
        if stale:
            self.path.unlink(missing_ok=True)
            if self._try_create():
                self._held = True
                return self
        raise LockHeld(f"{self.path.name} held by pid {info.get('pid')}")

    def release(self) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
