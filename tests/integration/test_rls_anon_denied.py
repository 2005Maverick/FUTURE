"""ST01.03.03 (HARD BLOCK): the public/anon key must not read or write any table,
and the owner-check helper must not be exposed as an RPC. Requires a probe row in
`sources` (inserted by the test harness via the service path) to make 'empty'
meaningful; run with FUTURE_RLS_PROBE=1 after inserting it."""
import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")
pytestmark = pytest.mark.skipif(not (URL and KEY), reason="SUPABASE_URL/PUBLISHABLE_KEY not set")
HEADERS = {"apikey": KEY or "", "Authorization": f"Bearer {KEY}"}
TABLES = ["sources", "opportunities", "contacts", "documents", "approvals", "budget_ledger", "app_owner", "settings"]


@pytest.mark.parametrize("table", TABLES)
def test_anon_cannot_read(table):
    r = httpx.get(f"{URL}/rest/v1/{table}?select=*", headers=HEADERS, timeout=20)
    assert r.status_code in (200, 401, 403), r.text
    if r.status_code == 200:
        assert r.json() == [], f"anon read rows from {table}: {r.text[:200]}"


def test_probe_row_exists_but_is_invisible_to_anon():
    if os.getenv("FUTURE_RLS_PROBE") != "1":
        pytest.skip("probe row not inserted for this run")
    r = httpx.get(f"{URL}/rest/v1/sources?name=eq.__anon_deny_probe__", headers=HEADERS, timeout=20)
    assert r.status_code in (200, 401, 403) and (r.status_code != 200 or r.json() == [])


def test_anon_cannot_write():
    r = httpx.post(f"{URL}/rest/v1/sources", headers={**HEADERS, "Content-Type": "application/json"},
                   json={"name": "anon-write-attempt", "kind": "manual"}, timeout=20)
    assert r.status_code in (401, 403), f"anon write not denied: {r.status_code} {r.text[:200]}"


def test_owner_helper_not_exposed_as_rpc():
    r = httpx.post(f"{URL}/rest/v1/rpc/is_owner", headers=HEADERS, json={}, timeout=20)
    assert r.status_code in (401, 403, 404), r.text
