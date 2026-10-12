import datetime as dt

import httpx

from future.collectors import openalex as oa
from future.collectors.openalex import OpenAlexLabCollector, aggregate, pick_institution

KEY = "test-key-not-real"
TODAY = lambda: dt.date(2026, 10, 13)  # noqa: E731

MIT = {"id": "https://openalex.org/I1", "display_name": "MIT", "country_code": "US",
       "lineage": ["https://openalex.org/I1"]}
CSAIL = {"id": "https://openalex.org/I11", "display_name": "CSAIL", "country_code": "US",
         "lineage": ["https://openalex.org/I11", "https://openalex.org/I1"]}
IISC = {"id": "https://openalex.org/I2", "display_name": "Indian Institute of Science", "country_code": "IN",
        "lineage": ["https://openalex.org/I2"]}


def ship(aid, name, insts, orcid=None):
    return {"author": {"id": f"https://openalex.org/{aid}", "display_name": name, "orcid": orcid},
            "institutions": insts}


def work(wid, authorships, title=None, year=2026, cited=0, venue="CoRL"):
    return {"id": f"https://openalex.org/{wid}", "title": title or f"Paper {wid}", "publication_year": year,
            "cited_by_count": cited, "authorships": authorships,
            "primary_location": {"source": {"display_name": venue}}}


def author_row(aid, last_known, h=30, works_count=120):
    return {"id": f"https://openalex.org/{aid}", "display_name": aid, "last_known_institutions": last_known,
            "summary_stats": {"h_index": h}, "works_count": works_count}


def page(results, cost=0.001):
    return {"meta": {"count": len(results), "cost_usd": cost}, "results": results}


class Api:
    """Routes /works by topic and /authors by id; records every request."""

    def __init__(self, works_by_topic, authors=(), works_status=200, authors_status=200):
        self.works_by_topic, self.authors = works_by_topic, {a["id"].rsplit("/", 1)[-1]: a for a in authors}
        self.works_status, self.authors_status = works_status, authors_status
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if req.url.path == "/works":
            if self.works_status != 200:
                return httpx.Response(self.works_status)
            topic = req.url.params["search.title_abstract_keywords"]
            pages = self.works_by_topic.get(topic, [[]])
            n = int(req.url.params.get("page", "1"))
            return httpx.Response(200, json=page(pages[n - 1] if n <= len(pages) else []))
        if self.authors_status != 200:
            return httpx.Response(self.authors_status)
        ids = req.url.params["filter"].split(":", 1)[1].split("|")
        return httpx.Response(200, json=page([self.authors[i] for i in ids if i in self.authors], cost=0.0001))


def collector(api, **kw):
    kw.setdefault("api_key", KEY)
    return OpenAlexLabCollector(transport=httpx.MockTransport(api), delay_s=0, sleep=lambda s: None,
                                today=TODAY, **kw)


def test_works_request_uses_scoped_search_year_filter_and_bearer_key_not_url():
    api = Api({"embodied AI": [[]]})
    list(collector(api, topics=["embodied AI"]).collect())
    req = api.requests[0]
    p = req.url.params
    assert req.url.path == "/works"
    assert p["search.title_abstract_keywords"] == "embodied AI"
    assert p["filter"] == "publication_year:2025-2026"
    assert p["sort"] == "relevance_score:desc" and p["per_page"] == "100" and p["page"] == "1"
    assert "authorships" in p["select"]
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    assert KEY not in str(req.url)                       # key never in a URL (logs, errors)


def test_years_override_and_per_page_capped_at_api_max():
    api = Api({"t": [[]]})
    list(collector(api, topics=["t"], years=(2024, 2026), per_page=500).collect())
    assert api.requests[0].url.params["filter"] == "publication_year:2024-2026"
    assert api.requests[0].url.params["per_page"] == "100"


def test_threshold_keeps_authors_with_two_or_more_matching_works():
    works = [work("W1", [ship("A1", "Ada", [MIT]), ship("A2", "Bob", [IISC])]),
             work("W2", [ship("A1", "Ada", [MIT])])]
    api = Api({"t": [works]}, authors=[author_row("A1", [MIT]), author_row("A2", [IISC])])
    c = collector(api, topics=["t"])
    recs = list(c.collect())
    assert [r.external_id for r in recs] == ["A1"]
    assert recs[0].payload["works"] == 2
    assert c.stats["candidates"] == 1 and c.stats["authors_seen"] == 2


