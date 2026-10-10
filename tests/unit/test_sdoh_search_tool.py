import pytest

pytest.importorskip("langchain")
try:
    from langchain.tools import StructuredTool  # noqa: F401
except ImportError:
    pytest.skip("langchain.tools.StructuredTool not available", allow_module_level=True)

from unittest.mock import patch

from tools.sdoh_search_tool import (
    PlaceScope,
    SdohSearchTool,
    _table_rows_as_dicts,
    dc_search_places,
)


class _StubTool:
    pass


def _make_search_tool() -> SdohSearchTool:
    return SdohSearchTool(dc_search_tool=_StubTool(), dc_observations_tool=None)


def _dc_bucket(n: int):
    return [{"indicator_id": f"dc{i}", "source": "datacommons", "name": f"DC {i}"} for i in range(n)]


def _cms_bucket(n: int):
    return [{"indicator_id": f"cms{i}", "source": "cms", "name": f"CMS {i}"} for i in range(n)]


def _places_bucket(n: int):
    return [
        {
            "indicator_id": f"cdcplaces:county/FOODINSECU{i}/CrdPrv",
            "source": "cdcplaces",
            "name": f"Food insecurity {i}",
        }
        for i in range(n)
    ]


def test_run_interleaves_dc_cms_cdcplaces():
    tool = _make_search_tool()
    tool._call_dc_search = lambda **kwargs: {"variables": []}  # type: ignore[method-assign]
    tool._normalize_dc_results = lambda *a, **k: _dc_bucket(10)  # type: ignore[method-assign]
    tool._search_cms = lambda **kwargs: _cms_bucket(10)  # type: ignore[method-assign]

    with patch(
        "tools.sdoh_search_tool.search_cdc_places_catalog",
        return_value=_places_bucket(5),
    ):
        out = tool._run(
            query="food insecurity county",
            sources=["datacommons", "cms", "cdcplaces"],
            max_results=20,
        )

    results = out["results"]
    assert len(results) == 20
    assert any(r["source"] == "cdcplaces" for r in results)
    assert results[0]["source"] == "datacommons"
    assert results[1]["source"] == "cms"
    assert results[2]["source"] == "cdcplaces"


def test_run_per_source_cap_warning():
    tool = _make_search_tool()
    tool._call_dc_search = lambda **kwargs: {"variables": []}  # type: ignore[method-assign]
    tool._normalize_dc_results = lambda *a, **k: _dc_bucket(3)  # type: ignore[method-assign]
    tool._search_cms = lambda **kwargs: _cms_bucket(3)  # type: ignore[method-assign]

    with patch("tools.sdoh_search_tool.search_cdc_places_catalog", return_value=_places_bucket(3)):
        out = tool._run(
            query="loneliness",
            sources=["datacommons", "cms"],
            max_results=20,
        )

    assert any("interleaved" in w for w in out["warnings"])
    assert any("per source" in w and "max_results=20" in w for w in out["warnings"])


def test_run_unsupported_source_warning():
    tool = _make_search_tool()
    tool._call_dc_search = lambda **kwargs: {"variables": []}  # type: ignore[method-assign]
    tool._normalize_dc_results = lambda *a, **k: _dc_bucket(2)  # type: ignore[method-assign]

    out = tool._run(
        query="diabetes",
        sources=["datacommons", "ihme"],
        max_results=10,
    )

    assert "datacommons" in out["sources_checked"]
    assert "ihme" not in out["sources_checked"]
    assert any("ihme" in w.lower() and "not supported" in w.lower() for w in out["warnings"])
    assert any("datacommons" in w and "cdcplaces" in w for w in out["warnings"])
    assert len(out["results"]) >= 1


def test_run_cdcplaces_only():
    tool = _make_search_tool()
    tool._call_dc_search = lambda **kwargs: {"variables": []}  # type: ignore[method-assign]
    tool._normalize_dc_results = lambda *a, **k: []  # type: ignore[method-assign]

    with patch(
        "tools.sdoh_search_tool.search_cdc_places_catalog",
        return_value=_places_bucket(3),
    ):
        out = tool._run(
            query="food insecurity county",
            sources=["cdcplaces"],
            max_results=10,
        )

    assert out["sources_checked"] == ["cdcplaces"]
    assert any("FOODINSECU" in r["indicator_id"] for r in out["results"])
    assert all(r["source"] == "cdcplaces" for r in out["results"])


