import os
from typing import List, Optional, Dict, Any

from langchain_openai import ChatOpenAI

from agent_types import OpenAIToolCallingAgent
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

class ReActAgent:
    """
    Class for ReAct Agent, handles initialization of the LLM, tools, and the agent itself.
    """
    
    def __init__(
        self,
        mcp_uri: str,
        model_name: str = "gpt-5.2",
        temperature: float = 0.0,
        max_iterations: int = 10,
        system_prompt_path: str = "agent_system_prompt.txt"
    ):
        """
        Initialize the ReAct Agent with all required tools.
        
        Args:
            mcp_uri: MCP server URI
            model_name: OpenAI model name
            temperature: LLM temperature setting
            max_iterations: Maximum agent iterations
            system_prompt_path: Path to system prompt file
        """
        self.mcp_uri = mcp_uri
        self.model_name = model_name
        self.temperature = temperature
        self.max_iterations = max_iterations
        
        # Load system prompt
        self.system_prompt = self._load_system_prompt(system_prompt_path)
        
        # Initialize LLM
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)
        
        # Initialize tools
        self.chart_tool = None
        self.map_tool = None
        self.tools = self._initialize_tools()
        
        # Initialize agent
        self.agent = OpenAIToolCallingAgent(
            tools=self.tools,
            llm=self.llm,
            max_iterations=max_iterations
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
            with open(path, 'r') as f:
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
        all_tools = []
        
        mcp_loader = McpTool(
            server_name="datacommons",
            server_config = {
            "url": self.mcp_uri,
            "transport": "streamable_http", 
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
                }
            }
        )
        indicators_mcp_tool = mcp_loader.get_tool("search_indicators")
        observations_mcp_tool = mcp_loader.get_tool("get_observations")
        sdoh_search_tool = SdohSearchTool(dc_search_tool=indicators_mcp_tool, dc_observations_tool=observations_mcp_tool)
        sdoh_observations_tool = SdohObservationsTool(dc_observations_tool=observations_mcp_tool)

        self.chart_tool = ChartTool(llm=self.llm)
        self.map_tool = MapTool(llm=self.llm)
        self.geojson_tool = GeoJsonTool()
        self.resolve_places_tool = ResolvePlacesForMapTool()

        # Build final tools list
        tools_list = [
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
        
        all_tools.extend(tools_list)
        
        return all_tools
    
    def run(self, user_prompt: str, include_system_prompt: bool = True) -> Dict[str, Any]:
        """
        Run the agent with a user prompt.
        
        Args:
            user_prompt: The user's query/request
            include_system_prompt: Whether to prepend the system prompt
            
        Returns:
            Dict containing 'output' and 'intermediate_steps'
        """
        if include_system_prompt and self.system_prompt:
            full_prompt = f"{self.system_prompt}\n\nUser request:\n{user_prompt}"
        else:
            full_prompt = user_prompt
        
        result = self.agent.run(full_prompt)
        return result
    
    def get_tool_descriptions_text(self) -> str:
        """
        Return a plain-text description of all tools available to the agent.
        """
        sections = []

        for idx, tool in enumerate(self.tools, start=1):
            # ---- Tool name ----
            if hasattr(tool, "name"):
                name = tool.name
            else:
                name = tool.__class__.__name__

            # ---- Description ----
            if hasattr(tool, "description") and tool.description:
                description = tool.description
            elif tool.__doc__:
                description = tool.__doc__
            else:
                description = "No description provided."

            # Normalize whitespace for LLMs
            description = " ".join(description.strip().split())

            section = (
                f"Tool {idx}: {name}\n"
                f"Purpose: {description}"
            )

            sections.append(section)

        return "\n\n".join(sections)
