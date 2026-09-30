from typing import List, Optional, Dict, Any

from sdoh_core.agent_types import ToolCallingAgent
from sdoh_core.llm_config import (
    build_chat_model,
    build_tool_calling_agent,
    llm_content_to_text,
    llm_provider,
)

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
from prompt_escape import escape_prompt_braces


class ReActAgent:
    """
    Public-data product agent: owns tool wiring and the system prompt.
    LLM factory and tool-calling loop come from sdoh_core.
    """

    def __init__(
        self,
        mcp_uri: str,
        model_name: str | None = None,
        provider: str | None = None,
        temperature: float = 0.0,
        max_iterations: int = 16,
        system_prompt_path: str = "agent_system_prompt.txt",
    ):
        self.mcp_uri = mcp_uri
        self.provider = provider or llm_provider()
        self.temperature = temperature
        self.max_iterations = max_iterations
        self.system_prompt = self._load_system_prompt(system_prompt_path)

        self.llm = build_chat_model(
            provider=self.provider,
            model_name=model_name,
            temperature=temperature,
        )
        self.model_name = getattr(self.llm, "model_name", None) or getattr(
            self.llm, "model", None
        )

        self.chart_tool = None
        self.map_tool = None
        self.tools = self._initialize_tools()

        loop_prompt = ToolCallingAgent._default_system_prompt()
        agent_system_prompt = (
            f"{loop_prompt}\n\n{self.system_prompt}"
            if self.system_prompt
            else loop_prompt
        )
        agent_system_prompt = escape_prompt_braces(agent_system_prompt)

        # force_tool=False so greetings / clarifications need not call a tool.
        self.agent = build_tool_calling_agent(
            self.llm,
            self.tools,
            force_tool=False,
            max_iterations=max_iterations,
            system_prompt=agent_system_prompt,
        )

    def get_chart_tool(self) -> Optional[ChartTool]:
        """Get reference to the chart tool for rendering."""
        return self.chart_tool

    def get_map_tool(self) -> Optional[MapTool]:
        """Get reference to the map tool for rendering."""
        return self.map_tool

    def _load_system_prompt(self, path: str) -> str:
        """Load the system prompt from file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            print(f"Warning: System prompt file not found at {path}. Using empty prompt.")
            return ""

    def _initialize_tools(self) -> List:
        """
        Initialize all tools required by the agent.

        Returns:
            List of initialized tools
        """
        mcp_loader = McpTool(
            server_name="datacommons",
            server_config={
                "url": self.mcp_uri,
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

        self.chart_tool = ChartTool(llm=self.llm)
        self.map_tool = MapTool(llm=self.llm)
        self.geojson_tool = GeoJsonTool()
        self.resolve_places_tool = ResolvePlacesForMapTool()

        return [
            sdoh_search_tool,
            sdoh_observations_tool,
            observations_mcp_tool,
            CorrelationTool(),
            RegressionTool(),
            DescriptiveStatsTool(),
            TimeSeriesTool(),
            self.chart_tool,
            self.map_tool,
            self.resolve_places_tool,
            self.geojson_tool,
        ]

    def run(self, user_prompt: str) -> Dict[str, Any]:
        """
        Run the agent with a user prompt.

        Returns:
            Dict containing 'output' and 'intermediate_steps'
        """
        result = self.agent.run(user_prompt)
        result["output"] = llm_content_to_text(result.get("output"))
        return result

    def get_tool_descriptions_text(self) -> str:
        """
        Return a plain-text description of all tools available to the agent.
        """
        sections = []

        for idx, tool in enumerate(self.tools, start=1):
            if hasattr(tool, "name"):
                name = tool.name
            else:
                name = tool.__class__.__name__

            if hasattr(tool, "description") and tool.description:
                description = tool.description
            elif tool.__doc__:
                description = tool.__doc__
            else:
                description = "No description provided."

            description = " ".join(description.strip().split())
            sections.append(f"Tool {idx}: {name}\nPurpose: {description}")

        return "\n\n".join(sections)
