from __future__ import annotations

import asyncio
from typing import Dict, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.tools import StructuredTool


class McpTool:
    """
    MCP tool loader for HTTP/WebSocket transports only.
    Safe for Streamlit, LangChain agents, and pydantic v1 stacks.
    """

    def __init__(self, server_name: str, server_config: dict):
        self.server_name = server_name
        self.server_config = server_config
        self._tools: Dict[str, StructuredTool] = {}
        self._loaded = False

    # ---------------------------
    # Public API (sync)
    # ---------------------------
    def get_tool(self, tool_name: str) -> Optional[StructuredTool]:
        """
        Synchronous entrypoint for LangChain agents.
        """
        if not self._loaded:
            self._load_tools_sync()

        return self._tools.get(tool_name)

    # ---------------------------
    # Internal loading
    # ---------------------------
    def _load_tools_sync(self) -> None:
        """
        Load tools exactly once.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop → safe to run
            asyncio.run(self._load_tools_async())
        else:
            # Running loop (rare in Streamlit, but possible in tests)
            # Force async caller discipline
            raise RuntimeError(
                "McpTool.get_tool() called from an active event loop. "
                "Call `await load_tools_async()` explicitly instead."
            )

    async def _load_tools_async(self) -> None:
        """
        Internal async loader.
        """
        if self._loaded:
            return

        client = MultiServerMCPClient(
            {self.server_name: self.server_config}
        )

        async with client.session(self.server_name):
            mcp_tools = await client.get_tools()

            for t in mcp_tools:
                # Create a closure to capture the tool
                def make_sync_func(tool):
                    def sync_func(**kwargs):
                        kwargs.pop("ctx", None)
                        # Run the async function in a new event loop
                        try:
                            loop = asyncio.get_running_loop()
                            # If there's already a loop, we need to run in executor
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(
                                    asyncio.run, 
                                    tool.ainvoke(kwargs)
                                )
                                return future.result()
                        except RuntimeError:
                            # No event loop running, safe to create one
                            return asyncio.run(tool.ainvoke(kwargs))
                    return sync_func

                self._tools[t.name] = StructuredTool.from_function(
                    name=t.name,
                    description=t.description,
                    func=make_sync_func(t),  # Use sync wrapper instead of coroutine
                    args_schema=t.args_schema,
                )

        self._loaded = True

    async def load_tools_async(self) -> None:
        """
        Async version for advanced use.
        """
        await self._load_tools_async()