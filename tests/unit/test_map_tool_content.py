from types import SimpleNamespace

import pytest

pytest.importorskip("langchain")
pytest.importorskip("sdoh_core")

from tools.dc_v2_helpers import flatten_str_ids
from tools.map_tool import MapTool


def test_flatten_str_ids_nested_lists():
    assert flatten_str_ids([["geoId/18001", "geoId/18003"], "geoId/18"]) == [
        "geoId/18001",
        "geoId/18003",
        "geoId/18",
    ]
    assert flatten_str_ids(None) == []


def test_map_tool_accepts_list_content_blocks():
    code = (
        "```python\n"
        "gdf = gpd.GeoDataFrame.from_features(GEOJSON_DATA[\"features\"])\n"
        "merged.plot(column='value', ax=ax, legend=True)\n"
        "```"
    )

    class FakeLLM:
        def invoke(self, _messages):
            return SimpleNamespace(
                content=[{"type": "text", "text": f"Indiana diabetes map.\n{code}"}]
            )

    tool = MapTool(llm=FakeLLM())
    raw = tool._run(
        user_input="choropleth of Indiana counties",
        data={"columns": ["dcid", "value"], "rows": [["geoId/18001", 12.3]]},
        geojson_ref="geojson_test",
        outline_geojson_ref="geojson_outline",
        region_type="US_COUNTIES",
    )
    import json

    out = json.loads(raw)
    assert out["status"] == "success"
    assert "from_features" in (out.get("code_block") or "")