def test_same_work_found_by_two_topics_counts_once_and_lists_both_topics():
    w1 = work("W1", [ship("A1", "Ada", [MIT])])
    w2 = work("W2", [ship("A1", "Ada", [MIT])])
    api = Api({"embodied AI": [[w1, w2]], "LLM alignment": [[w1]]}, authors=[author_row("A1", [MIT])])
    recs = list(collector(api, topics=["embodied AI", "LLM alignment"]).collect())
    assert len(recs) == 1
    p = recs[0].payload
    assert p["works"] == 2                               # W1 not double-counted
    assert p["departments"] == ["embodied AI", "LLM alignment"]
    assert p["title"] == "Research outreach: Ada — embodied AI"


def test_single_work_matched_by_two_topics_does_not_pass_threshold():
    w1 = work("W1", [ship("A1", "Ada", [MIT])])
    api = Api({"a": [[w1]], "b": [[w1]]})
    assert list(collector(api, topics=["a", "b"]).collect()) == []


def test_preprint_and_published_versions_of_one_paper_count_once():
    a = [ship("A1", "Ada", [MIT])]
    versions = [work("W1", a, title="Assessing Vision-Language Models", cited=2),
                work("W2", a, title="Assessing Vision–Language Models", cited=9, venue="IEEE RA-L")]
    assert list(collector(Api({"t": [versions]}), topics=["t"], enrich=False).collect()) == []
    agg = aggregate([("t", w) for w in versions])["https://openalex.org/A1"]
    [kept] = agg.papers.values()
    assert kept.venue == "IEEE RA-L"                     # the most-cited version wins


def test_huge_author_lists_do_not_count():
    crowd = [ship(f"A{i}", f"P{i}", [MIT]) for i in range(30)]
    api = Api({"t": [[work("W1", crowd), work("W2", crowd)]]})
    assert list(collector(api, topics=["t"]).collect()) == []


def test_payload_shape_url_and_summary():
    works = [work("W1", [ship("A1", "Ada", [CSAIL], orcid="https://orcid.org/0000-0001")], title="VLA policies",
                  year=2026, cited=50, venue="CoRL"),
             work("W2", [ship("A1", "Ada", [CSAIL], orcid="https://orcid.org/0000-0001")], title="Robot evals",
                  year=2025, cited=5, venue=None)]
    api = Api({"t": [works]}, authors=[author_row("A1", [MIT], h=42)])
    r = list(collector(api, topics=["t"]).collect())[0]
    p = r.payload
    assert r.source == "openalex" and r.external_id == "A1" and r.url == "https://orcid.org/0000-0001"
    assert {k: p[k] for k in ("board", "org", "location", "offices", "track", "opp_type", "updated_at",
                              "first_published")} == {
        "board": "openalex", "org": "MIT", "location": "United States", "offices": [], "track": "research",
        "opp_type": "lab_outreach", "updated_at": None, "first_published": None}
    assert p["h_index"] == 42 and [t["title"] for t in p["top_papers"]] == ["VLA policies", "Robot evals"]
    assert "VLA policies (2026, CoRL, 50 citations)" in p["content_html"]
    assert "Robot evals (2025, 5 citations)" in p["content_html"] and "<" not in p["content_html"]


def test_url_falls_back_to_openalex_page_without_orcid():
    works = [work("W1", [ship("A1", "Ada", [MIT])]), work("W2", [ship("A1", "Ada", [MIT])])]
    r = list(collector(Api({"t": [works]}, authors=[author_row("A1", [MIT])]), topics=["t"]).collect())[0]
    assert r.url == "https://openalex.org/A1"


def test_content_hash_ignores_volatile_author_stats():
    works = [work("W1", [ship("A1", "Ada", [MIT])]), work("W2", [ship("A1", "Ada", [MIT])])]
    h1 = list(collector(Api({"t": [works]}, authors=[author_row("A1", [MIT], h=10)]), topics=["t"]).collect())[0]
    h2 = list(collector(Api({"t": [works]}, authors=[author_row("A1", [MIT], h=11)]), topics=["t"]).collect())[0]
    assert h1.content_hash == h2.content_hash


