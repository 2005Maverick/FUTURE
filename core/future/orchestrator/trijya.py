"""trijya-3 availability probe + queue/fallback policy (DESIGN §2, ST01.04.04).

trijya-3 sleeps unpredictably. Before routing GPU work there we probe it; if it
is asleep, work waits up to `max_wait` and then falls back (laptop / Haiku),
unless the job forbids fallback (e.g. local fine-tuning).
"""
from __future__ import annotations

import datetime as dt
import os
import socket
from dataclasses import dataclass
from enum import Enum

SSH_PORT = 22
OLLAMA_PORT = 11434
SEARXNG_PORT = 8888
DEFAULT_MAX_WAIT = dt.timedelta(hours=6)


def port_open(host: str, port: int, timeout_s: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


@dataclass(frozen=True)
class TrijyaStatus:
    host: str
    awake: bool
    services: dict[str, bool]

    def ready(self, service: str) -> bool:
        return self.awake and self.services.get(service, False)


def probe(host: str | None = None, services: dict[str, int] | None = None, timeout_s: float = 3.0) -> TrijyaStatus:
    host = host or os.environ.get("TRIJYA_HOST", "")
    if not host:
        return TrijyaStatus(host="", awake=False, services={})
    services = services if services is not None else {"ollama": OLLAMA_PORT, "searxng": SEARXNG_PORT}
    awake = port_open(host, SSH_PORT, timeout_s)
    return TrijyaStatus(host=host, awake=awake,
                        services={name: awake and port_open(host, port, timeout_s) for name, port in services.items()})


class Route(str, Enum):
    TRIJYA = "trijya"
    WAIT = "wait"
    FALLBACK = "fallback"


def decide(status: TrijyaStatus, service: str, queued_at: dt.datetime, now: dt.datetime, *,
           max_wait: dt.timedelta = DEFAULT_MAX_WAIT, fallback_allowed: bool = True) -> Route:
    if status.ready(service):
        return Route.TRIJYA
    if not fallback_allowed:
        return Route.WAIT
    return Route.WAIT if now - queued_at < max_wait else Route.FALLBACK
