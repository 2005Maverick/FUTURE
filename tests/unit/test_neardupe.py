from future.pipeline import normalize as n
from future.pipeline.neardupe import merge_near_duplicates, norm_org


def opp(org, title, location, source, i):
    raw = {"url": f"https://x/{i}", "content_hash": f"h{i}", "source": source,
           "payload": {"board": org.lower(), "org": org, "title": title, "location": location, "offices": [],
                       "content_html": "<p>Build ML.</p>", "departments": []}}
    return n.from_ats(raw)


def test_same_role_across_sources_merges_and_keeps_ats_record():
    a = opp("OpenAI, Inc.", "Applied AI Engineer - India", "Remote - India", "himalayas", 1)
    b = opp("OpenAI", "Applied AI Engineer", "Delhi, India", "ashby", 2)
    kept, merged = merge_near_duplicates([a, b])
    assert len(kept) == 1 and kept[0].details["source"] == "ashby"
    assert kept[0].raw_hashes == ["h2", "h1"] and merged


def test_different_roles_or_regions_stay_separate():
    a = opp("OpenAI", "Applied AI Engineer", "Delhi, India", "ashby", 1)
    b = opp("OpenAI", "Research Engineer", "Delhi, India", "ashby", 2)          # different role
    c = opp("OpenAI", "Applied AI Engineer", "London, UK", "ashby", 3)           # different region
    d = opp("Cohere", "Applied AI Engineer", "Delhi, India", "ashby", 4)         # different company
    kept, merged = merge_near_duplicates([a, b, c, d])
    assert len(kept) == 4 and not merged


def test_real_false_merges_from_audit_stay_separate():
    """Regression: pairs the first version wrongly merged on live data (S03.05 audit)."""
    pairs = [("Engineering Manager, Data Infrastructure", "Engineering Manager, Inference Infrastructure"),
             ("Applied AI Architect, Beneficial Deployments (Life Sciences)",
              "Applied AI Engineer, Beneficial Deployments (Life Sciences)"),
             ("Commercial Counsel, GTM", "Commercial Counsel, Hardware"),
             ("Director, Revenue Accounting", "Director, Technical Revenue Accounting")]
    for i, (t1, t2) in enumerate(pairs):
        # same source (one board) AND cross-source variants must both stay separate
        for s2 in ("greenhouse", "himalayas"):
            kept, merged = merge_near_duplicates([opp("Anthropic", t1, "San Francisco, CA", "greenhouse", 10 * i),
                                                  opp("Anthropic", t2, "San Francisco, CA", s2, 10 * i + 1)])
            assert len(kept) == 2, (t1, t2, s2, merged)


def test_org_normalisation():
    assert norm_org("Sarvam AI Pvt. Ltd.") == norm_org("Sarvam AI")
