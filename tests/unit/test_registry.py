import json

import httpx

from future.collectors import registry as reg


def test_slug_extraction_rules():
    assert reg.slug_from_url("ashby", "https://jobs.ashbyhq.com/OpenAI/abc-123") == "openai"
    assert reg.slug_from_url("greenhouse", "https://boards.greenhouse.io/embed/job_board?for=acme&b=x") == "acme"
    assert reg.slug_from_url("greenhouse", "https://job-boards.greenhouse.io/anthropic/jobs/1") == "anthropic"
    assert reg.slug_from_url("workable", "https://apply.workable.com/j/ABC123") is None     # reserved path
    assert reg.slug_from_url("lever", "https://jobs.lever.co/") is None
    assert reg.slug_from_url("lever", "https://jobs.lever.co/bad%20slug/x") is None


def mock_client(routes):
    def handler(req):
        url = str(req.url)
        for frag, (status, body) in routes.items():
            if frag in url:
                return httpx.Response(status, text=body if isinstance(body, str) else json.dumps(body))
        return httpx.Response(404, text="")
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_harvest_reads_pages_and_retries_502():
    calls = {"n": 0}
    lines = "\n".join(json.dumps({"url": u}) for u in [
        "https://jobs.ashbyhq.com/sarvam/1", "https://jobs.ashbyhq.com/sarvam/2", "https://jobs.ashbyhq.com/openai/9"])

    def handler(req):
        if "showNumPages" in str(req.url):
            calls["n"] += 1
            return httpx.Response(502 if calls["n"] == 1 else 200, text=json.dumps({"pages": 1}))
        return httpx.Response(200, text=lines + "\nnot json")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert reg.harvest_slugs("ashby", ["CC-X"], client, sleep=lambda s: None) == {"sarvam", "openai"}


def test_validate_counts_relevant_india_ok_roles():
    body = {"jobs": [
        {"title": "Machine Learning Engineer", "location": "Bengaluru"},
        {"title": "Research Engineer", "location": "San Francisco"},
        {"title": "Account Executive", "location": "Mumbai"},
        {"title": "AI Engineer", "location": "", "isRemote": True},
    ]}
    s = reg.validate("ashby", "acme", mock_client({"job-board/acme": (200, body)}))
    assert (s.jobs, s.relevant, s.relevant_india_ok, s.error) == (4, 3, 2, None)


def test_validate_records_http_errors():
    s = reg.validate("lever", "gone", mock_client({}))
    assert s.error == "http 404" and s.jobs == 0


def test_selection_and_seed_union(tmp_path, monkeypatch):
    stats = [reg.BoardStats("ashby", "a", 5, 2, 1, "t"), reg.BoardStats("ashby", "b", 5, 2, 0, "t"),
             reg.BoardStats("lever", "c", 1, 1, 1, "t", error="http 404")]
    path = tmp_path / "registry.json"
    reg.save_registry(stats, path)
    assert json.loads(path.read_text())["selected"] == {"ashby": ["a"]}
    seeds = tmp_path / "ashby.txt"
    seeds.write_text("# manual\nopenai\na\n")
    monkeypatch.setattr(reg, "SEEDS_DIR", tmp_path)
    assert reg.seeds_for("ashby", path) == ["openai", "a"]
