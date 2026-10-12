"""S04.05: the page watcher emits a record only when a page's meaningful text changes."""
import json

import httpx
import pytest

from future.collectors import pagewatch as pw
from future.collectors.base import SEEDS_DIR

BODY = " ".join(["Applications for the summer research internship open in January."] * 6)


def page_html(body=BODY, title="Research Internship", script="var t = 1;", extra=""):
    return (f"<html><head><title>{title}</title><style>p{{color:red}}</style><script>{script}</script></head>"
            f"<body><nav>Home | About | Contact</nav><main><h1>{title}</h1><p>{body}</p>{extra}</main>"
            f"<footer>Copyright 2026</footer></body></html>")


PAGES = [
    {"id": "oist", "url": "https://example.org/oist", "track": "research", "org": "OIST", "kind": "programme"},
    {"id": "daad", "url": "https://example.org/daad", "track": "research", "org": "DAAD", "kind": "scholarship"},
    {"id": "yc", "url": "https://example.org/yc", "track": "funding", "org": "Y Combinator", "kind": "accelerator"},
]


def make_client(routes):
    """routes: {path: html str | int status | Exception}."""
    def handler(req):
        val = routes.get(req.url.path)
        if val is None:
            return httpx.Response(404)
        if isinstance(val, Exception):
            raise val
        if isinstance(val, int):
            return httpx.Response(val)
        return httpx.Response(200, text=val)
    return httpx.Client(transport=httpx.MockTransport(handler))


def run(routes, state_path, pages=PAGES, **kw):
    c = pw.PageWatchCollector(pages=pages, client=make_client(routes), state_path=state_path,
                              delay_s=0, sleep=lambda s: None, **kw)
    return c, list(c.collect())


@pytest.fixture
def state(tmp_path):
    return tmp_path / "pagewatch" / "state.json"


def all_ok():
    return {"/oist": page_html(), "/daad": page_html(title="WISE"), "/yc": page_html(title="Apply")}


def test_first_run_emits_every_page_with_common_payload_shape(state):
    c, recs = run(all_ok(), state)
    assert [r.external_id for r in recs] == ["oist", "daad", "yc"]
    assert c.report.units_ok == 3 and c.report.units_failed == 0 and c.report.records == 3
    assert c.report.ok_units == ["oist", "daad", "yc"]
    p = recs[0].payload
    assert recs[0].source == "pagewatch" and recs[0].url == "https://example.org/oist"
    assert p["board"] == "oist" and p["org"] == "OIST" and p["title"] == "Research Internship"
    assert p["location"] == "" and p["offices"] == [] and p["departments"] == ["research"]
    assert p["updated_at"] is None and p["first_published"] is None
    assert p["page_kind"] == "programme" and p["track"] == "research"
    assert "summer research internship" in p["content_html"]
    assert json.loads(state.read_text(encoding="utf-8")).keys() == {"oist", "daad", "yc"}


def test_unchanged_second_run_emits_nothing(state):
    run(all_ok(), state)
    c, recs = run(all_ok(), state)
    assert recs == [] and c.report.units_ok == 3 and c.report.records == 0


def test_changed_text_emits_only_that_page(state):
    run(all_ok(), state)
    routes = {**all_ok(), "/daad": page_html(title="WISE", body=BODY + " Deadline extended to 15 November.")}
    c, recs = run(routes, state)
    assert [r.external_id for r in recs] == ["daad"]
    assert "Deadline extended" in recs[0].payload["content_html"]
    assert c.changed == ["daad"]


def test_content_hash_tracks_text(state):
    _, first = run(all_ok(), state)
    _, again = run(all_ok(), state.with_name("other.json"))
    assert first[0].content_hash == again[0].content_hash
    _, changed = run({**all_ok(), "/oist": page_html(body="Completely new text " * 20)}, state.with_name("x.json"))
    assert changed[0].content_hash != first[0].content_hash


def test_whitespace_script_style_nav_footer_changes_are_not_changes(state):
    run(all_ok(), state)
    noisy = ("<html>\n  <head><title>Research   Internship</title><style>body{margin:0}</style>"
             "<script>window.csrf='abc123-new-token';</script></head>\n<body>\n"
             "<nav>Home | News | Login</nav>\n<main>\n  <h1>Research\n Internship</h1>\n"
             f"<p>\n{BODY.replace(' ', '   ')}\n</p>\n<noscript>enable JS</noscript></main>\n"
             "<footer>Copyright 2027, updated</footer>\n</body></html>")
    c, recs = run({**all_ok(), "/oist": noisy}, state)
    assert recs == [] and c.report.units_ok == 3


def test_failed_fetch_keeps_old_hash_and_is_recorded(state):
    run(all_ok(), state)
    before = json.loads(state.read_text(encoding="utf-8"))["daad"]["hash"]
    routes = {**all_ok(), "/daad": 404}
    c, recs = run(routes, state)
    assert recs == [] and c.report.units_failed == 1 and c.report.units_ok == 2
    assert "daad" not in c.report.ok_units and c.report.errors[0].startswith("daad: PageFetchError: HTTP 404")
    assert json.loads(state.read_text(encoding="utf-8"))["daad"]["hash"] == before


