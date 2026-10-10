"""Public-data tool assembly. The conversation agent is Core ReActAgent."""
from typing import Any, Dict, List, Tuple

from tools.mcp_tool import McpTool
from tools.correlation_tool import CorrelationTool
from tools.regression_tool import RegressionTool
from tools.descriptive_stats_tool import DescriptiveStatsTool
from tools.time_series_tool import TimeSeriesTool
from tools.chart_tool import ChartTool
from tools.map_tool import MapTool
from tools.geojson_tool import GeoJsonTool
from tools.sdoh_search_tool import SdohSearchTool
from tools.sdoh_observations_tool import SdohObservationsTool
from tools.resolve_places_tool import ResolvePlacesForMapTool


def build_public_data_tools(mcp_uri: str, llm: Any) -> Tuple[List[Any], ChartTool, MapTool]:
    """Return LangChain tools plus chart/map handles for AfterTurnHook."""
    mcp_loader = McpTool(
        server_name="datacommons",
        server_config={
            "url": mcp_uri,
            "transport": "streamable_http",
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        },
    )
    indicators_mcp_tool = mcp_loader.get_tool("search_indicators")
    observations_mcp_tool = mcp_loader.get_tool("get_observations")
    sdoh_search_tool = SdohSearchTool(
        dc_search_tool=indicators_mcp_tool,
        dc_observations_tool=observations_mcp_tool,
    )
    sdoh_observations_tool = SdohObservationsTool(
        dc_observations_tool=observations_mcp_tool
    )
    chart_tool = ChartTool(llm=llm)
    map_tool = MapTool(llm=llm)
    tools = [
        sdoh_search_tool,
        sdoh_observations_tool,
        observations_mcp_tool,
        CorrelationTool(),
        RegressionTool(),
        DescriptiveStatsTool(),
        TimeSeriesTool(),
        chart_tool,
        map_tool,
        ResolvePlacesForMapTool(),
        GeoJsonTool(),
    ]
    return tools, chart_tool, map_tool


def tool_descriptions_text(tools: List[Any]) -> str:
    sections = []
    for idx, tool in enumerate(tools, start=1):
        name = tool.name if hasattr(tool, "name") else tool.__class__.__name__
        if hasattr(tool, "description") and tool.description:
            description = tool.description
        elif tool.__doc__:
            description = tool.__doc__
        else:
            description = "No description provided."
        description = " ".join(description.strip().split())
        sections.append(f"Tool {idx}: {name}\nPurpose: {description}")
    return "\n\n".join(sections)


def collect_viz_extras(chart_tool: ChartTool | None, map_tool: MapTool | None) -> Dict[str, Any]:
    extras: Dict[str, Any] = {}
    if chart_tool and getattr(chart_tool, "_latest_result", None):
        latest = chart_tool._latest_result
        if latest and latest.get("code_block"):
            extras["chart_code"] = latest.get("code_block")
    if map_tool and getattr(map_tool, "_latest_result", None):
        latest = map_tool._latest_result
        if latest:
            if latest.get("code_block"):
                extras["map_code"] = latest.get("code_block")
            if latest.get("geojson_ref"):
                extras["map_geojson_ref"] = latest.get("geojson_ref")
            if latest.get("outline_geojson_ref"):
                extras["map_outline_geojson_ref"] = latest.get("outline_geojson_ref")
            if latest.get("data"):
                extras["map_data"] = latest.get("data")
    return extras