def test_table_rows_as_dicts_maps_columns():
    table = {
        "columns": ["dcid", "name", "placesWithData"],
        "rows": [
            ["Count_Person", "population count", []],
            ["Count_Person_PerArea", "Population Density", []],
        ],
    }
    rows = _table_rows_as_dicts(table)
    assert rows[0]["dcid"] == "Count_Person"
    assert rows[1]["name"] == "Population Density"


def test_dc_search_places_defaults_to_united_states():
    assert dc_search_places(None) == ["United States"]
    assert dc_search_places(PlaceScope()) == ["United States"]
    assert dc_search_places(PlaceScope(within="Franklin County, OH")) == ["Franklin County, OH"]


def test_normalize_variable_candidates_table():
    tool = _make_search_tool()
    raw = {
        "status": "SUCCESS",
        "variableCandidates": {
            "columns": ["dcid", "name", "placesWithData", "observationProperties"],
            "rows": [
                ["Count_Person", "population count", {"value": [], "Count": 0}, {"value": [], "Count": 0}],
                ["Median_Age_Person", "Median age of population", {"value": [], "Count": 0}, {}],
            ],
        },
        "topicCandidates": {
            "columns": ["dcid", "name", "memberVariables"],
            "rows": [["dc/topic/Demographics", "Demographics", ["Count_Person_Female"]]],
        },
    }
    items = tool._normalize_dc_results(raw, max_results=10, include_metric_source=False)
    native_ids = [i["native_id"] for i in items]
    assert native_ids[:2] == ["Count_Person", "Median_Age_Person"]
    assert items[0]["name"] == "population count"
    assert "Count_Person_Female" in native_ids


def test_normalize_place_scoped_camel_case_payload():
    tool = _make_search_tool()
    raw = {
        "status": "SUCCESS",
        "dcidNameMappings": {
            "Count_Person": "population count",
            "Count_Person_PerArea": "Population Density",
        },
        "topics": [
            {
                "dcid": "dc/topic/Demographics",
                "memberVariables": ["Count_Person_Female"],
                "description": "Demographics",
            }
        ],
        "variables": [
            {"dcid": "Count_Person", "placesWithData": ["country/USA"]},
            {"dcid": "Count_Person_PerArea", "placesWithData": ["country/USA"]},
        ],
    }
    items = tool._normalize_dc_results(raw, max_results=10, include_metric_source=False)
    by_id = {i["native_id"]: i for i in items}
    assert by_id["Count_Person"]["name"] == "population count"
    assert by_id["Count_Person_PerArea"]["name"] == "Population Density"
    assert "Count_Person_Female" in by_id


def test_normalize_legacy_snake_case_payload():
    tool = _make_search_tool()
    raw = {
        "variables": [{"dcid": "Count_Person"}],
        "dcid_name_mappings": {"Count_Person": "Total population"},
    }
    items = tool._normalize_dc_results(raw, max_results=5, include_metric_source=False)
    assert items == [
        {
            "indicator_id": "datacommons:Count_Person",
            "source": "datacommons",
            "native_id": "Count_Person",
            "name": "Total population",
            "type": "StatisticalVariable",
            "description": None,
            "repository": {"name": "Data Commons"},
            "metric_source": None,
        }
    ]


def test_run_forwards_default_and_explicit_places():
    tool = _make_search_tool()
    captured: dict = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return {"variables": [{"dcid": "Count_Person"}], "dcidNameMappings": {"Count_Person": "population count"}}

    tool._call_dc_search = _capture  # type: ignore[method-assign]
    tool._search_cms = lambda **kwargs: []  # type: ignore[method-assign]

    out = tool._run(query="population", sources=["datacommons"], max_results=5, include_metric_source=False)
    assert captured["places"] == ["United States"]
    assert any("United States" in w for w in out["warnings"])
    assert out["results"][0]["native_id"] == "Count_Person"

    captured.clear()
    out = tool._run(
        query="population",
        sources=["datacommons"],
        place_scope=PlaceScope(within="Ohio"),
        max_results=5,
        include_metric_source=False,
    )
    assert captured["places"] == ["Ohio"]
    assert not any("United States" in w for w in out["warnings"])