def test_network_error_on_first_sighting_stores_no_hash_and_retries_later(state):
    routes = {**all_ok(), "/yc": httpx.ConnectError("boom")}
    c, recs = run(routes, state)
    assert [r.external_id for r in recs] == ["oist", "daad"] and c.report.units_failed == 1
    assert "ConnectError" in c.report.errors[0]
    assert "yc" not in json.loads(state.read_text(encoding="utf-8"))
    _, recs = run(all_ok(), state)
    assert [r.external_id for r in recs] == ["yc"]


def test_server_error_is_retried_once(state):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, text=page_html())
    c = pw.PageWatchCollector(pages=PAGES[:1], client=httpx.Client(transport=httpx.MockTransport(handler)),
                              state_path=state, delay_s=0, sleep=lambda s: None)
    assert len(list(c.collect())) == 1 and calls["n"] == 2


def test_js_shell_with_too_little_text_is_a_failure(state):
    shell = "<html><head><title>App</title><script>render()</script></head><body><div id=root></div></body></html>"
    c, recs = run({**all_ok(), "/oist": shell}, state)
    assert [r.external_id for r in recs] == ["daad", "yc"]
    assert c.report.units_failed == 1 and "chars of text" in c.report.errors[0]


def test_text_is_truncated_but_hash_covers_full_text(state):
    long_body = "word " * 5000
    _, recs = run({**all_ok(), "/oist": page_html(body=long_body)}, state)
    assert len(recs[0].payload["content_html"]) == pw.MAX_TEXT_CHARS
    # a change beyond the truncation point is still a change
    _, recs = run({**all_ok(), "/oist": page_html(body=long_body + " tail-change")}, state)
    assert [r.external_id for r in recs] == ["oist"]


def test_custom_max_chars(state):
    _, recs = run(all_ok(), state, max_chars=50)
    assert all(len(r.payload["content_html"]) == 50 for r in recs)


def test_title_falls_back_to_id(state):
    html = f"<html><body><p>{BODY}</p></body></html>"
    _, recs = run({**all_ok(), "/oist": html}, state)
    assert recs[0].payload["title"] == "oist"


def test_polite_delay_between_pages(state):
    sleeps = []
    c = pw.PageWatchCollector(pages=PAGES, client=make_client(all_ok()), state_path=state,
                              delay_s=1.5, sleep=sleeps.append)
    list(c.collect())
    assert sleeps == [1.5, 1.5]


def test_html_to_text_strips_chrome_and_keeps_blocks():
    title, text = pw.html_to_text(page_html(extra="<ul><li>Stipend: 3000 EUR</li><li>Duration: 3 months</li></ul>"))
    assert title == "Research Internship"
    assert "var t" not in text and "color:red" not in text and "Home | About" not in text and "Copyright" not in text
    assert "Stipend: 3000 EUR\nDuration: 3 months" in text


def test_rotating_content_outside_main_is_ignored(state):
    run(all_ok(), state)
    rotated = page_html(extra="").replace("</main>", "</main><div class='ad-carousel'>Study at TH Rosenheim</div>")
    c, recs = run({**all_ok(), "/oist": rotated}, state)
    assert recs == []


def test_stub_main_falls_back_to_whole_body():
    html = f"<html><body><main><p>Loading</p></main><div><p>{BODY}</p></div></body></html>"
    _, text = pw.html_to_text(html)
    assert "summer research internship" in text and "Loading" in text


def test_svg_titles_do_not_pollute_page_title():
    html = (f"<html><head><title>Apply to YC</title></head><body><svg><title>Twitter</title></svg>"
            f"<p>{BODY}</p><svg><title>LinkedIn</title></svg></body></html>")
    title, text = pw.html_to_text(html)
    assert title == "Apply to YC" and "Twitter" not in text and "LinkedIn" not in text


def test_unclosed_head_does_not_hide_body():
    _, text = pw.html_to_text(f"<html><head><title>T</title><body><p>{BODY}</p>")
    assert "summer research internship" in text


@pytest.mark.parametrize("bad", [
    {"id": "x", "url": "https://a", "track": "jobs", "org": "o", "kind": "programme"},
    {"id": "x", "url": "https://a", "track": "ms", "org": "o", "kind": "party"},
    {"id": "x", "url": "ftp://a", "track": "ms", "org": "o", "kind": "programme"},
    {"id": "", "url": "https://a", "track": "ms", "org": "o", "kind": "programme"},
])
def test_invalid_seed_entries_are_rejected(bad):
    with pytest.raises(ValueError):
        pw.validate_pages([bad])


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        pw.validate_pages([PAGES[0], PAGES[0]])


def test_shipped_seed_file_is_valid():
    pages = pw.load_pages(SEEDS_DIR / "pagewatch.json")
    assert 20 <= len(pages) <= 30
    assert {p["track"] for p in pages} == {"research", "ms", "funding"}
    assert all(p["url"].startswith("https://") for p in pages)
