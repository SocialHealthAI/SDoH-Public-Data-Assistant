from tools.sdoh_search_merge import interleave_search_results, per_source_cap


def test_per_source_cap_splits_budget():
    assert per_source_cap(20, 3) == 7
    assert per_source_cap(20, 1) == 20


def test_interleave_includes_every_source():
    dc = [{"indicator_id": f"dc{i}", "source": "datacommons"} for i in range(10)]
    cms = [{"indicator_id": f"cms{i}", "source": "cms"} for i in range(10)]
    places = [{"indicator_id": f"places{i}", "source": "cdcplaces"} for i in range(5)]
    merged = interleave_search_results([dc, cms, places], max_results=20)
    assert any(r["source"] == "cdcplaces" for r in merged)
    assert merged[0]["source"] == "datacommons"
    assert merged[1]["source"] == "cms"
    assert merged[2]["source"] == "cdcplaces"
