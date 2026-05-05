import os
from typing import Optional, Any
from pydantic import PrivateAttr

from langchain_core.tools import BaseTool
from langchain_tavily import TavilySearch


class SearchTool(BaseTool):
    name: str = "search_tool"
    description: str = (
        "Use this tool to search the web for up-to-date information. "
        "Best used for recent events, breaking news, or current facts."
    )

    _search: TavilySearch = PrivateAttr()

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        # Ensure API key is set
        if not os.environ.get("TAVILY_API_KEY"):
            os.environ["TAVILY_API_KEY"] = "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"

        self._search = TavilySearch(
            max_results=5,
            topic="general"
        )

    def _run(self, query: str, run_manager: Optional[Any] = None) -> str:
        return self._search.invoke(query)

    async def _arun(self, query: str, run_manager: Optional[Any] = None) -> str:
        return await self._search.ainvoke(query)
