import datetime as dt

from future.pipeline.liveness import expired_keys

TODAY = dt.date(2026, 10, 12)


def row(key, source, board, last="2026-10-11"):
    return {"id": f"id-{key}", "dedup_key": key, "details": {"source": source, "board": board}, "last_seen_at": last}


def test_missing_from_healthy_full_feed_board_expires():
    out = expired_keys([row("a", "ashby", "openai"), row("b", "ashby", "openai")], {"a"}, {"ashby": {"openai"}}, TODAY)
    assert out == [("id-b", "no longer listed on ashby/openai")]


def test_failed_board_never_expires_anything():
    """A network error must not look like a closed posting."""
    assert expired_keys([row("b", "ashby", "openai")], set(), {"ashby": {"sarvam"}}, TODAY) == []
    assert expired_keys([row("b", "lever", "cred")], set(), {}, TODAY) == []


def test_search_sources_only_age_out():
    fresh = row("h1", "himalayas", "co1", last="2026-10-05")
    stale = row("h2", "himalayas", "co2", last="2026-09-01")
    out = expired_keys([fresh, stale], set(), {"himalayas": {"anything"}}, TODAY)
    assert [o[0] for o in out] == ["id-h2"]
