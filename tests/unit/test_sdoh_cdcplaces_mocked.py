import pytest

pytest.importorskip("langchain")
try:
    from langchain.tools import StructuredTool  # noqa: F401
except ImportError:
    pytest.skip("langchain.tools.StructuredTool not available", allow_module_level=True)

from unittest.mock import patch

from tools.sdoh_observations_tool import SdohObservationsTool
from tools.sdoh_search_tool import SdohSearchTool


class _StubTool:
    pass


@patch("tools.sdoh_observations_tool.fetch_places_observations_batched")
def test_cdcplaces_observations_county(mock_fetch):
    mock_fetch.return_value = [
        {
            "locationid": "18001",
            "locationname": "Clark",
            "year": "2023",
            "data_value": "14.2",
            "data_value_unit": "%",
            "data_value_type": "Age-adjusted prevalence",
            "datavaluetypeid": "AgeAdjPrv",
            "measureid": "LONELINESS",
            "datasource": "BRFSS",
            "category": "Health-Related Social Needs",
        }
    ]
    tool = SdohObservationsTool(dc_observations_tool=_StubTool())
    out = tool._run(
        indicators=["cdcplaces:county/LONELINESS/AgeAdjPrv"],
        place={"level": "county", "ids": ["geoId/18001"]},
        time={"year": 2023},
        sources=["cdcplaces"],
    )
    rows = out["data"]["rows"]
    assert len(rows) == 1
    assert rows[0]["place_key"] == "geoId/18001"
    assert rows[0]["year"] == 2023
    assert rows[0]["value"] == 14.2
    assert rows[0]["source"] == "cdcplaces"


def test_search_includes_cdcplaces():
    tool = SdohSearchTool(dc_search_tool=_StubTool(), dc_observations_tool=None)
    tool._call_dc_search = lambda **kwargs: {"variables": []}  # type: ignore[method-assign]
    tool._normalize_dc_results = lambda *a, **k: []  # type: ignore[method-assign]
    out = tool._run(query="food insecurity county", sources=["cdcplaces"], max_results=10)
    assert "cdcplaces" in out["sources_checked"]
    assert any("FOODINSECU" in r["indicator_id"] for r in out["results"])
