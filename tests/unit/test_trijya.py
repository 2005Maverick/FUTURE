import datetime as dt
import socket
import threading

from future.orchestrator import trijya as t

NOW = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)


def status(awake, **services):
    return t.TrijyaStatus(host="h", awake=awake, services=services)


def test_ready_service_routes_to_trijya():
    assert t.decide(status(True, ollama=True), "ollama", NOW, NOW) is t.Route.TRIJYA


def test_awake_but_service_down_waits_then_falls_back():
    st = status(True, ollama=False)
    assert t.decide(st, "ollama", NOW - dt.timedelta(hours=1), NOW) is t.Route.WAIT
    assert t.decide(st, "ollama", NOW - dt.timedelta(hours=7), NOW) is t.Route.FALLBACK


def test_asleep_waits_until_max_wait_then_falls_back():
    st = status(False)
    assert t.decide(st, "ollama", NOW - dt.timedelta(hours=5, minutes=59), NOW) is t.Route.WAIT
    assert t.decide(st, "ollama", NOW - dt.timedelta(hours=6), NOW) is t.Route.FALLBACK


def test_no_fallback_jobs_wait_forever():
    assert t.decide(status(False), "ollama", NOW - dt.timedelta(days=3), NOW,
                    fallback_allowed=False) is t.Route.WAIT


def test_port_open_against_local_listener():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    threading.Thread(target=lambda: srv.accept(), daemon=True).start()
    assert t.port_open("127.0.0.1", port, timeout_s=2)
    srv.close()
    assert not t.port_open("127.0.0.1", port, timeout_s=1)


def test_probe_without_host_is_asleep(monkeypatch):
    monkeypatch.delenv("TRIJYA_HOST", raising=False)
    st = t.probe(host="")
    assert not st.awake and st.services == {}