def test_author_lookup_batches_ids_and_drops_authors_without_last_known_institution():
    works = [work(f"W{i}", [ship("A1", "Ada", [MIT]), ship("A2", "Bob", [IISC]), ship("A3", "Cy", [IISC])])
             for i in range(2)]
    api = Api({"t": [works]}, authors=[author_row("A1", [MIT]), author_row("A2", []), author_row("A3", [IISC])])
    c = collector(api, topics=["t"], author_batch=2)
    recs = list(c.collect())
    author_calls = [r for r in api.requests if r.url.path == "/authors"]
    assert len(author_calls) == 2                          # 3 ids in batches of 2
    assert author_calls[0].url.params["filter"].startswith("ids.openalex:")
    assert sorted(r.external_id for r in recs) == ["A1", "A3"]
    assert c.stats["no_institution"] == 1


def test_current_institution_prefers_lineage_match_then_first_last_known():
    agg = aggregate([("t", work("W1", [ship("A1", "Ada", [CSAIL])]))])["https://openalex.org/A1"]
    assert pick_institution(agg, [IISC, MIT]).name == "MIT"        # CSAIL's lineage contains MIT
    assert pick_institution(agg, [IISC]).name == "CSAIL"           # mismatch: trust the recent works
    assert pick_institution(agg, []) is None                         # looked up, nothing current
    assert pick_institution(agg, None).name == "CSAIL"               # not looked up: works affiliation
    bare = aggregate([("t", work("W1", [ship("A1", "Ada", [])]))])["https://openalex.org/A1"]
    assert pick_institution(bare, [IISC]).name == "Indian Institute of Science"   # works carry no affiliation
    assert pick_institution(bare, None) is None


def test_author_lookup_failure_falls_back_to_works_affiliation():
    works = [work("W1", [ship("A1", "Ada", [IISC])]), work("W2", [ship("A1", "Ada", [IISC])])]
    c = collector(Api({"t": [works]}, authors_status=500), topics=["t"])
    recs = list(c.collect())
    assert len(recs) == 1 and recs[0].payload["org"] == "Indian Institute of Science"
    assert recs[0].payload["location"] == "India"
    assert c.report.units_failed == 1 and any("authors" in e for e in c.report.errors)


def test_works_errors_are_recorded_not_raised_and_never_contain_the_key():
    c = collector(Api({}, works_status=429), topics=["a", "b"])
    assert list(c.collect()) == []
    assert c.report.units_failed == 2 and c.report.units_ok == 0
    assert all(KEY not in e for e in c.report.errors)


def test_client_error_is_reported_with_status():
    c = collector(Api({}, works_status=400), topics=["a"])
    list(c.collect())
    assert c.report.errors == ["'a' p1: HTTPStatusError 400"]


def test_paging_stops_on_short_page_and_respects_pages_per_topic():
    full = [work(f"W{i}", [ship("A1", "Ada", [MIT])]) for i in range(3)]
    api = Api({"t": [full, full, full, full]})
    list(collector(api, topics=["t"], per_page=3, pages_per_topic=2, enrich=False).collect())
    assert [r.url.params["page"] for r in api.requests] == ["1", "2"]
    api2 = Api({"t": [full[:1]]})
    list(collector(api2, topics=["t"], per_page=3, pages_per_topic=5, enrich=False).collect())
    assert len(api2.requests) == 1


def test_request_cap_reserves_author_lookups_and_cost_is_summed():
    w = [work("W1", [ship("A1", "Ada", [MIT])]), work("W2", [ship("A1", "Ada", [MIT])])]
    topics = [f"t{i}" for i in range(10)]
    api = Api({t: [w] for t in topics}, authors=[author_row("A1", [MIT])])
    c = collector(api, topics=topics, max_requests=oa.ENRICH_RESERVE + 3)
    recs = list(c.collect())
    works_calls = [r for r in api.requests if r.url.path == "/works"]
    assert len(works_calls) == 3 and len(api.requests) == 4 <= c.max_requests
    assert c.requests == 4 and abs(c.cost_usd - 0.0031) < 1e-9
    assert len(recs) == 1 and any("budget reached" in e for e in c.report.errors)


def test_cost_cap_stops_searching():
    api = Api({f"t{i}": [[]] for i in range(5)})
    c = collector(api, topics=[f"t{i}" for i in range(5)], max_cost_usd=0.002)
    list(c.collect())
    assert len(api.requests) == 2


def test_missing_key_runs_keyless_and_says_so():
    api = Api({"t": [[]]})
    c = collector(api, topics=["t"], api_key="")
    list(c.collect())
    assert "Authorization" not in api.requests[0].headers
    assert any("no OPENALEX_API_KEY" in e for e in c.report.errors)
