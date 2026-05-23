import pytest

pytest.importorskip("langchain")
try:
    from langchain.tools import StructuredTool  # noqa: F401
except ImportError:
    pytest.skip("langchain.tools.StructuredTool not available", allow_module_level=True)

from unittest.mock import patch

from tools.resolve_places_tool import PlacesRequest, ResolvePlacesForMapTool


def _make_tool() -> ResolvePlacesForMapTool:
    return ResolvePlacesForMapTool()


@patch("tools.resolve_places_tool.fetch_property_values_map", return_value={})
def test_resolve_zip_ids(mock_names):
    tool = _make_tool()
    out = tool._run(places=PlacesRequest(level="zip", ids=["45202", "45214"]))
    dcids = [r["dcid"] for r in out["resolved"]]
    assert dcids == ["zip/45202", "zip/45214"]
    assert all(r["place_key"] == r["dcid"] for r in out["resolved"])
    mock_names.assert_called_once()


@patch("tools.resolve_places_tool.fetch_property_values_map", return_value={})
def test_resolve_tract_ids(mock_names):
    tool = _make_tool()
    out = tool._run(
        places=PlacesRequest(level="tract", ids=["39061000200", "geoId/39061000201"])
    )
    dcids = [r["dcid"] for r in out["resolved"]]
    assert "geoId/39061000200" in dcids
    assert "geoId/39061000201" in dcids
