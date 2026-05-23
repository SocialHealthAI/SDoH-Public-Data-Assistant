import pytest

pytest.importorskip("langchain")
try:
    from langchain.tools import StructuredTool  # noqa: F401
except ImportError:
    pytest.skip("langchain.tools.StructuredTool not available", allow_module_level=True)

from unittest.mock import patch

from tools.sdoh_search_tool import SdohSearchTool


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
